"""Отправка накопленных уведомлений пользователям."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from .jobs import Vacancy
from .notifier import Notifier, NotifierError, RetryAfterError, UserBlockedError
from .schemas import DeliveryReport
from src.core.config import ServiceSettings
from .unit_of_work import UnitOfWork, UowFactory

log = logging.getLogger(__name__)

MAX_RATE_LIMIT_WAITS = 3   # сколько раз подряд ждём ответ «слишком часто», прежде чем засчитать неудачу


@dataclass(slots=True)
class _PendingItem:
    notification_id: UUID
    user_id: UUID
    telegram_id: int
    vacancy: Vacancy


class NotificationService:
    """Берёт из очереди уведомления со статусом pending и отправляет их через Notifier.

    Результат каждой отправки сразу фиксируется в БД отдельной короткой транзакцией, поэтому при
    падении процесса повторно уйдёт самое большее одно сообщение. Рассчитано на один рабочий процесс.
    """

    def __init__(
        self, notifier: Notifier, uow_factory: UowFactory = UnitOfWork, settings: ServiceSettings | None = None
    ) -> None:
        self._notifier = notifier
        self._uow_factory = uow_factory
        self._settings = settings or ServiceSettings()
        self._lock = asyncio.Lock()

    async def deliver_pending(self) -> DeliveryReport:
        """Отправить всё, что накопилось. Параллельные вызовы выстраиваются в очередь."""
        async with self._lock:
            report = DeliveryReport()
            handled: set[UUID] = set()    # за один вызов каждое уведомление пробуем один раз
            blocked: set[UUID] = set()

            while True:
                items, skipped_users = await self._load_batch(report)
                fresh = [item for item in items if item.notification_id not in handled]
                if not fresh and not skipped_users:
                    break
                for item in fresh:
                    handled.add(item.notification_id)
                    if item.user_id in blocked:
                        continue
                    await self._deliver_one(item, report, blocked)
                    await asyncio.sleep(self._settings.send_interval_seconds)
            return report


    async def _load_batch(self, report: DeliveryReport) -> tuple[list[_PendingItem], set[UUID]]:
        """Очередная порция. Уведомления неактивных пользователей снимаются с очереди, не отправляясь."""
        async with self._uow_factory() as uow:
            notifications = await uow.notifications.list_pending(limit=self._settings.delivery_batch_size)
            items: list[_PendingItem] = []
            inactive_users: set[UUID] = set()
            for n in notifications:
                if not n.user.is_active:
                    inactive_users.add(n.user_id)
                    continue
                items.append(_PendingItem(n.id, n.user_id, n.user.telegram_id, n.vacancy.to_domain()))

            for user_id in inactive_users:
                report.skipped += await uow.notifications.skip_pending_for_user(user_id)
            if inactive_users:
                await uow.commit()
            return items, inactive_users

    async def _deliver_one(self, item: _PendingItem, report: DeliveryReport, blocked: set[UUID]) -> None:
        for _ in range(MAX_RATE_LIMIT_WAITS):
            try:
                await self._notifier.send_vacancy(item.telegram_id, item.vacancy)
            except RetryAfterError as exc:
                log.warning("Telegram просит подождать %.1f с", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 0.5)
                continue
            except UserBlockedError:
                blocked.add(item.user_id)
                await self._deactivate_user(item.user_id)
                report.users_deactivated += 1
                return
            except NotifierError as exc:
                await self._register_failure(item.notification_id, str(exc))
                report.failed += 1
                return
            except Exception as exc:   # непредвиденная ошибка (например, в форматировании) не должна ронять рассылку
                log.exception("Неожиданная ошибка при отправке уведомления %s", item.notification_id)
                await self._register_failure(item.notification_id, repr(exc))
                report.failed += 1
                return
            else:
                await self._mark_sent(item.notification_id)
                report.sent += 1
                return

        await self._register_failure(item.notification_id, "превышен лимит запросов Telegram")
        report.failed += 1

    async def _mark_sent(self, notification_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.notifications.mark_sent([notification_id])
            await uow.commit()

    async def _register_failure(self, notification_id: UUID, error: str) -> None:
        async with self._uow_factory() as uow:
            await uow.notifications.register_failure(
                notification_id, error, max_attempts=self._settings.max_delivery_attempts
            )
            await uow.commit()

    async def _deactivate_user(self, user_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.users.set_active(user_id, False)
            await uow.notifications.skip_pending_for_user(user_id)
            await uow.commit()
