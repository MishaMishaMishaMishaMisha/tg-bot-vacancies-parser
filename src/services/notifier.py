"""Интерфейс отправки уведомлений и форматирование сообщения.

Сервисы не знают про Telegram: они вызывают Notifier. Реализация для aiogram лежит в
src/tg_bot_interface/telegram_notifier.py.
"""
from __future__ import annotations

import html
import re
from typing import Protocol

from .jobs import Vacancy

SOURCE_TITLES = {"dou": "DOU", "djinni": "Djinni"}
OPEN_LINK_TEXT = "Відкрити вакансію"
MAX_DESCRIPTION_CHARS = 350


class NotifierError(Exception):
    """Не удалось отправить сообщение (временная или неизвестная ошибка): будет повторная попытка."""


class UserBlockedError(NotifierError):
    """Пользователь заблокировал бота или удалил чат: отправлять ему больше нельзя."""


class RetryAfterError(NotifierError):
    """Telegram просит подождать (лимиты)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


class Notifier(Protocol):
    async def send_vacancy(self, telegram_id: int, vacancy: Vacancy) -> None:
        """Отправить вакансию. Должен бросать UserBlockedError, RetryAfterError или NotifierError."""
        ...


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(",.;:- ") + "…"


def format_vacancy(vacancy: Vacancy, *, max_description: int = MAX_DESCRIPTION_CHARS) -> str:
    """Сообщение в формате Telegram HTML (теги <b> и <a>)."""
    lines = [f"<b>{_escape(vacancy.title)}</b>"]

    where = ", ".join(vacancy.locations)
    header = " · ".join(_escape(part) for part in (vacancy.company, where) if part)
    if header:
        lines.append(header)

    details = [part for part in (vacancy.salary, vacancy.category, *vacancy.tags) if part]
    if details:
        lines.append(_escape(" · ".join(details)))

    if vacancy.text:
        lines += ["", _escape(_shorten(vacancy.text, max_description))]

    source = SOURCE_TITLES.get(vacancy.source, vacancy.source)
    link = html.escape(vacancy.url, quote=True)
    lines += ["", f'<a href="{link}">{OPEN_LINK_TEXT}</a> · {_escape(source)}']
    return "\n".join(lines)
