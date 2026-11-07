from __future__ import annotations

import logging
from enum import Enum
from typing import Mapping, Protocol, Sequence
from uuid import UUID

from .exceptions import (
    SubscriptionLimitError,
    SubscriptionNotFoundError,
    UserNotFoundError,
    ValidationError,
)
from .jobs import Employment, Experience, JobSource, Region
from .query_builder import SubscriptionQueryBuilder
from .schemas import CreateSubscriptionResult, QueryWarning, SubscriptionFilters, SubscriptionInfo
from .settings import ServiceSettings
from .unit_of_work import UnitOfWork, UowFactory

log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100


class SubscriptionSeeder(Protocol):
    """Тот, кто «засевает» подписку: помечает текущие вакансии прочитанными (реализует PollingService)."""

    async def seed(self, subscription_id: UUID) -> object: ...


def _text(value: object) -> str:
    return str(value.value if isinstance(value, Enum) else value).strip()


def _unique(values: Sequence[object], *, lower: bool = False) -> list[str]:
    """Убирает пустые значения и повторы (без учёта регистра), сохраняя порядок."""
    result: dict[str, str] = {}
    for value in values:
        text = _text(value)
        if text:
            result.setdefault(text.casefold(), text.lower() if lower else text)
    return list(result.values())


class SubscriptionService:
    """Фильтры пользователей: создание, изменение, пауза, удаление."""

    def __init__(
        self,
        uow_factory: UowFactory,
        query_builder: SubscriptionQueryBuilder,
        sources: Mapping[str, JobSource],
        settings: ServiceSettings | None = None,
        seeder: SubscriptionSeeder | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._builder = query_builder
        self._sources = sources
        self._settings = settings or ServiceSettings()
        self._seeder = seeder

    # ------------------------------------------------------------------ создание и изменение

    async def create(
        self, telegram_id: int, filters: SubscriptionFilters, *, name: str | None = None
    ) -> CreateSubscriptionResult:
        """Сохранить фильтры пользователя.

        Бросает ValidationError, если фильтры некорректны или ни один из выбранных сайтов не может их
        выполнить. Если выполнить может не каждый сайт, подписка создаётся, а в результате приходят warnings.
        Текущие вакансии сразу помечаются как просмотренные, чтобы пользователь получал только новые.
        """
        normalized = self._normalize(filters)
        name = self._clean_name(name)
        await self._validate(normalized)
        warnings = await self._check_runnable(normalized)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            if user is None:
                raise UserNotFoundError(f"Пользователь {telegram_id} не зарегистрирован")
            if await uow.subscriptions.count_by_user(user.id) >= self._settings.max_subscriptions_per_user:
                raise SubscriptionLimitError(
                    f"Максимум подписок на пользователя: {self._settings.max_subscriptions_per_user}"
                )
            model = await uow.subscriptions.create(user_id=user.id, name=name, **normalized.to_columns())
            info = SubscriptionInfo.from_model(model)
            await uow.commit()

        info = await self._seed(info)
        return CreateSubscriptionResult(info, warnings)

    async def update(
        self,
        telegram_id: int,
        subscription_id: UUID,
        filters: SubscriptionFilters,
        *,
        name: str | None = None,
    ) -> CreateSubscriptionResult:
        """Заменить фильтры подписки целиком. Подписка «засевается» заново."""
        normalized = self._normalize(filters)
        await self._validate(normalized)
        warnings = await self._check_runnable(normalized)

        async with self._uow_factory() as uow:
            model = await self._get_owned(uow, telegram_id, subscription_id)
            values = {**normalized.to_columns(), "seeded_at": None}
            if name is not None:
                values["name"] = self._clean_name(name)
            await uow.subscriptions.update(model, **values)
            info = SubscriptionInfo.from_model(model)
            await uow.commit()

        info = await self._seed(info)
        return CreateSubscriptionResult(info, warnings)

    async def set_active(self, telegram_id: int, subscription_id: UUID, is_active: bool) -> SubscriptionInfo:
        """Поставить подписку на паузу или включить.

        После паузы подписка «засевается» заново: вакансии, появившиеся за время паузы, не придут пачкой.
        """
        async with self._uow_factory() as uow:
            model = await self._get_owned(uow, telegram_id, subscription_id)
            resumed = is_active and not model.is_active
            values: dict = {"is_active": is_active}
            if resumed:
                values["seeded_at"] = None
            await uow.subscriptions.update(model, **values)
            info = SubscriptionInfo.from_model(model)
            await uow.commit()

        if resumed:
            info = await self._seed(info)
        return info

    async def delete(self, telegram_id: int, subscription_id: UUID) -> bool:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            if user is None:
                return False
            deleted = await uow.subscriptions.delete_for_user(subscription_id, user.id)
            await uow.commit()
            return deleted

    # ------------------------------------------------------------------ чтение

    async def list_for_user(self, telegram_id: int, *, only_active: bool = False) -> list[SubscriptionInfo]:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            if user is None:
                raise UserNotFoundError(f"Пользователь {telegram_id} не зарегистрирован")
            models = await uow.subscriptions.list_by_user(user.id, only_active=only_active)
            return [SubscriptionInfo.from_model(m) for m in models]

    async def get(self, telegram_id: int, subscription_id: UUID) -> SubscriptionInfo:
        async with self._uow_factory() as uow:
            model = await self._get_owned(uow, telegram_id, subscription_id)
            return SubscriptionInfo.from_model(model)

    async def check(self, filters: SubscriptionFilters) -> list[QueryWarning]:
        """Проверить фильтры, ничего не сохраняя (например, для предпросмотра в боте).

        Бросает ValidationError, если подписку создать нельзя; иначе возвращает предупреждения.
        """
        normalized = self._normalize(filters)
        await self._validate(normalized)
        return await self._check_runnable(normalized)

    # ------------------------------------------------------------------ внутренности

    @staticmethod
    async def _get_owned(uow: UnitOfWork, telegram_id: int, subscription_id: UUID):
        user = await uow.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError(f"Пользователь {telegram_id} не зарегистрирован")
        model = await uow.subscriptions.get_for_user(subscription_id, user.id)
        if model is None:
            raise SubscriptionNotFoundError(f"Подписка {subscription_id} не найдена")
        return model

    @staticmethod
    def _clean_name(name: str | None) -> str | None:
        name = (name or "").strip()
        return name[:MAX_NAME_LENGTH] or None

    @staticmethod
    def _normalize(filters: SubscriptionFilters) -> SubscriptionFilters:
        return SubscriptionFilters(
            sources=_unique(filters.sources, lower=True),
            categories=_unique(filters.categories),
            experiences=_unique(filters.experiences),
            cities=_unique(filters.cities),
            employments=_unique(filters.employments),
            english_levels=_unique(filters.english_levels),
            regions=_unique(filters.regions),
            min_salary=filters.min_salary or None,
            relocation=bool(filters.relocation),
            keywords=_unique(filters.keywords, lower=True),
            exclude_keywords=_unique(filters.exclude_keywords, lower=True),
        )

    async def _validate(self, filters: SubscriptionFilters) -> None:
        """Проверки, не требующие знания о возможностях сайтов."""
        errors: list[str] = []
        s = self._settings

        if not filters.sources:
            errors.append("Не выбран ни один сайт.")
        unknown = [name for name in filters.sources if name not in self._sources]
        if unknown:
            errors.append(f"Неизвестные сайты: {', '.join(unknown)}.")

        for label, values, enum_cls in (
            ("опыт", filters.experiences, Experience),
            ("формат работы", filters.employments, Employment),
            ("регион", filters.regions, Region),
        ):
            allowed = {member.value for member in enum_cls}
            bad = [v for v in values if v not in allowed]
            if bad:
                errors.append(f"Недопустимое значение ({label}): {', '.join(bad)}.")

        if filters.min_salary is not None and not 0 < filters.min_salary <= s.max_salary:
            errors.append(f"Минимальная зарплата должна быть от 1 до {s.max_salary}.")

        for label, words in (("ключевые слова", filters.keywords), ("исключаемые слова", filters.exclude_keywords)):
            if len(words) > s.max_keywords:
                errors.append(f"Слишком много слов ({label}): максимум {s.max_keywords}.")
            if any(len(word) > s.max_keyword_length for word in words):
                errors.append(f"Слишком длинное слово ({label}): максимум {s.max_keyword_length} символов.")

        # Уровни английского проверяем по спискам сайтов, у которых они есть (сейчас это Djinni).
        if filters.english_levels and not errors:
            valid: set[str] = set()
            for name in filters.sources:
                options = await self._sources[name].get_filter_options()
                valid.update(item["value"] for item in options.groups.get("english_level", []))
            bad = [v for v in filters.english_levels if valid and v not in valid]
            if bad:
                errors.append(f"Недопустимый уровень английского: {', '.join(bad)}.")

        if errors:
            raise ValidationError(" ".join(errors))

    async def _check_runnable(self, filters: SubscriptionFilters) -> list[QueryWarning]:
        """Строит запросы для каждого сайта. Если не получилось ни для одного, подписка бесполезна."""
        warnings: list[QueryWarning] = []
        runnable = 0
        for name in filters.sources:
            plan = await self._builder.build(self._sources[name], filters)
            warnings.extend(plan.warnings)
            if plan.queries:
                runnable += 1
            else:
                warnings.append(
                    QueryWarning(name, "source_skipped", "сайт не может выполнить эти фильтры, он не будет опрашиваться")
                )
        if runnable == 0:
            raise ValidationError(
                "Ни один из выбранных сайтов не может выполнить эти фильтры.", warnings=warnings
            )
        return warnings

    async def _seed(self, info: SubscriptionInfo) -> SubscriptionInfo:
        """Засеять подписку сразу и вернуть её актуальное состояние (is_seeded).

        Если не вышло, ничего страшного: подписка без отметки «засеяна» в любом цикле опроса
        получает вакансии как пропущенные, и её засеет очередной цикл.
        """
        if self._seeder is None:
            return info
        try:
            await self._seeder.seed(info.id)
        except Exception:
            log.exception("Не удалось сразу засеять подписку %s; её засеет очередной цикл опроса", info.id)
            return info

        async with self._uow_factory() as uow:
            model = await uow.subscriptions.get(info.id)
            return SubscriptionInfo.from_model(model) if model is not None else info
