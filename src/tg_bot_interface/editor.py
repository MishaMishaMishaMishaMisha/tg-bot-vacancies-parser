from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.services import (
    ServiceContainer,
    SubscriptionFilters,
    SubscriptionNotFoundError,
    ValidationError,
)

from . import keyboards, screens, texts
from .callbacks import Action
from .draft import save_draft
from .states import Editor
from .common import Ui, english_labels, get_main_subscription, show_main_menu
from .flow import LIST_FIELDS, SMALL_FIELDS, open_list, render_field, session_or_expire, show_editor, small_options

router = Router(name="editor")

# поле фильтра -> состояние, в котором бот ждёт текст
INPUT_STATES = {
    "min_salary": Editor.waiting_salary,
    "keywords": Editor.waiting_keywords,
    "exclude_keywords": Editor.waiting_exclude,
}


@router.callback_query(Action.filter(F.a == "edit"))
async def start_editing(callback: CallbackQuery, state: FSMContext, container: ServiceContainer) -> None:
    """Открыть редактор: с сохранёнными фильтрами или с пустыми (все сайты выбраны сразу)."""
    await callback.answer()
    ui = Ui.from_callback(callback)
    if ui is None:
        return
    subscription = await get_main_subscription(container, callback.from_user.id)
    if subscription is not None:
        draft, subscription_id = subscription.filters, str(subscription.id)
    else:
        draft, subscription_id = SubscriptionFilters(sources=list(container.filters.source_names)), None

    await state.clear()
    await state.update_data(subscription_id=subscription_id)
    await ui.remember(state)
    await save_draft(state, draft)
    await show_editor(ui, state, container)


@router.callback_query(Action.filter(F.a == "screen"))
async def open_screen(
    callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer
) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, draft = session
    await callback.answer()
    await state.set_state(None)   # любая навигация выводит из режима ввода текста

    field = callback_data.f
    if field == "editor":
        await show_editor(ui, state, container)
    elif field in SMALL_FIELDS:
        await render_field(ui, state, container, field)
    elif field in LIST_FIELDS:
        data = await state.get_data()
        keep = callback_data.v == "keep" and data.get("list_field") == field and data.get("list_items")
        if not keep:   # «Назад» из поиска возвращает список как был, остальные входы начинают заново
            await open_list(state, container, field)
        await render_field(ui, state, container, field)
    elif field in INPUT_STATES:
        await state.set_state(INPUT_STATES[field])
        text, markup = screens.prompt_screen(field, draft, max_salary=container.settings.max_salary)
        await ui.render(text, markup)


@router.callback_query(Action.filter(F.a == "toggle"))
async def toggle(
    callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer
) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, draft = session
    await callback.answer()
    field, value = callback_data.f, callback_data.v

    if field == "relocation":
        draft.relocation = not draft.relocation
        await save_draft(state, draft)
        await show_editor(ui, state, container)
        return
    if field not in SMALL_FIELDS or value not in {v for v, _ in await small_options(container, field)}:
        return   # неизвестное поле или значение: игнорируем

    current = getattr(draft, field)
    setattr(draft, field, [x for x in current if x != value] if value in current else [*current, value])
    await save_draft(state, draft)
    await render_field(ui, state, container, field)


@router.callback_query(Action.filter(F.a == "pick"))
async def pick(callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer) -> None:
    """Выбрать или снять элемент длинного списка (в callback только его номер)."""
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, draft = session
    await callback.answer()
    field = callback_data.f
    items = (await state.get_data()).get("list_items") or []
    if field not in LIST_FIELDS or not callback_data.v.isdigit() or int(callback_data.v) >= len(items):
        return

    name = items[int(callback_data.v)]
    current = getattr(draft, field)
    if name.casefold() in {c.casefold() for c in current}:
        setattr(draft, field, [c for c in current if c.casefold() != name.casefold()])
    else:
        setattr(draft, field, [*current, name])
    await save_draft(state, draft)
    await render_field(ui, state, container, field)


@router.callback_query(Action.filter(F.a == "page"))
async def change_page(
    callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer
) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, _ = session
    await callback.answer()
    if callback_data.f in LIST_FIELDS:
        await state.update_data(list_page=callback_data.p)
        await render_field(ui, state, container, callback_data.f)


@router.callback_query(Action.filter(F.a == "search"))
async def start_search(callback: CallbackQuery, callback_data: Action, state: FSMContext) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, _ = session
    await callback.answer()
    if callback_data.f not in LIST_FIELDS:
        return
    await state.set_state(Editor.waiting_search)
    await state.update_data(list_field=callback_data.f)
    text, markup = screens.search_prompt_screen(callback_data.f)
    await ui.render(text, markup)


@router.callback_query(Action.filter(F.a == "clear_search"))
async def clear_search(
    callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer
) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, _ = session
    await callback.answer()
    if callback_data.f in LIST_FIELDS:
        await state.update_data(list_query="", list_page=0)
        await render_field(ui, state, container, callback_data.f)


@router.callback_query(Action.filter(F.a == "clear"))
async def clear(
    callback: CallbackQuery, callback_data: Action, state: FSMContext, container: ServiceContainer
) -> None:
    """Очистить фильтр. После очистки значения из текстового экрана возвращаемся в редактор."""
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, draft = session
    await callback.answer()
    field = callback_data.f

    if field in LIST_FIELDS or (field in SMALL_FIELDS and field != "sources"):
        setattr(draft, field, [])
        await save_draft(state, draft)
        await render_field(ui, state, container, field)
    elif field == "min_salary" or field in ("keywords", "exclude_keywords"):
        if field == "min_salary":
            draft.min_salary = None
        else:
            setattr(draft, field, [])
        await save_draft(state, draft)
        await state.set_state(None)
        await show_editor(ui, state, container)


@router.callback_query(Action.filter(F.a == "cancel"))
async def cancel(callback: CallbackQuery, state: FSMContext, container: ServiceContainer) -> None:
    await callback.answer()
    await state.clear()
    await show_main_menu(callback, container)


@router.callback_query(Action.filter(F.a == "save"))
async def save(callback: CallbackQuery, state: FSMContext, container: ServiceContainer) -> None:
    session = await session_or_expire(callback, state)
    if session is None:
        return
    ui, draft = session

    # Минимальные требования проверяем сразу, не обращаясь к сервисам.
    if not draft.sources:
        await callback.answer(texts.ALERT_NO_SOURCES, show_alert=True)
        return
    if not draft.categories:
        await callback.answer(texts.ALERT_NO_CATEGORIES, show_alert=True)
        return

    await callback.answer()
    await ui.render(texts.SAVING)   # создание подписки включает засев: сайты опрашиваются, это занимает время

    telegram_id = callback.from_user.id
    subscription_id = (await state.get_data()).get("subscription_id")
    try:
        if subscription_id:
            try:
                result = await container.subscriptions.update(telegram_id, UUID(subscription_id), draft)
            except SubscriptionNotFoundError:   # подписку успели удалить: создаём заново
                result = await container.subscriptions.create(telegram_id, draft)
        else:
            result = await container.subscriptions.create(telegram_id, draft)
    except ValidationError as exc:
        details = texts.warning_lines(exc.warnings) or texts.SAVE_FAILED_HINT
        await ui.render(f"{texts.SAVE_FAILED}\n\n{details}", keyboards.save_failed())
        return

    await state.clear()
    subscription = result.subscription
    parts = [texts.SAVED, "", screens.format_filters(subscription.filters, await english_labels(container))]
    if not subscription.is_active:
        parts += ["", texts.STATUS_PAUSED]
    elif not subscription.is_seeded:
        parts += ["", texts.STATUS_PENDING]
    warnings = texts.warning_lines(result.warnings)
    if warnings:
        parts += ["", warnings]
    await ui.render("\n".join(parts), keyboards.main_menu(has_filters=True, is_active=subscription.is_active))
