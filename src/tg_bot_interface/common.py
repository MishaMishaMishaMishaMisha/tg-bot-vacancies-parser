"""Общие помощники обработчиков."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.services import ServiceContainer, SubscriptionInfo

from . import screens

Event = Message | CallbackQuery


async def get_main_subscription(container: ServiceContainer, telegram_id: int) -> SubscriptionInfo | None:
    """Бот ведёт у пользователя один набор фильтров; если их несколько, берётся самый ранний."""
    subscriptions = await container.subscriptions.list_for_user(telegram_id)
    return min(subscriptions, key=lambda s: s.created_at) if subscriptions else None


async def english_labels(container: ServiceContainer) -> dict[str, str]:
    catalog = await container.filters.get_catalog()
    return {choice.value: choice.label for choice in catalog.english_levels}


class Ui:
    """Одно «живое» сообщение, которое бот редактирует по мере навигации по экранам."""

    def __init__(self, bot: Bot, chat_id: int, message_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    @classmethod
    def from_callback(cls, callback: CallbackQuery) -> "Ui | None":
        message = callback.message
        if not isinstance(message, Message):   # сообщение слишком старое или недоступно
            return None
        return cls(callback.bot, message.chat.id, message.message_id)

    @classmethod
    async def from_state(cls, bot: Bot, state: FSMContext) -> "Ui | None":
        data = await state.get_data()
        if "ui_chat_id" not in data or "ui_message_id" not in data:
            return None
        return cls(bot, data["ui_chat_id"], data["ui_message_id"])

    async def remember(self, state: FSMContext) -> None:
        await state.update_data(ui_chat_id=self.chat_id, ui_message_id=self.message_id)

    async def render(self, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        try:
            await self.bot.edit_message_text(
                text, chat_id=self.chat_id, message_id=self.message_id, reply_markup=markup
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():   # тот же текст и кнопки: не ошибка
                raise


async def respond(event: Event, text: str, markup: InlineKeyboardMarkup | None = None) -> Ui:
    """Ответ на сообщение (новое сообщение) или на нажатие кнопки (правка того же сообщения).

    Для кнопки ответ на callback (`callback.answer()`) обработчик отправляет сам, один раз.
    Возвращает Ui, чтобы потом обновить это же сообщение (например, «Зберігаю…» -> результат).
    """
    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        ui = Ui(event.bot, event.message.chat.id, event.message.message_id)
        await ui.render(text, markup)
        return ui
    message = event.message if isinstance(event, CallbackQuery) else event
    if message is None:   # у callback нет доступного сообщения: пишем в личный чат
        sent = await event.bot.send_message(event.from_user.id, text, reply_markup=markup)
    else:
        sent = await message.answer(text, reply_markup=markup)
    return Ui(event.bot, sent.chat.id, sent.message_id)


async def ack(event: Event) -> None:
    """Подтвердить нажатие кнопки (убирает «часики»); для обычных сообщений ничего не делает."""
    if isinstance(event, CallbackQuery):
        await event.answer()


async def show_main_menu(event: Event, container: ServiceContainer, notice: str | None = None) -> Ui:
    subscription = await get_main_subscription(container, event.from_user.id)
    text, markup = screens.main_menu_screen(subscription)
    return await respond(event, f"{notice}\n\n{text}" if notice else text, markup)
