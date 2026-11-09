"""Шаги редактора фильтров, общие для обработчиков кнопок и текстового ввода."""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.services import ServiceContainer, SubscriptionFilters

from . import screens, texts
from .draft import load_draft
from .common import Ui, english_labels

SMALL_FIELDS = ("sources", "experiences", "employments", "regions", "english_levels")
LIST_FIELDS = ("categories", "cities")


async def small_options(container: ServiceContainer, field: str) -> list[tuple[str, str]]:
    """Варианты короткого списка: пары (значение, подпись)."""
    if field == "sources":
        return [(name, texts.SOURCE_TITLES.get(name, name)) for name in container.filters.source_names]
    if field == "experiences":
        return list(texts.EXPERIENCE_LABELS.items())
    if field == "employments":
        return list(texts.EMPLOYMENT_LABELS.items())
    if field == "regions":
        return list(texts.REGION_LABELS.items())
    if field == "english_levels":
        catalog = await container.filters.get_catalog()
        return [(choice.value, choice.label) for choice in catalog.english_levels]
    raise ValueError(f"Неизвестное поле: {field}")


async def open_list(state: FSMContext, container: ServiceContainer, field: str) -> None:
    """Загрузить длинный список (категории или города выбранных сайтов) и сбросить поиск и страницу."""
    draft = await load_draft(state)
    catalog = await container.filters.get_catalog(draft.sources if draft else None)
    items = catalog.categories if field == "categories" else catalog.cities
    await state.update_data(list_items=items, list_field=field, list_query="", list_page=0)


async def render_field(ui: Ui, state: FSMContext, container: ServiceContainer, field: str) -> None:
    """Показать экран выбора для поля: короткий список или длинный список с поиском."""
    draft = await load_draft(state)
    if field in SMALL_FIELDS:
        text, markup = screens.small_screen(field, draft, await small_options(container, field))
    else:
        data = await state.get_data()
        text, markup = screens.list_screen(
            field, draft, data.get("list_items", []), data.get("list_query", ""), data.get("list_page", 0)
        )
    await ui.render(text, markup)


async def show_editor(ui: Ui, state: FSMContext, container: ServiceContainer) -> None:
    draft = await load_draft(state)
    text, markup = screens.editor_screen(draft, await english_labels(container))
    await ui.render(text, markup)


async def session_or_expire(
    callback: CallbackQuery, state: FSMContext
) -> tuple[Ui, SubscriptionFilters] | None:
    """Окно и черновик текущей сессии. Если их нет (например, бот перезапускался), предупреждает пользователя."""
    ui = Ui.from_callback(callback)
    draft = await load_draft(state)
    if ui is None or draft is None:
        await state.clear()
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return None
    return ui, draft
