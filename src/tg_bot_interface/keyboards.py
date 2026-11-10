from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services import SubscriptionFilters

from . import texts
from .callbacks import Action

PAGE_SIZE = 12   # элементов на странице длинного списка: 2 колонки по 6 строк


def _btn(text: str, **callback) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=Action(**callback).pack())


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _short(text: str, limit: int = 30) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _field_label(field: str, count: int = 0) -> str:
    emoji, title = texts.FIELD_META[field]
    return f"{emoji} {title}" + (f" ({count})" if count else "")



def main_menu(has_filters: bool, is_active: bool = True) -> InlineKeyboardMarkup:
    if not has_filters:
        return _markup([[_btn(texts.BTN_SETUP, a="edit")], [_btn(texts.BTN_HELP, a="help")]])
    toggle = _btn(texts.BTN_PAUSE, a="pause") if is_active else _btn(texts.BTN_RESUME, a="resume")
    return _markup([
        [_btn(texts.BTN_SHOW, a="show"), _btn(texts.BTN_EDIT, a="edit")],
        [toggle],
        [_btn(texts.BTN_DELETE, a="delete")],
        [_btn(texts.BTN_HELP, a="help")],
    ])


def back_to_menu() -> InlineKeyboardMarkup:
    return _markup([[_btn(texts.BTN_MENU, a="menu")]])


def my_filters(is_active: bool) -> InlineKeyboardMarkup:
    toggle = _btn(texts.BTN_PAUSE, a="pause") if is_active else _btn(texts.BTN_RESUME, a="resume")
    return _markup([[_btn(texts.BTN_EDIT, a="edit")], [toggle], [_btn(texts.BTN_MENU, a="menu")]])


def confirm_delete() -> InlineKeyboardMarkup:
    return _markup([[_btn(texts.BTN_YES_DELETE, a="delete_yes")], [_btn(texts.BTN_CANCEL, a="menu")]])


def save_failed() -> InlineKeyboardMarkup:
    return _markup([[_btn(texts.BTN_BACK_TO_FILTERS, a="screen", f="editor")], [_btn(texts.BTN_MENU, a="menu")]])



def editor(filters: SubscriptionFilters) -> InlineKeyboardMarkup:
    def open_screen(field: str, count: int = 0) -> InlineKeyboardButton:
        return _btn(_field_label(field, count), a="screen", f=field)

    relocation = f"{_field_label('relocation')}: {'так' if filters.relocation else 'ні'}"
    return _markup([
        [open_screen("sources", len(filters.sources))],
        [open_screen("categories", len(filters.categories))],
        [open_screen("experiences", len(filters.experiences)), open_screen("employments", len(filters.employments))],
        [open_screen("cities", len(filters.cities)), open_screen("regions", len(filters.regions))],
        [open_screen("english_levels", len(filters.english_levels)), open_screen("min_salary")],
        [open_screen("keywords", len(filters.keywords)), open_screen("exclude_keywords", len(filters.exclude_keywords))],
        [_btn(relocation, a="toggle", f="relocation")],
        [_btn(texts.BTN_SAVE, a="save"), _btn(texts.BTN_CANCEL, a="cancel")],
    ])


def toggles(
    field: str, options: list[tuple[str, str]], selected: set[str], *, clearable: bool = True
) -> InlineKeyboardMarkup:
    """Короткий список с переключателями: по кнопке на вариант."""
    rows = [
        [_btn(f"{'✅' if value in selected else '⬜️'} {label}", a="toggle", f=field, v=value)]
        for value, label in options
    ]
    controls = []
    if clearable:
        controls.append(_btn(texts.BTN_CLEAR, a="clear", f=field))
    controls.append(_btn(texts.BTN_DONE, a="screen", f="editor"))
    rows.append(controls)
    return _markup(rows)


def paged_list(
    field: str,
    entries: list[tuple[int, str]],
    selected_keys: set[str],
    page: int,
    pages: int,
    has_query: bool,
) -> InlineKeyboardMarkup:
    """Длинный список (категории, города): две колонки, страницы, поиск.

    entries: пары (номер элемента в сохранённом списке, название); в callback уходит только номер.
    """
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, label in entries:
        mark = "✅ " if label.casefold() in selected_keys else ""
        row.append(_btn(_short(mark + label), a="pick", f=field, v=str(index)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if pages > 1:
        nav = []
        if page > 0:
            nav.append(_btn("◀️", a="page", f=field, p=page - 1))
        nav.append(_btn(f"{page + 1}/{pages}", a="noop"))
        if page < pages - 1:
            nav.append(_btn("▶️", a="page", f=field, p=page + 1))
        rows.append(nav)

    tools = [_btn(texts.BTN_SEARCH, a="search", f=field)]
    if has_query:
        tools.append(_btn(texts.BTN_RESET_SEARCH, a="clear_search", f=field))
    rows.append(tools)
    rows.append([_btn(texts.BTN_CLEAR, a="clear", f=field), _btn(texts.BTN_DONE, a="screen", f="editor")])
    return _markup(rows)


def prompt(back_to: str, clear_field: str | None = None, *, keep_list: bool = False) -> InlineKeyboardMarkup:
    """Экран, где бот ждёт текст. back_to: экран, на который ведёт «Назад».

    keep_list=True: вернуться к списку, не сбрасывая поиск и страницу.
    """
    row = []
    if clear_field:
        row.append(_btn(texts.BTN_CLEAR, a="clear", f=clear_field))
    row.append(_btn(texts.BTN_BACK, a="screen", f=back_to, v="keep" if keep_list else ""))
    return _markup([row])
