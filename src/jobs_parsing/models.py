"""Общие модели данных. Не зависят от конкретного сайта."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum


class Experience(str, Enum):
    """Опыт в терминах бота. Каждый источник сам переводит это в свои параметры."""

    NONE = "none"        # без опыта
    UP_TO_1 = "0-1"
    Y1_3 = "1-3"
    Y3_5 = "3-5"
    Y5_PLUS = "5plus"


class Employment(str, Enum):
    """Формат работы. Значения совпадают с параметром employment на Djinni."""

    REMOTE = "remote"
    PART_TIME = "parttime"
    OFFICE = "office"


class Region(str, Enum):
    """Регион вакансии. Значения совпадают с параметром region на Djinni."""

    WORLDWIDE = "worldwide"
    UKRAINE = "UKR"
    EU = "eu"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Один запрос к сайту (то, что уходит на сторону сайта).

    frozen=True делает объект хэшируемым: его можно использовать как ключ словаря,
    чтобы объединять одинаковые подписки разных пользователей в один запрос.
    Всё остальное (ключевые слова и т.д.) проверяется локально.

    Если источник не умеет какой-то фильтр, он бросает UnsupportedQuery:
    молча игнорировать фильтр нельзя, пользователь получил бы неподходящие вакансии.
    """

    category: str | None = None
    experience: Experience | None = None
    city: str | None = None              # название города: «Київ»
    employment: Employment | None = None
    relocation: bool = False             # только DOU
    english: str | None = None           # значение сайта (см. FilterOptions.groups); только Djinni
    region: Region | None = None         # только Djinni
    min_salary: int | None = None        # только Djinni


@dataclass(frozen=True, slots=True)
class Vacancy:
    source: str                      # "dou", "djinni", ...
    id: str                          # id внутри источника
    title: str
    url: str
    company: str | None = None
    category: str | None = None
    locations: tuple[str, ...] = ()
    salary: str | None = None
    # Для Djinni это время последнего обновления вакансии, а не создания.
    published: datetime | None = None
    tags: tuple[str, ...] = ()       # прочие метки карточки: опыт, английский, домен...
    text: str = ""                   # описание без HTML

    @property
    def uid(self) -> str:
        """Глобально уникальный ключ: id могут совпасть на разных сайтах."""
        return f"{self.source}:{self.id}"


@dataclass(slots=True)
class FilterOptions:
    """Какие значения фильтров умеет сайт (для кнопок в боте)."""

    categories: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    experiences: list[str] = field(default_factory=list)  # «родные» значения сайта
    flags: list[str] = field(default_factory=list)        # фильтры-флаги: remote, ...
    # Остальные группы фильтров: имя параметра -> [{"value": ..., "label": ...}]
    groups: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.categories or self.cities or self.experiences or self.flags or self.groups)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FilterOptions":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
