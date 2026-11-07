"""Объекты, которыми сервисы обмениваются с ботом.

Сервисы возвращают эти dataclass, а не ORM-модели: после закрытия сессии с моделями
в async-коде нельзя безопасно работать (DetachedInstanceError / MissingGreenlet).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from .jobs import Employment, Experience, Region

if TYPE_CHECKING:
    from src.db.models import SubscriptionModel, UserModel


# ------------------------------------------------------------------ пользователи

@dataclass(slots=True)
class UserInfo:
    id: UUID
    telegram_id: int
    username: str | None
    first_name: str | None
    language_code: str | None
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, model: "UserModel") -> "UserInfo":
        return cls(
            id=model.id,
            telegram_id=model.telegram_id,
            username=model.username,
            first_name=model.first_name,
            language_code=model.language_code,
            is_active=model.is_active,
            created_at=model.created_at,
        )


# ------------------------------------------------------------------ подписки

@dataclass(slots=True)
class SubscriptionFilters:
    """Фильтры подписки в терминах бота. Пустой список означает «любое значение».

    sources           сайты: "dou", "djinni"
    experiences       значения Experience: "none", "0-1", "1-3", "3-5", "5plus"
    employments       значения Employment: "remote", "parttime", "office"
    regions           значения Region: "worldwide", "UKR", "eu", "other"
    english_levels    значения сайта (см. FilterCatalog.english_levels), только Djinni
    categories/cities названия как в FilterCatalog
    keywords          в вакансии должно встретиться хотя бы одно из слов
    exclude_keywords  вакансия с любым из этих слов не отправляется
    """

    sources: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    experiences: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    employments: list[str] = field(default_factory=list)
    english_levels: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    min_salary: int | None = None
    relocation: bool = False
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, model: "SubscriptionModel") -> "SubscriptionFilters":
        return cls(
            sources=list(model.sources),
            categories=list(model.categories),
            experiences=list(model.experiences),
            cities=list(model.cities),
            employments=list(model.employments),
            english_levels=list(model.english_levels),
            regions=list(model.regions),
            min_salary=model.min_salary,
            relocation=model.relocation,
            keywords=list(model.keywords),
            exclude_keywords=list(model.exclude_keywords),
        )

    def to_columns(self) -> dict:
        """Имена полей совпадают с колонками SubscriptionModel."""
        return asdict(self)


@dataclass(slots=True)
class SubscriptionInfo:
    id: UUID
    user_id: UUID
    name: str | None
    is_active: bool
    filters: SubscriptionFilters
    created_at: datetime
    is_seeded: bool    # False: идёт «засев», уведомления по этой подписке ещё не отправляются

    @classmethod
    def from_model(cls, model: "SubscriptionModel") -> "SubscriptionInfo":
        return cls(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            is_active=model.is_active,
            filters=SubscriptionFilters.from_model(model),
            created_at=model.created_at,
            is_seeded=model.seeded_at is not None,
        )


@dataclass(slots=True)
class QueryWarning:
    """Что не удалось учесть при построении запросов к сайту.

    code: categories_unavailable | cities_unavailable | experiences_invalid |
          employments_invalid | regions_invalid | unsupported_filter | source_skipped | unknown_source
    """

    source: str
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.source}: {self.code}: {self.detail}"


@dataclass(slots=True)
class CreateSubscriptionResult:
    subscription: SubscriptionInfo
    warnings: list[QueryWarning] = field(default_factory=list)   # бот может показать их пользователю


# ------------------------------------------------------------------ каталог фильтров для кнопок бота

@dataclass(slots=True)
class FilterChoice:
    value: str
    label: str


@dataclass(slots=True)
class FilterCatalog:
    categories: list[str]
    cities: list[str]
    experiences: list[Experience]
    employments: list[Employment]
    regions: list[Region]
    english_levels: list[FilterChoice]
    max_salary: int


# ------------------------------------------------------------------ отчёты о работе

@dataclass(slots=True)
class CycleReport:
    subscriptions: int = 0
    queries_planned: int = 0
    queries_failed: int = 0
    vacancies_fetched: int = 0
    new_vacancies: int = 0
    notifications_created: int = 0
    subscriptions_seeded: int = 0
    duration_seconds: float = 0.0


@dataclass(slots=True)
class DeliveryReport:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    users_deactivated: int = 0
