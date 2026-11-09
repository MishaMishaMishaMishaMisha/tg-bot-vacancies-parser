"""/start, главное меню, помощь и события блокировки бота."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import KICKED, MEMBER, ChatMemberUpdatedFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from src.services import ServiceContainer

from . import keyboards, screens, texts
from .callbacks import Action
from .common import ack, get_main_subscription, respond, show_main_menu

log = logging.getLogger(__name__)

router = Router(name="start")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    """Регистрация пользователя (или обновление его данных и повторное включение)."""
    await state.clear()
    user = message.from_user
    await container.users.register(
        user.id, username=user.username, first_name=user.first_name, language_code=user.language_code
    )
    subscription = await get_main_subscription(container, user.id)
    if subscription is None:
        await message.answer(texts.WELCOME_NEW, reply_markup=keyboards.main_menu(has_filters=False))
        return
    text, markup = screens.main_menu_screen(subscription)
    await message.answer(f"{texts.WELCOME_BACK}\n\n{text}", reply_markup=markup)


@router.message(Command("menu"))
@router.message(Command("cancel"))
async def cmd_menu(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    await state.clear()
    await show_main_menu(message, container)


@router.callback_query(Action.filter(F.a == "menu"))
async def cb_menu(callback: CallbackQuery, state: FSMContext, container: ServiceContainer) -> None:
    await state.clear()
    await ack(callback)
    await show_main_menu(callback, container)


@router.message(Command("help"))
@router.callback_query(Action.filter(F.a == "help"))
async def help_(event: Message | CallbackQuery) -> None:
    await ack(event)
    await respond(event, texts.HELP, keyboards.back_to_menu())


@router.callback_query(Action.filter(F.a == "noop"))
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ------------------------------------------------------------------ пользователь заблокировал или разблокировал бота

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, container: ServiceContainer) -> None:
    """Сообщения такому пользователю не отправляем; фильтры сохраняются."""
    await container.users.deactivate(event.from_user.id)
    log.info("Пользователь %s заблокировал бота", event.from_user.id)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, container: ServiceContainer) -> None:
    user = event.from_user
    await container.users.register(
        user.id, username=user.username, first_name=user.first_name, language_code=user.language_code
    )
