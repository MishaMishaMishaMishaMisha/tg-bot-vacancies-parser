"""Сборка всех сервисов в одном месте.

    container = ServiceContainer(notifier=TelegramNotifier(bot))
    await container.start()        # запускает фоновый опрос
    ...
    await container.users.register(telegram_id, username=...)
    await container.subscriptions.create(telegram_id, SubscriptionFilters(...))
    ...
    await container.stop()
"""
from __future__ import annotations

from typing import Sequence

from .filter_catalog_service import FilterCatalogService
from .jobs import available_sources, create_source
from .notification_service import NotificationService
from .notifier import Notifier
from .polling_service import PollingService
from .query_builder import SubscriptionQueryBuilder
from .scheduler import PollingScheduler
from .settings import ServiceSettings
from .subscription_service import SubscriptionService
from .unit_of_work import UnitOfWork, UowFactory
from .user_service import UserService


class ServiceContainer:
    def __init__(
        self,
        notifier: Notifier,
        *,
        settings: ServiceSettings | None = None,
        uow_factory: UowFactory | None = None,
        source_names: Sequence[str] | None = None,
    ) -> None:
        self.settings = settings or ServiceSettings()
        uow_factory = uow_factory or UnitOfWork

        # Источники создаются один раз: у каждого свой HTTP-клиент, кэш фильтров и паузы между запросами.
        self.sources = {name: create_source(name) for name in (source_names or available_sources())}
        builder = SubscriptionQueryBuilder(self.settings.max_queries_per_subscription)

        self.users = UserService(uow_factory)
        self.filters = FilterCatalogService(self.sources, self.settings)
        self.polling = PollingService(self.sources, uow_factory, builder, self.settings)
        self.subscriptions = SubscriptionService(
            uow_factory, builder, self.sources, self.settings, seeder=self.polling
        )
        self.delivery = NotificationService(notifier, uow_factory, self.settings)
        self.scheduler = PollingScheduler(self.polling, self.delivery, self.filters, self.settings)

    async def start(self) -> None:
        self.scheduler.start()

    async def stop(self) -> None:
        await self.scheduler.stop()
        for source in self.sources.values():
            await source.aclose()
