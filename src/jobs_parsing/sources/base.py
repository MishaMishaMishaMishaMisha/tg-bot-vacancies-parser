"""Базовый класс источника вакансий и реестр источников."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import httpx

from ..models import FilterOptions, SearchQuery, Vacancy

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "uk,en;q=0.8",
}


class UnsupportedQuery(Exception):
    """Источник не умеет искать по такому набору фильтров."""


class JobSource(ABC):
    """Общий интерфейс. Новый сайт = новый подкласс с двумя методами:
    `fetch` и `fetch_filter_options`.
    """

    name: ClassVar[str]                 # короткий идентификатор: "dou", "djinni", ...
    min_interval: ClassVar[float] = 1.0  # минимальная пауза между запросами, сек

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        cache_dir: str | Path = "cache",
    ) -> None:
        # Свой клиент создаём сами и сами закрываем; переданный снаружи не трогаем
        # (в этом случае заголовки/таймауты задаёт вызывающий код).
        self._owns_client = client is None
        self.client = client if client is not None else httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        )
        self.cache_dir = Path(cache_dir)
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._options: FilterOptions | None = None

    # ---- что должен реализовать каждый источник --------------------------------

    @abstractmethod
    async def fetch(self, query: SearchQuery | None = None) -> list[Vacancy]:
        """Свежие вакансии по запросу (новые сверху)."""

    @abstractmethod
    async def fetch_filter_options(self) -> FilterOptions:
        """Скачать с сайта доступные значения фильтров."""
        
    @abstractmethod
    async def validate_query(self, query: SearchQuery) -> None:
        """Бросает UnsupportedQuery (или ValueError), если сайт не умеет искать по такому запросу."""

    # ---- общая логика ----------------------------------------------------------

    async def get_filter_options(self, refresh: bool = False) -> FilterOptions:
        """Фильтры с кэшем: память -> файл cache/<name>_filters.json -> сайт."""
        if self._options is not None and not refresh:
            return self._options

        path = self.cache_dir / f"{self.name}_filters.json"
        if not refresh and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            cached = FilterOptions.from_dict(data)
            if not cached.is_empty:  # файл другого формата (например, от старого скрипта) пропускаем
                self._options = cached
                return cached

        options = await self.fetch_filter_options()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(options.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._options = options
        return options

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET с паузой между запросами и проверкой статуса."""
        async with self._lock:
            wait = self._last_request + self.min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

        response = await self.client.get(url, **kwargs)
        log.debug("%s GET %s -> %s", self.name, response.url, response.status_code)
        response.raise_for_status()
        return response

    def _require_unset(self, query: SearchQuery, *names: str) -> None:
        """Бросает UnsupportedQuery, если задан фильтр, которого нет у этого сайта."""
        used = [n for n in names if getattr(query, n)]
        if used:
            raise UnsupportedQuery(f"{self.name}: не поддерживает фильтры {', '.join(used)}")

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def __aenter__(self) -> "JobSource":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()


# ---- реестр источников ---------------------------------------------------------

_REGISTRY: dict[str, type[JobSource]] = {}


def register_source(cls: type[JobSource]) -> type[JobSource]:
    """Декоратор: добавляет класс в реестр под его `name`."""
    _REGISTRY[cls.name] = cls
    return cls


def available_sources() -> list[str]:
    return sorted(_REGISTRY)


def create_source(name: str, **kwargs) -> JobSource:
    try:
        return _REGISTRY[name](**kwargs)
    except KeyError:
        raise ValueError(f"Неизвестный источник {name!r}. Доступны: {available_sources()}")
