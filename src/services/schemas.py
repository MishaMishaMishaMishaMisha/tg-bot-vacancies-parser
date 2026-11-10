from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from .jobs import Employment, Experience, Region

if TYPE_CHECKING:
    from src.db.models import SubscriptionModel, UserModel



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



@dataclass(slots=True)
class SubscriptionFilters:


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

    source: str
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.source}: {self.code}: {self.detail}"


@dataclass(slots=True)
class CreateSubscriptionResult:
    subscription: SubscriptionInfo
    warnings: list[QueryWarning] = field(default_factory=list)  



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
