"""Фоновый запуск: опрос сайтов, отправка уведомлений и периодическое обновление фильтров."""
from __future__ import annotations

import asyncio
import logging
import time

from .filter_catalog_service import FilterCatalogService
from .notification_service import NotificationService
from .polling_service import PollingService
from .schemas import CycleReport, DeliveryReport
from .settings import ServiceSettings

log = logging.getLogger(__name__)


class PollingScheduler:
    def __init__(
        self,
        polling: PollingService,
        delivery: NotificationService,
        catalog: FilterCatalogService,
        settings: ServiceSettings | None = None,
    ) -> None:
        self._polling = polling
        self._delivery = delivery
        self._catalog = catalog
        self._settings = settings or ServiceSettings()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_filters_refresh = time.monotonic()

    def start(self) -> None:
        """Запустить фоновую задачу (нужен работающий event loop, например, из on_startup бота)."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._last_filters_refresh = time.monotonic()
        self._task = asyncio.create_task(self._run(), name="polling-scheduler")

    async def stop(self, timeout: float = 30.0) -> None:
        """Остановить: дать текущему шагу закончиться, а по истечении timeout прервать."""
        self._stop.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def run_once(self) -> tuple[CycleReport | None, DeliveryReport | None]:
        """Один шаг: опрос сайтов и отправка. Ошибки логируются, шаги не мешают друг другу."""
        cycle: CycleReport | None = None
        delivery: DeliveryReport | None = None
        try:
            cycle = await self._polling.run_cycle()
        except Exception:
            log.exception("Цикл опроса завершился с ошибкой")
        try:
            # Отправляем и накопленное с прошлых раз (например, после перезапуска или сбоя Telegram)
            delivery = await self._delivery.deliver_pending()
            if delivery.sent or delivery.failed or delivery.users_deactivated:
                log.info("Отправка уведомлений: %s", delivery)
        except Exception:
            log.exception("Отправка уведомлений завершилась с ошибкой")
        return cycle, delivery

    async def _run(self) -> None:
        log.info("Планировщик запущен, интервал %s с", self._settings.poll_interval_seconds)
        while not self._stop.is_set():
            await self._refresh_filters_if_due()
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._settings.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
        log.info("Планировщик остановлен")

    async def _refresh_filters_if_due(self) -> None:
        if time.monotonic() - self._last_filters_refresh < self._settings.filters_refresh_interval_seconds:
            return
        self._last_filters_refresh = time.monotonic()
        try:
            await self._catalog.refresh_all()
        except Exception:
            log.exception("Не удалось обновить фильтры")
