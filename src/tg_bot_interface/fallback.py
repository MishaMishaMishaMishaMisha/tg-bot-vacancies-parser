from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from src.services import ServiceContainer

from . import screens, texts
from .common import get_main_subscription

router = Router(name="fallback")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message()
async def unknown_message(message: Message, container: ServiceContainer) -> None:
    subscription = await get_main_subscription(container, message.from_user.id)
    text, markup = screens.main_menu_screen(subscription)
    await message.answer(f"{texts.UNKNOWN_MESSAGE}\n\n{text}", reply_markup=markup)


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    """Кнопка из старого сообщения, которую бот уже не понимает (например, после обновления)."""
    await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
