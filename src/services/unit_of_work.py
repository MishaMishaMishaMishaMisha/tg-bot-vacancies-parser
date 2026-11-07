"""Unit of Work: одна сессия БД, все репозитории на ней и явный commit.

    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(123)
        await uow.commit()

Если внутри блока было исключение или commit не вызывали, изменения откатываются.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.db_connection import async_session_factory
from src.db.repositories import (
    NotificationRepository,
    SubscriptionRepository,
    UserRepository,
    VacancyRepository,
)


class UnitOfWork:
    session: AsyncSession
    users: UserRepository
    subscriptions: SubscriptionRepository
    vacancies: VacancyRepository
    notifications: NotificationRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or async_session_factory

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.subscriptions = SubscriptionRepository(self.session)
        self.vacancies = VacancyRepository(self.session)
        self.notifications = NotificationRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self.session.rollback()
        finally:
            await self.session.close()   # незакоммиченное откатывается

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


UowFactory = Callable[[], UnitOfWork]
