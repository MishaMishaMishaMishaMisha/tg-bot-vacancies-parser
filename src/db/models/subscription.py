from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
    true,
    DateTime
)
from sqlalchemy import UUID as SQLAlchemy_UUID
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
 
from .base import Base, TimestampMixin, _EMPTY_ARRAY

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.db.models.user import UserModel
    from src.db.models.notification import NotificationModel

 
class SubscriptionModel(TimestampMixin, Base):
    """Набор фильтров пользователя.
 
    Пустой массив фильтра означает «любое значение». Только `sources` обязателен.
    Значения хранятся в терминах бота (см. jobbot.models.SearchQuery и перечисления),
    а перевод в параметры конкретного сайта делают источники.
    """
 
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("cardinality(sources) > 0", name="sources_not_empty"),
        CheckConstraint("min_salary IS NULL OR min_salary >= 0", name="min_salary_non_negative"),
    )
 
    #id: Mapped[int] = mapped_column(primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(
                                SQLAlchemy_UUID(as_uuid=True),
                                primary_key=True,
                                server_default=text("gen_random_uuid()"))
    
    user_id: Mapped[uuid.UUID] = mapped_column(
                                    ForeignKey("users.id", ondelete="CASCADE"), 
                                    index=True, 
                                    nullable=False)
    
    name: Mapped[str | None] = mapped_column(String(100))
    
    is_active: Mapped[bool] = mapped_column(Boolean, 
                                            default=True, 
                                            server_default=true(), 
                                            nullable=False)
 
    # Какие сайты отслеживать: "dou", "djinni"...
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                               nullable=False, 
                                               server_default=_EMPTY_ARRAY)
 
    # Серверные фильтры (уходят на сайт)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                  nullable=False, 
                                                  server_default=_EMPTY_ARRAY)
    experiences: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                   nullable=False, 
                                                   server_default=_EMPTY_ARRAY)
    cities: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                              nullable=False, 
                                              server_default=_EMPTY_ARRAY)
    employments: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                   nullable=False, 
                                                   server_default=_EMPTY_ARRAY)
    english_levels: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                      nullable=False, 
                                                      server_default=_EMPTY_ARRAY)
    regions: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                               nullable=False, 
                                               server_default=_EMPTY_ARRAY)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    relocation: Mapped[bool] = mapped_column(Boolean, 
                                             default=False, 
                                             server_default=text("false"), 
                                             nullable=False)
 
    # Локальные фильтры (проверяются по тексту вакансии уже в боте)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                nullable=False, 
                                                server_default=_EMPTY_ARRAY)
    exclude_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), 
                                                        nullable=False, 
                                                        server_default=_EMPTY_ARRAY)
    
    seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
 

    user: Mapped["UserModel"] = relationship(back_populates="subscriptions", 
                                             lazy="raise_on_sql")
    
    notifications: Mapped[list["NotificationModel"]] = relationship(
                        back_populates="subscription", 
                        passive_deletes=True, 
                        lazy="raise_on_sql")
 
