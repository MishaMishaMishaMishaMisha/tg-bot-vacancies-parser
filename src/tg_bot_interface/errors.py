"""Обработка ошибок: пользователь видит понятное сообщение, подробности уходят в лог."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

from src.services import UserNotFoundError

from . import texts

log = logging.getLogger(__name__)

router = Router(name="errors")


async def _tell_user(event: ErrorEvent, text: str) -> None:
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(text, show_alert=True)
        elif update.message is not None:
            await update.message.answer(text)
    except Exception:   # сообщить об ошибке не вышло: не маскируем исходную ошибку
        log.debug("Не удалось сообщить пользователю об ошибке", exc_info=True)


@router.error(ExceptionTypeFilter(UserNotFoundError))
async def user_not_registered(event: ErrorEvent) -> None:
    """Например, базу очистили, а у пользователя остались старые кнопки."""
    await _tell_user(event, texts.NOT_REGISTERED)


@router.error()
async def unexpected_error(event: ErrorEvent) -> None:
    log.error("Необработанная ошибка в обработчике", exc_info=event.exception)
    await _tell_user(event, texts.GENERIC_ERROR)
