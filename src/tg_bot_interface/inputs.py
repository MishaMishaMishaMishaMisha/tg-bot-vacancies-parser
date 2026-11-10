from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.services import ServiceContainer, SubscriptionFilters

from . import keyboards, texts
from .draft import load_draft, save_draft
from .states import Editor
from .common import Ui
from .flow import LIST_FIELDS, render_field, show_editor

router = Router(name="inputs")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# Команды (/menu, /cancel...) в текстовый ввод не попадают: ими занимается роутер start.


async def _session(message: Message, state: FSMContext) -> tuple[Ui, SubscriptionFilters] | None:
    ui = await Ui.from_state(message.bot, state)
    draft = await load_draft(state)
    if ui is None or draft is None:
        await state.clear()
        await message.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.back_to_menu())
        return None
    return ui, draft


async def _delete_quietly(message: Message) -> None:
    """Убрать сообщение пользователя, чтобы чат не засорялся (если нельзя, не страшно)."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


def parse_words(text: str) -> list[str]:
    """«Django, flask; FastAPI» -> ['Django', 'flask', 'FastAPI'] без пустых и повторяющихся слов."""
    words: dict[str, str] = {}
    for part in re.split(r"[,;\n]+", text):
        word = part.strip()
        if word:
            words.setdefault(word.casefold(), word)
    return list(words.values())


@router.message(Editor.waiting_search, F.text, ~F.text.startswith("/"))
async def input_search(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    session = await _session(message, state)
    if session is None:
        return
    ui, _ = session
    field = (await state.get_data()).get("list_field")
    if field not in LIST_FIELDS:
        await state.clear()
        await message.answer(texts.SESSION_EXPIRED, reply_markup=keyboards.back_to_menu())
        return

    await state.update_data(list_query=message.text.strip(), list_page=0)
    await state.set_state(None)
    await _delete_quietly(message)
    await render_field(ui, state, container, field)


@router.message(Editor.waiting_salary, F.text, ~F.text.startswith("/"))
async def input_salary(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    session = await _session(message, state)
    if session is None:
        return
    ui, draft = session
    limit = container.settings.max_salary
    text = message.text.strip()
    if not (text.isascii() and text.isdigit()) or int(text) > limit:
        await message.answer(texts.INPUT_BAD_SALARY.format(max_salary=limit))
        return

    draft.min_salary = int(text) or None   # 0 убирает фильтр
    await save_draft(state, draft)
    await state.set_state(None)
    await _delete_quietly(message)
    await show_editor(ui, state, container)


async def _store_words(message: Message, state: FSMContext, container: ServiceContainer, field: str) -> None:
    session = await _session(message, state)
    if session is None:
        return
    ui, draft = session
    words = parse_words(message.text)
    settings = container.settings
    if not words:
        await message.answer(texts.INPUT_EMPTY)
        return
    if len(words) > settings.max_keywords:
        await message.answer(texts.INPUT_TOO_MANY_WORDS.format(limit=settings.max_keywords))
        return
    if any(len(word) > settings.max_keyword_length for word in words):
        await message.answer(texts.INPUT_WORD_TOO_LONG.format(limit=settings.max_keyword_length))
        return

    setattr(draft, field, words)
    await save_draft(state, draft)
    await state.set_state(None)
    await _delete_quietly(message)
    await show_editor(ui, state, container)


@router.message(Editor.waiting_keywords, F.text, ~F.text.startswith("/"))
async def input_keywords(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    await _store_words(message, state, container, "keywords")


@router.message(Editor.waiting_exclude, F.text, ~F.text.startswith("/"))
async def input_exclude(message: Message, state: FSMContext, container: ServiceContainer) -> None:
    await _store_words(message, state, container, "exclude_keywords")
