"""Экраны бота: пара (текст, клавиатура). Чистые функции: данные приходят аргументами."""
from __future__ import annotations

import math

from aiogram.types import InlineKeyboardMarkup

from src.services import SubscriptionFilters, SubscriptionInfo

from . import keyboards, texts
from .texts import esc


def _join(values, labeler=lambda v: v, limit: int = 8) -> str:
    shown = [esc(labeler(v)) for v in list(values)[:limit]]
    rest = len(values) - limit
    return ", ".join(shown) + (f" … ще {rest}" if rest > 0 else "")


def _line(field: str, value: str) -> str:
    emoji, title = texts.FIELD_META[field]
    return f"{emoji} <b>{title}:</b> {value}"


def format_filters(filters: SubscriptionFilters, english_labels: dict[str, str] | None = None) -> str:
    """Выбранные источники и фильтры по строке на каждый."""
    english = english_labels or {}
    lines = [
        _line("sources", _join(filters.sources, lambda s: texts.SOURCE_TITLES.get(s, s)) or texts.NOT_CHOSEN),
        _line("categories", _join(filters.categories) or texts.NOT_CHOSEN),
        _line("experiences", _join(filters.experiences, lambda v: texts.EXPERIENCE_LABELS.get(v, v)) or texts.ANY),
        _line("employments", _join(filters.employments, lambda v: texts.EMPLOYMENT_LABELS.get(v, v)) or texts.ANY),
        _line("cities", _join(filters.cities) or texts.ANY),
        _line("regions", _join(filters.regions, lambda v: texts.REGION_LABELS.get(v, v)) or texts.ANY),
        _line("english_levels", _join(filters.english_levels, lambda v: english.get(v, v)) or texts.ANY),
        _line("min_salary", f"від ${filters.min_salary}" if filters.min_salary else texts.ANY),
    ]
    if filters.relocation:
        lines.append(_line("relocation", "так"))
    lines.append(_line("keywords", _join(filters.keywords) or "—"))
    lines.append(_line("exclude_keywords", _join(filters.exclude_keywords) or "—"))
    return "\n".join(lines)


# ------------------------------------------------------------------ главное меню и «Мои фильтры»

def main_menu_screen(subscription: SubscriptionInfo | None) -> tuple[str, InlineKeyboardMarkup]:
    if subscription is None:
        return texts.MENU_NO_FILTERS, keyboards.main_menu(has_filters=False)
    status = texts.STATUS_ACTIVE if subscription.is_active else texts.STATUS_PAUSED
    return f"🏠 <b>Головне меню</b>\n\n{status}", keyboards.main_menu(True, subscription.is_active)


def my_filters_screen(
    subscription: SubscriptionInfo | None, english_labels: dict[str, str] | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    if subscription is None:
        return texts.NO_FILTERS, keyboards.main_menu(has_filters=False)
    parts = [
        texts.FILTERS_HEADER,
        texts.STATUS_ACTIVE if subscription.is_active else texts.STATUS_PAUSED,
    ]
    if subscription.is_active and not subscription.is_seeded:
        parts.append(texts.STATUS_PENDING)
    parts += ["", format_filters(subscription.filters, english_labels)]
    return "\n".join(parts), keyboards.my_filters(subscription.is_active)


# ------------------------------------------------------------------ редактор

def editor_screen(
    filters: SubscriptionFilters, english_labels: dict[str, str] | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    text = f"{texts.EDITOR_HEADER}\n\n{format_filters(filters, english_labels)}\n\n{texts.EDITOR_HINT}"
    return text, keyboards.editor(filters)


def small_screen(
    field: str, filters: SubscriptionFilters, options: list[tuple[str, str]]
) -> tuple[str, InlineKeyboardMarkup]:
    emoji, title = texts.FIELD_META[field]
    text = f"{emoji} <b>{title}</b>\n\n{texts.SCREEN_INTRO[field]}"
    selected = set(getattr(filters, field))
    return text, keyboards.toggles(field, options, selected, clearable=field != "sources")


def list_screen(
    field: str, filters: SubscriptionFilters, items: list[str], query: str, page: int
) -> tuple[str, InlineKeyboardMarkup]:
    emoji, title = texts.FIELD_META[field]
    needle = query.strip().casefold()
    matches = [(i, item) for i, item in enumerate(items) if not needle or needle in item.casefold()]
    pages = max(1, math.ceil(len(matches) / keyboards.PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    chunk = matches[page * keyboards.PAGE_SIZE:(page + 1) * keyboards.PAGE_SIZE]

    selected = getattr(filters, field)
    lines = [
        f"{emoji} <b>{title}</b>",
        "",
        texts.SCREEN_INTRO[field],
        "",
        f"Обрано ({len(selected)}): {_join(selected, limit=10) or '—'}",
    ]
    if needle:
        lines.append(f"Пошук «{esc(query.strip())}»: знайдено {len(matches)}")
    if not matches:
        lines.append("Нічого не знайдено. Спробуйте інший запит.")

    markup = keyboards.paged_list(
        field, chunk, {s.casefold() for s in selected}, page, pages, has_query=bool(needle)
    )
    return "\n".join(lines), markup


def prompt_screen(
    field: str, filters: SubscriptionFilters, *, max_salary: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран ввода текста: зарплата, ключевые слова или исключаемые слова."""
    if field == "min_salary":
        current = f"від ${filters.min_salary}" if filters.min_salary else "не задано"
        return texts.PROMPT_SALARY.format(max_salary=max_salary, current=current), keyboards.prompt("editor", field)
    template = texts.PROMPT_KEYWORDS if field == "keywords" else texts.PROMPT_EXCLUDE
    words = _join(getattr(filters, field), limit=15) or "немає"
    return template.format(current=words), keyboards.prompt("editor", field)


def search_prompt_screen(list_field: str) -> tuple[str, InlineKeyboardMarkup]:
    return texts.PROMPT_SEARCH, keyboards.prompt(list_field, keep_list=True)
