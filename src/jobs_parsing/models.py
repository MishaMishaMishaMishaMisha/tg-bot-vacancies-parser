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

    category: str | None = None
    experience: Experience | None = None
    city: str | None = None             
    employment: Employment | None = None
    relocation: bool = False           
    english: str | None = None       
    region: Region | None = None    
    min_salary: int | None = None       


@dataclass(frozen=True, slots=True)
class Vacancy:
    source: str                    
    id: str                        
    title: str
    url: str
    company: str | None = None
    category: str | None = None
    locations: tuple[str, ...] = ()
    salary: str | None = None
    published: datetime | None = None
    tags: tuple[str, ...] = ()     
    text: str = ""               

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.id}"


@dataclass(slots=True)
class FilterOptions:
    """Какие значения фильтров умеет сайт (для кнопок в боте)."""

    categories: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    experiences: list[str] = field(default_factory=list)
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
