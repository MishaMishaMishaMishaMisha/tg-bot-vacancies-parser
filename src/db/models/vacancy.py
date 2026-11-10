from __future__ import annotations

import uuid

from datetime import datetime
 
from sqlalchemy import (
    text,
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy import UUID as SQLAlchemy_UUID
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
 
from src.jobs_parsing.models import Vacancy as DomainVacancy
from .base import Base, utcnow, _EMPTY_ARRAY

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.db.models.notification import NotificationModel
 
 
class VacancyModel(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_vacancies_source_external_id"),
        Index("ix_vacancies_source_active_last_seen", "source", "is_active", "last_seen_at"),
    )
 
    id: Mapped[uuid.UUID] = mapped_column(
                                SQLAlchemy_UUID(as_uuid=True),
                                primary_key=True,
                                server_default=text("gen_random_uuid()"))
    
    # jobsdou/djinni/итд
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    
    # id вакансии на сайте
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
 
    title: Mapped[str] = mapped_column(Text, nullable=False)
    
    url: Mapped[str] = mapped_column(Text, nullable=False)
    
    company: Mapped[str | None] = mapped_column(Text)
    
    category: Mapped[str | None] = mapped_column(Text)
    
    locations: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                 nullable=False, 
                                                 server_default=_EMPTY_ARRAY)
    
    salary: Mapped[str | None] = mapped_column(Text)
    
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                            nullable=False, 
                                            server_default=_EMPTY_ARRAY)
    
    description: Mapped[str | None] = mapped_column(Text)
    
    # Для Djinni это время последнего обновления на сайте, а не создания.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Когда бот впервые и в последний раз видел вакансию на сайте.
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    
    # Вакансия пропала с сайта (поля можно не использовать, пока такая проверка не нужна).
    is_active: Mapped[bool] = mapped_column(Boolean, 
                                            default=True, 
                                            server_default=true(), 
                                            nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
 

    notifications: Mapped[list["NotificationModel"]] = relationship(
                        back_populates="vacancy", 
                        cascade="all, delete-orphan", 
                        passive_deletes=True, 
                        lazy="raise_on_sql")
 

    def to_domain(self) -> DomainVacancy:
        return DomainVacancy(
            source=self.source,
            id=self.external_id,
            title=self.title,
            url=self.url,
            company=self.company,
            category=self.category,
            locations=tuple(self.locations),
            salary=self.salary,
            published=self.published_at,
            tags=tuple(self.tags),
            text=self.description or "",
        )
 
 