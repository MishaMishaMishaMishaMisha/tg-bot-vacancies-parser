from __future__ import annotations

import uuid
 
from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
    true,
    text
)
from sqlalchemy import UUID as SQLAlchemy_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.db.models.subscription import SubscriptionModel
    from src.db.models.notification import NotificationModel

 
class UserModel(TimestampMixin, Base):
    __tablename__ = "users"
 
    #id: Mapped[int] = mapped_column(primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(
                                SQLAlchemy_UUID(as_uuid=True),
                                primary_key=True,
                                server_default=text("gen_random_uuid()"))
    
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    
    username: Mapped[str | None] = mapped_column(String(64))
    
    first_name: Mapped[str | None] = mapped_column(String(128))
    
    language_code: Mapped[str | None] = mapped_column(String(16))
    
    # False, если пользователь заблокировал бота: таким пользователям не отправляем.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
 
 
    subscriptions: Mapped[list["SubscriptionModel"]] = relationship(
                        back_populates="user", 
                        cascade="all, delete-orphan", 
                        passive_deletes=True, 
                        lazy="raise_on_sql")
    
    notifications: Mapped[list["NotificationModel"]] = relationship(
                        back_populates="user", 
                        cascade="all, delete-orphan", 
                        passive_deletes=True, 
                        lazy="raise_on_sql")
