"""Мои фильтры, пауза и возобновление уведомлений, удаление фильтров."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.services import ServiceContainer

from . import keyboards, screens, texts
from .callbacks import Action
from .common import ack, english_labels, get_main_subscription, respond, show_main_menu

router = Router(name="subscription")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("filters"))
@router.callback_query(Action.filter(F.a == "show"))
async def show_filters(event: Message | CallbackQuery, container: ServiceContainer) -> None:
    await ack(event)
    subscription = await get_main_subscription(container, event.from_user.id)
    text, markup = screens.my_filters_screen(subscription, await english_labels(container))
    await respond(event, text, markup)


@router.message(Command("pause"))
@router.callback_query(Action.filter(F.a == "pause"))
async def pause(event: Message | CallbackQuery, container: ServiceContainer) -> None:
    """Отказ от уведомлений: фильтры и аккаунт остаются, вакансии просто не приходят."""
    await ack(event)
    subscription = await get_main_subscription(container, event.from_user.id)
    if subscription is None:
        await respond(event, texts.NO_FILTERS, keyboards.main_menu(has_filters=False))
        return
    if subscription.is_active:
        await container.subscriptions.set_active(event.from_user.id, subscription.id, False)
    await respond(event, texts.PAUSED, keyboards.main_menu(has_filters=True, is_active=False))


@router.message(Command("resume"))
@router.callback_query(Action.filter(F.a == "resume"))
async def resume(event: Message | CallbackQuery, container: ServiceContainer) -> None:
    """Возобновление: подписка заново «засевается», поэтому пропущенные за паузу вакансии не придут пачкой."""
    await ack(event)
    subscription = await get_main_subscription(container, event.from_user.id)
    if subscription is None:
        await respond(event, texts.NO_FILTERS, keyboards.main_menu(has_filters=False))
        return
    if not subscription.is_active:
        ui = await respond(event, texts.RESUMING)
        await container.subscriptions.set_active(event.from_user.id, subscription.id, True)
        await ui.render(texts.RESUMED, keyboards.main_menu(has_filters=True, is_active=True))
        return
    await show_main_menu(event, container)


@router.callback_query(Action.filter(F.a == "delete"))
async def ask_delete(callback: CallbackQuery) -> None:
    await callback.answer()
    await respond(callback, texts.DELETE_CONFIRM, keyboards.confirm_delete())


@router.callback_query(Action.filter(F.a == "delete_yes"))
async def delete(callback: CallbackQuery, state: FSMContext, container: ServiceContainer) -> None:
    await callback.answer()
    subscription = await get_main_subscription(container, callback.from_user.id)
    if subscription is not None:
        await container.subscriptions.delete(callback.from_user.id, subscription.id)
    await state.clear()
    await show_main_menu(callback, container, notice=texts.DELETED)
