"""Превращает фильтры подписки в запросы к конкретному сайту.

У подписки фильтры списками (категории: Python и Java, опыт: 1-3 и 3-5 ...), а сайт принимает
один запрос на одну комбинацию. Поэтому строится произведение списков, и каждая комбинация
проверяется на то, умеет ли сайт её выполнить.

Важное правило: если пользователь что-то выбрал, а у сайта этого нет (категории или города
с таким названием), запросов для сайта не строится. Фильтр нельзя молча «ослабить» до «любое
значение»: пользователь получил бы лавину неподходящих вакансий.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .exceptions import ValidationError
from .jobs import Employment, Experience, JobSource, Region, SearchQuery, UnsupportedQuery
from .schemas import QueryWarning, SubscriptionFilters


@dataclass(slots=True)
class QueryPlan:
    source: str
    queries: list[SearchQuery] = field(default_factory=list)
    warnings: list[QueryWarning] = field(default_factory=list)


def _key(text: str) -> str:
    return text.strip().casefold()


class SubscriptionQueryBuilder:
    def __init__(self, max_queries: int = 30) -> None:
        self._max_queries = max_queries

    async def build(self, source: JobSource, filters: SubscriptionFilters) -> QueryPlan:
        plan = QueryPlan(source=source.name)
        options = await source.get_filter_options()   # из кэша; при первом вызове скачает с сайта

        categories = self._resolve_names(filters.categories, options.categories, plan, "categories_unavailable")
        cities = self._resolve_names(filters.cities, options.cities, plan, "cities_unavailable")
        experiences = self._parse_enum(filters.experiences, Experience, plan, "experiences_invalid")
        employments = self._parse_enum(filters.employments, Employment, plan, "employments_invalid")
        regions = self._parse_enum(filters.regions, Region, plan, "regions_invalid")
        english = list(filters.english_levels) or [None]

        axes = [categories, experiences, cities, employments, english, regions]
        total = math.prod(len(axis) for axis in axes)
        if total > self._max_queries:
            raise ValidationError(
                f"Слишком много комбинаций фильтров: {total} (максимум {self._max_queries}). "
                "Выберите меньше значений."
            )

        reasons: dict[str, None] = {}   # причины отказа без повторов, с сохранением порядка
        seen: set[SearchQuery] = set()
        # Если какая-то ось пуста (выбранного нет на сайте), произведение пустое и запросов не будет.
        for category, experience, city, employment, eng, region in itertools.product(*axes):
            query = SearchQuery(
                category=category,
                experience=experience,
                city=city,
                employment=employment,
                english=eng,
                region=region,
                min_salary=filters.min_salary or None,
                relocation=filters.relocation,
            )
            if query in seen:
                continue
            seen.add(query)
            try:
                await source.validate_query(query)
            except (UnsupportedQuery, ValueError) as exc:
                reasons.setdefault(str(exc), None)
                continue
            plan.queries.append(query)

        for reason in reasons:
            plan.warnings.append(QueryWarning(source.name, "unsupported_filter", reason))
        return plan

    @staticmethod
    def _resolve_names(
        wanted: Sequence[str], available: Sequence[str], plan: QueryPlan, code: str
    ) -> list[str | None]:
        """Сопоставляет выбранные названия с теми, что есть на сайте (без учёта регистра)."""
        if not wanted:
            return [None]
        index = {_key(name): name for name in available}
        resolved: list[str | None] = []
        missing: list[str] = []
        for value in wanted:
            canonical = index.get(_key(value))
            if canonical is None:
                missing.append(value)
            elif canonical not in resolved:
                resolved.append(canonical)
        if missing:
            plan.warnings.append(QueryWarning(plan.source, code, ", ".join(missing)))
        return resolved

    @staticmethod
    def _parse_enum(wanted: Sequence[str], enum_cls: type[Enum], plan: QueryPlan, code: str) -> list:
        if not wanted:
            return [None]
        parsed: list = []
        invalid: list[str] = []
        for value in wanted:
            try:
                member = enum_cls(value)
            except ValueError:
                invalid.append(value)
                continue
            if member not in parsed:
                parsed.append(member)
        if invalid:
            plan.warnings.append(QueryWarning(plan.source, code, ", ".join(invalid)))
        return parsed
