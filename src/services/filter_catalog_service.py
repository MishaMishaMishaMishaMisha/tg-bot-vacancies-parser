from __future__ import annotations

import asyncio
import logging
from typing import Mapping, Sequence

from .jobs import Employment, Experience, FilterOptions, JobSource, Region
from .schemas import FilterCatalog, FilterChoice
from .settings import ServiceSettings

log = logging.getLogger(__name__)


class FilterCatalogService:
    """Какие значения фильтров можно предложить пользователю (для кнопок и списков в боте)."""

    def __init__(self, sources: Mapping[str, JobSource], settings: ServiceSettings | None = None) -> None:
        self._sources = sources
        self._settings = settings or ServiceSettings()

    @property
    def source_names(self) -> list[str]:
        return sorted(self._sources)

    async def get_options(self, source: str) -> FilterOptions:
        """Фильтры одного сайта в его собственных терминах."""
        return await self._sources[source].get_filter_options()

    async def get_catalog(self, sources: Sequence[str] | None = None) -> FilterCatalog:
        """Объединённый каталог по выбранным сайтам (по умолчанию по всем)."""
        names = list(sources) if sources else self.source_names
        options = [await self.get_options(name) for name in names]

        categories = self._union(o.categories for o in options)
        cities = self._union(o.cities for o in options)

        english: dict[str, FilterChoice] = {}
        for option in options:
            for item in option.groups.get("english_level", []):
                english.setdefault(item["value"], FilterChoice(item["value"], item.get("label") or item["value"]))

        return FilterCatalog(
            categories=categories,
            cities=cities,
            experiences=list(Experience),
            employments=list(Employment),
            regions=list(Region),
            english_levels=list(english.values()),
            max_salary=self._settings.max_salary,
        )

    async def refresh(self, source: str) -> None:
        """Заново скачать фильтры сайта и обновить кэш на диске."""
        await self._sources[source].get_filter_options(refresh=True)

    async def refresh_all(self) -> dict[str, bool]:
        """Обновить фильтры всех сайтов. Сбой одного сайта не мешает остальным."""

        async def one(name: str) -> bool:
            try:
                await self.refresh(name)
                return True
            except Exception:
                log.exception("Не удалось обновить фильтры сайта %s", name)
                return False

        names = self.source_names
        results = await asyncio.gather(*(one(name) for name in names))
        return dict(zip(names, results))

    @staticmethod
    def _union(lists) -> list[str]:
        """Объединение списков без повторов (без учёта регистра), по алфавиту."""
        merged: dict[str, str] = {}
        for values in lists:
            for value in values:
                merged.setdefault(value.strip().casefold(), value)
        return sorted(merged.values(), key=str.casefold)
