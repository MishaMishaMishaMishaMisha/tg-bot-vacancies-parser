"""Базовые классы SQLAlchemy: Base с naming convention и миксин с временными метками."""
from __future__ import annotations
 
from datetime import datetime, timezone
 
from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
 
# Явные имена ограничений и индексов: без них Alembic (autogenerate) не сможет
# надёжно переименовывать и удалять ограничения.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Пустой массив по умолчанию на стороне БД.
_EMPTY_ARRAY = text("'{}'")
 
 
def utcnow() -> datetime:
    return datetime.now(timezone.utc)
 
 
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
 
 
class TimestampMixin:
 
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )