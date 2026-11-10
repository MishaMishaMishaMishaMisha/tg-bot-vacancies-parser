from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from src.db.models import NotificationStatus
from src.db.repositories import NewNotification

from .exceptions import ValidationError
from .jobs import JobSource, SearchQuery, Vacancy
from .matching import passes_local_filters
from .query_builder import SubscriptionQueryBuilder
from .schemas import CycleReport, SubscriptionFilters
from src.core.config import ServiceSettings
from .unit_of_work import UnitOfWork, UowFactory

log = logging.getLogger(__name__)

QueryKey = tuple[str, SearchQuery]   # (имя сайта, запрос)


@dataclass(slots=True, eq=False)
class ActiveSubscription:

    id: UUID
    user_id: UUID
    filters: SubscriptionFilters
    is_seeded: bool


class PollingService:
    """Основной процесс.

    1. Берёт включённые подписки активных пользователей.
    2. Для каждой подписки и сайта строит запросы и объединяет одинаковые: если у 20 человек
       одинаковый фильтр, на сайт уходит один запрос.
    3. Скачивает вакансии (разные сайты параллельно, внутри сайта по очереди).
    4. Сохраняет вакансии, определяет подходящие подписки и создаёт уведомления
       (повторно одну вакансию одному пользователю создать нельзя, это гарантирует БД).
    5. «Засевает» новые подписки: для них текущие вакансии помечаются пропущенными, не отправляются.

    Отправкой сообщений занимается NotificationService.
    """

    def __init__(
        self,
        sources: Mapping[str, JobSource],
        uow_factory: UowFactory = UnitOfWork,
        query_builder: SubscriptionQueryBuilder | None = None,
        settings: ServiceSettings | None = None,
    ) -> None:
        self._sources = sources
        self._uow_factory = uow_factory
        self._settings = settings or ServiceSettings()
        self._builder = query_builder or SubscriptionQueryBuilder(self._settings.max_queries_per_subscription)
        self._cycle_lock = asyncio.Lock()



    async def run_cycle(self) -> CycleReport:
        """Один полный проход по всем подписчикам. Два цикла одновременно не выполняются."""
        async with self._cycle_lock:
            return await self._run(only=None)

    async def seed(self, subscription_id: UUID) -> CycleReport:
        """Засеять одну подписку (вызывается сразу после её создания или изменения).

        Не ждёт общий цикл: все операции безопасно повторяются, а подписка без отметки «засеяна»
        в любом цикле получает вакансии как пропущенные, а не как новые.
        """
        return await self._run(only={subscription_id})

   

    async def _run(self, only: set[UUID] | None) -> CycleReport:
        started = time.monotonic()
        report = CycleReport()

        subscriptions = await self._load_subscriptions(only)
        report.subscriptions = len(subscriptions)
        if not subscriptions:
            return report

        subscribers, keys_by_subscription = await self._plan(subscriptions)
        report.queries_planned = len(subscribers)

        fetched, failed = await self._fetch_all(list(subscribers))
        report.queries_failed = len(failed)

        await self._save_and_match(subscriptions, subscribers, keys_by_subscription, fetched, failed, report)
        report.duration_seconds = time.monotonic() - started
        log.info("Цикл опроса: %s", report)
        return report

    async def _load_subscriptions(self, only: set[UUID] | None) -> list[ActiveSubscription]:
        async with self._uow_factory() as uow:
            models = await uow.subscriptions.list_active()
            return [
                ActiveSubscription(
                    id=m.id,
                    user_id=m.user_id,
                    filters=SubscriptionFilters.from_model(m),
                    is_seeded=m.seeded_at is not None,
                )
                for m in models
                if only is None or m.id in only
            ]

    async def _plan(
        self, subscriptions: list[ActiveSubscription]
    ) -> tuple[dict[QueryKey, list[ActiveSubscription]], dict[UUID, list[QueryKey]]]:
        """Объединяет запросы подписок: ключ (сайт, запрос) -> кому он нужен."""
        subscribers: dict[QueryKey, list[ActiveSubscription]] = {}
        keys_by_subscription: dict[UUID, list[QueryKey]] = {s.id: [] for s in subscriptions}

        for subscription in subscriptions:
            for source_name in subscription.filters.sources:
                source = self._sources.get(source_name)
                if source is None:
                    log.warning("Подписка %s: неизвестный сайт %r", subscription.id, source_name)
                    continue
                try:
                    plan = await self._builder.build(source, subscription.filters)
                except ValidationError as exc:
                    log.warning("Подписка %s, сайт %s пропущен: %s", subscription.id, source_name, exc)
                    continue
                except Exception:
                    log.exception("Подписка %s, сайт %s: не удалось построить запросы", subscription.id, source_name)
                    continue
                for query in plan.queries:
                    key = (source_name, query)
                    subscribers.setdefault(key, []).append(subscription)
                    keys_by_subscription[subscription.id].append(key)
        return subscribers, keys_by_subscription

    async def _fetch_all(self, keys: list[QueryKey]) -> tuple[dict[QueryKey, list[Vacancy]], set[QueryKey]]:
        by_source: dict[str, list[SearchQuery]] = {}
        for source_name, query in keys:
            by_source.setdefault(source_name, []).append(query)

        fetched: dict[QueryKey, list[Vacancy]] = {}
        failed: set[QueryKey] = set()

        async def fetch_source(name: str, queries: list[SearchQuery]) -> None:
            source = self._sources[name]
            for query in queries:   # внутри сайта по очереди: источник сам выдерживает паузы между запросами
                try:
                    items = await source.fetch(query)
                    fetched[(name, query)] = [self._with_category(v, query) for v in items]
                except Exception as exc:   # сбой одного запроса не должен ронять весь цикл
                    failed.add((name, query))
                    log.warning("Запрос не выполнен: %s %s: %s", name, query, exc)

        await asyncio.gather(*(fetch_source(name, queries) for name, queries in by_source.items()))
        return fetched, failed

    @staticmethod
    def _with_category(vacancy: Vacancy, query: SearchQuery) -> Vacancy:
        """DOU не отдаёт категорию в RSS: берём ту, по которой вакансию нашли."""
        if vacancy.category is None and query.category:
            return replace(vacancy, category=query.category)
        return vacancy

    async def _save_and_match(
        self,
        subscriptions: list[ActiveSubscription],
        subscribers: dict[QueryKey, list[ActiveSubscription]],
        keys_by_subscription: dict[UUID, list[QueryKey]],
        fetched: dict[QueryKey, list[Vacancy]],
        failed: set[QueryKey],
        report: CycleReport,
    ) -> None:
        unique: dict[tuple[str, str], Vacancy] = {}
        for items in fetched.values():
            for vacancy in items:
                unique.setdefault((vacancy.source, vacancy.id), vacancy)
        report.vacancies_fetched = len(unique)

        async with self._uow_factory() as uow:
            result = await uow.vacancies.upsert_many(list(unique.values()))
            db_ids = {(m.source, m.external_id): m.id for m in (*result.new, *result.existing)}
            new_keys = {(m.source, m.external_id) for m in result.new}
            report.new_vacancies = len(result.new)

            pending: list[NewNotification] = []
            skipped: list[NewNotification] = []
            for key, items in fetched.items():
                self._warn_if_gap(key, items, new_keys, subscribers[key])
                for subscription in subscribers[key]:
                    f = subscription.filters
                    for vacancy in items:
                        if not passes_local_filters(vacancy, f.keywords, f.exclude_keywords):
                            continue
                        notification = NewNotification(
                            user_id=subscription.user_id,
                            vacancy_id=db_ids[(vacancy.source, vacancy.id)],
                            subscription_id=subscription.id,
                        )
                        (pending if subscription.is_seeded else skipped).append(notification)

            # Сначала настоящие уведомления: если вакансия подходит и «засеянной», и новой подписке
            # одного пользователя, должна сработать «засеянная».
            created = await uow.notifications.add_many_if_absent(pending, status=NotificationStatus.PENDING)
            await uow.notifications.add_many_if_absent(skipped, status=NotificationStatus.SKIPPED)
            report.notifications_created = len(created)

            # Подписка считается засеянной, если все её запросы выполнены. Иначе повторим в следующем цикле.
            for subscription in subscriptions:
                if subscription.is_seeded:
                    continue
                if any(key in failed for key in keys_by_subscription[subscription.id]):
                    continue
                await uow.subscriptions.update_by_id(subscription.id, seeded_at=datetime.now(timezone.utc))
                report.subscriptions_seeded += 1

            await uow.commit()

    def _warn_if_gap(
        self,
        key: QueryKey,
        items: list[Vacancy],
        new_keys: set[tuple[str, str]],
        subscribers: list[ActiveSubscription],
    ) -> None:
        """Выдача целиком из новых вакансий может означать, что часть новых уже вытеснена за её пределы."""
        if len(items) < self._settings.gap_warning_threshold:
            return
        if not any(s.is_seeded for s in subscribers):
            return   # для новых подписок это ожидаемо
        if all((v.source, v.id) in new_keys for v in items):
            log.warning(
                "Все %s вакансий по запросу %s %s новые: возможно, часть пропущена. "
                "Опрашивайте чаще или сузьте фильтры.",
                len(items), key[0], key[1],
            )
