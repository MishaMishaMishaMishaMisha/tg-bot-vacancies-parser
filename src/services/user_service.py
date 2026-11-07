from __future__ import annotations

import logging

from .exceptions import UserNotFoundError
from .schemas import UserInfo
from .unit_of_work import UnitOfWork, UowFactory

log = logging.getLogger(__name__)


class UserService:
    """Пользователи Telegram: регистрация, обновление профиля, включение и выключение."""

    def __init__(self, uow_factory: UowFactory = UnitOfWork) -> None:
        self._uow_factory = uow_factory

    async def register(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        language_code: str | None = None,
    ) -> UserInfo:
        """Создать пользователя или обновить его данные (вызывайте в обработчике /start).

        Заодно снова включает пользователя, который раньше заблокировал бота.
        """
        async with self._uow_factory() as uow:
            user = await uow.users.upsert_from_telegram(
                telegram_id, username=username, first_name=first_name, language_code=language_code
            )
            info = UserInfo.from_model(user)   # DTO собираем до commit: после него атрибуты «протухают»
            await uow.commit()
            return info

    async def get(self, telegram_id: int) -> UserInfo | None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            return UserInfo.from_model(user) if user else None

    async def deactivate(self, telegram_id: int) -> bool:
        """Пользователь заблокировал бота: больше не отправляем и снимаем неотправленное с очереди.

        Вызывайте из обработчика my_chat_member (статус kicked). Подписки не удаляются,
        поэтому после /start всё продолжит работать.
        """
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            if user is None:
                return False
            await uow.users.set_active(user.id, False)
            await uow.notifications.skip_pending_for_user(user.id)
            await uow.commit()
            return True

    async def delete(self, telegram_id: int) -> bool:
        """Полностью удалить пользователя со всеми подписками и уведомлениями."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_telegram_id(telegram_id)
            if user is None:
                return False
            await uow.users.delete(user)
            await uow.commit()
            return True

    async def require(self, telegram_id: int) -> UserInfo:
        """Как get, но с исключением: удобно для обработчиков, которым нужен зарегистрированный пользователь."""
        user = await self.get(telegram_id)
        if user is None:
            raise UserNotFoundError(f"Пользователь {telegram_id} не зарегистрирован")
        return user

    async def count_active(self) -> int:
        async with self._uow_factory() as uow:
            return await uow.users.count_active()
