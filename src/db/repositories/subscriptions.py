from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import contains_eager

from ..models import SubscriptionModel, UserModel
from .base import BaseRepository


class SubscriptionRepository(BaseRepository[SubscriptionModel]):
    model = SubscriptionModel

    async def get_for_user(self, subscription_id: UUID, user_id: UUID) -> SubscriptionModel | None:

        stmt = select(SubscriptionModel).where(
            SubscriptionModel.id == subscription_id, SubscriptionModel.user_id == user_id
        )
        return await self.session.scalar(stmt)

    async def list_by_user(self, user_id: UUID, *, only_active: bool = False) -> Sequence[SubscriptionModel]:
        stmt = select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        if only_active:
            stmt = stmt.where(SubscriptionModel.is_active.is_(True))
        return (await self.session.scalars(stmt.order_by(SubscriptionModel.id))).all()

    async def count_by_user(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        return await self.session.scalar(stmt) or 0

    async def list_active(self, source: str | None = None) -> Sequence[SubscriptionModel]:

        stmt = (
            select(SubscriptionModel)
            .join(SubscriptionModel.user)
            .where(SubscriptionModel.is_active.is_(True), UserModel.is_active.is_(True))
            .options(contains_eager(SubscriptionModel.user))
            .order_by(SubscriptionModel.id)
        )
        if source is not None:
            stmt = stmt.where(SubscriptionModel.sources.any(source))
        return (await self.session.scalars(stmt)).all()

    async def set_active(self, subscription_id: UUID, is_active: bool) -> bool:
        stmt = update(SubscriptionModel).where(SubscriptionModel.id == subscription_id).values(is_active=is_active)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def delete_for_user(self, subscription_id: UUID, user_id: UUID) -> bool:
        stmt = delete(SubscriptionModel).where(
            SubscriptionModel.id == subscription_id, SubscriptionModel.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0