from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from src.db.models.base import utcnow
from ..models import NotificationModel, NotificationStatus
from .base import BaseRepository


@dataclass(frozen=True, slots=True)
class NewNotification:
    user_id: UUID
    vacancy_id: UUID
    subscription_id: UUID | None = None


class NotificationRepository(BaseRepository[NotificationModel]):
    model = NotificationModel
    CHUNK = 1000

    async def add_many_if_absent(
        self,
        items: Sequence[NewNotification],
        *,
        status: NotificationStatus = NotificationStatus.PENDING,
    ) -> list[NotificationModel]:
        """Создаёт уведомления, которых ещё нет, и возвращает ТОЛЬКО созданные.

        Пара (user_id, vacancy_id) уникальна, поэтому повторно вакансия пользователю не уйдёт,
        даже если она подходит под несколько его подписок или попала в выдачу снова.
        Со status=SKIPPED этим же методом «засевают» вакансии, уже существующие в момент создания подписки.
        """
        unique = {(i.user_id, i.vacancy_id): i for i in items}
        created_ids: list[int] = []
        values = list(unique.values())

        for start in range(0, len(values), self.CHUNK):
            rows = [
                {
                    "user_id": i.user_id,
                    "vacancy_id": i.vacancy_id,
                    "subscription_id": i.subscription_id,
                    "status": status,
                }
                for i in values[start:start + self.CHUNK]
            ]
            stmt = (
                pg_insert(NotificationModel)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[NotificationModel.user_id, NotificationModel.vacancy_id])
                .returning(NotificationModel.id)
            )
            created_ids += list((await self.session.scalars(stmt)).all())
        return list(await self.get_many(created_ids))

    async def get_notified_vacancy_ids(self, user_id: UUID, vacancy_ids: Iterable[UUID]) -> set[UUID]:
        """Какие из этих вакансий пользователь уже получил (или они помечены как пропущенные)."""
        ids = list(vacancy_ids)
        if not ids:
            return set()
        stmt = select(NotificationModel.vacancy_id).where(
            NotificationModel.user_id == user_id, NotificationModel.vacancy_id.in_(ids)
        )
        return set((await self.session.scalars(stmt)).all())

    async def list_pending(self, *, limit: int = 100, lock: bool = False) -> Sequence[NotificationModel]:
        """Очередь на отправку: сразу с пользователем и вакансией.

        lock=True берёт строки с FOR UPDATE SKIP LOCKED: так несколько воркеров не заберут одно и то же.
        """
        stmt = (
            select(NotificationModel)
            .where(NotificationModel.status == NotificationStatus.PENDING)
            .options(selectinload(NotificationModel.user), selectinload(NotificationModel.vacancy))
            .order_by(NotificationModel.id)
            .limit(limit)
        )
        if lock:
            stmt = stmt.with_for_update(skip_locked=True, of=NotificationModel)
        return (await self.session.scalars(stmt)).all()

    async def mark_sent(self, notification_ids: Iterable[UUID]) -> int:
        ids = list(notification_ids)
        if not ids:
            return 0
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.id.in_(ids))
            .values(status=NotificationStatus.SENT, sent_at=utcnow(), last_error=None)
            .execution_options(synchronize_session=False)
        )
        return (await self.session.execute(stmt)).rowcount

    async def register_failure(
        self, notification_id: UUID, error: str, *, max_attempts: int = 3
    ) -> NotificationModel | None:
        """Записать неудачную отправку. После max_attempts попыток статус становится FAILED."""
        notification = await self.get(notification_id)
        if notification is None:
            return None
        notification.attempts += 1
        notification.last_error = error[:1000]
        if notification.attempts >= max_attempts:
            notification.status = NotificationStatus.FAILED
        await self.session.flush()
        return notification

    async def skip_pending_for_user(self, user_id: UUID) -> int:
        """Снять с очереди всё неотправленное (например, пользователь заблокировал бота)."""
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.status == NotificationStatus.PENDING)
            .values(status=NotificationStatus.SKIPPED)
            .execution_options(synchronize_session=False)
        )
        return (await self.session.execute(stmt)).rowcount

    async def count_by_status(self) -> dict[NotificationStatus, int]:
        stmt = select(NotificationModel.status, func.count()).group_by(NotificationModel.status)
        return {status: n for status, n in (await self.session.execute(stmt)).all()}

    async def delete_older_than(self, created_before: datetime) -> int:
        """Чистка старых уведомлений. Внимание: после удаления вакансия снова может уйти пользователю,
        если она ещё есть в выдаче, поэтому порог должен быть заметно больше срока жизни вакансий.
        """
        stmt = delete(NotificationModel).where(
            NotificationModel.created_at < created_before,
            NotificationModel.status != NotificationStatus.PENDING,
        )
        return (await self.session.execute(stmt)).rowcount