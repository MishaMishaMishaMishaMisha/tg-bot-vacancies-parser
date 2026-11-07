from __future__ import annotations
 
import enum
import uuid

from datetime import datetime
 
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text
)
from sqlalchemy import UUID as SQLAlchemy_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
 
from .base import Base, utcnow

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.db.models.subscription import SubscriptionModel
    from src.db.models.user import UserModel
    from src.db.models.vacancy import VacancyModel


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"   # создано, ещё не отправлено
    SENT = "sent"         # отправлено пользователю
    SKIPPED = "skipped"   # помечено без отправки (например, вакансии, бывшие на момент подписки)
    FAILED = "failed"     # не удалось отправить после всех попыток
 
class NotificationModel(Base):
    """Связка «пользователь получил вакансию». Одна вакансия уходит пользователю один раз,
    даже если подходит под несколько его подписок: за это отвечает уникальность (user_id, vacancy_id).
    """
 
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_notifications_user_vacancy"),
        # Частичный индекс: очередь неотправленных остаётся маленькой, сколько бы ни было отправленных.
        Index("ix_notifications_pending", "id", postgresql_where=text("status = 'pending'")),
    )
 
    #id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(
                                SQLAlchemy_UUID(as_uuid=True),
                                primary_key=True,
                                server_default=text("gen_random_uuid()"))
    
    user_id: Mapped[uuid.UUID] = mapped_column(
                                ForeignKey("users.id", ondelete="CASCADE"), 
                                nullable=False)
    
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
                                ForeignKey("vacancies.id", ondelete="CASCADE"), 
                                index=True, 
                                nullable=False)
    
    # Какая подписка сработала (если подписку удалили, остаётся NULL).
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
                                ForeignKey("subscriptions.id", ondelete="SET NULL"), 
                                index=True)
 
    status: Mapped[NotificationStatus] = mapped_column(
                                Enum(
                                    NotificationStatus,
                                    native_enum=False, # обычный VARCHAR вместо типа ENUM: проще мигрировать
                                    length=16,
                                    create_constraint=False,
                                    values_callable=lambda enum_cls: [m.value for m in enum_cls],
                                ),
                                default=NotificationStatus.PENDING,
                                server_default=NotificationStatus.PENDING.value,
                                nullable=False)
    
    attempts: Mapped[int] = mapped_column(Integer, 
                                          default=0, 
                                          server_default=text("0"), 
                                          nullable=False)
    
    last_error: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
 
 
    user: Mapped["UserModel"] = relationship(
                                    back_populates="notifications",
                                    lazy="raise_on_sql")
    
    vacancy: Mapped["VacancyModel"] = relationship(
                                    back_populates="notifications", 
                                    lazy="raise_on_sql")
    
    subscription: Mapped["SubscriptionModel | None"] = relationship(
                                    back_populates="notifications", 
                                    lazy="raise_on_sql")
    
