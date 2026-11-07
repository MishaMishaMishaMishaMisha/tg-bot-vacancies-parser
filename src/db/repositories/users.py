from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from ..models import UserModel
from .base import BaseRepository


class UserRepository(BaseRepository[UserModel]):
    model = UserModel

    async def get_by_telegram_id(self, telegram_id: int) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.telegram_id == telegram_id)
        return await self.session.scalar(stmt)

    async def get_with_subscriptions(self, user_id: UUID) -> UserModel | None:
        """Пользователь вместе с подписками (в async-коде их нельзя подгрузить «лениво»)."""
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .options(selectinload(UserModel.subscriptions))
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(stmt)

    async def upsert_from_telegram(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        language_code: str | None = None,
    ) -> UserModel:
        """Создать пользователя или обновить его данные из Telegram (например, при /start).

        Заодно снова делает пользователя активным: если он написал боту, значит, не заблокировал его.
        """
        insert_stmt = pg_insert(UserModel).values(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[UserModel.telegram_id],
            set_={
                "username": insert_stmt.excluded.username,
                "first_name": insert_stmt.excluded.first_name,
                "language_code": insert_stmt.excluded.language_code,
                "is_active": True,
                "updated_at": func.now(),  # при ON CONFLICT Python-овый onupdate не срабатывает
            },
        ).returning(UserModel)
        result = await self.session.scalars(stmt, execution_options={"populate_existing": True})
        return result.one()

    async def set_active(self, user_id: UUID, is_active: bool) -> bool:
        stmt = update(UserModel).where(UserModel.id == user_id).values(is_active=is_active)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def set_active_by_telegram_id(self, telegram_id: int, is_active: bool) -> bool:
        """Например, выключить пользователя, который заблокировал бота."""
        stmt = update(UserModel).where(UserModel.telegram_id == telegram_id).values(is_active=is_active)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def list_active(self, *, limit: int | None = None, offset: int = 0) -> Sequence[UserModel]:
        stmt = select(UserModel).where(UserModel.is_active.is_(True)).order_by(UserModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.scalars(stmt)).all()

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(UserModel).where(UserModel.is_active.is_(True))
        return await self.session.scalar(stmt) or 0