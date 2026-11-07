"""Реализация Notifier для aiogram 3: отправляет вакансию сообщением в чат пользователя."""
from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import LinkPreviewOptions

from src.services.jobs import Vacancy
from src.services.notifier import NotifierError, RetryAfterError, UserBlockedError, format_vacancy

# Эти ошибки BadRequest означают, что написать пользователю невозможно (удалил чат, аккаунт и т.п.)
_DEAD_CHAT_MARKERS = ("chat not found", "user is deactivated", "bot was blocked", "peer_id_invalid")


class TelegramNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_vacancy(self, telegram_id: int, vacancy: Vacancy) -> None:
        try:
            await self._bot.send_message(
                chat_id=telegram_id,
                text=format_vacancy(vacancy),
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramForbiddenError as exc:       # пользователь заблокировал бота
            raise UserBlockedError(str(exc)) from exc
        except TelegramRetryAfter as exc:           # слишком частые сообщения
            raise RetryAfterError(exc.retry_after) from exc
        except TelegramBadRequest as exc:
            if any(marker in str(exc).lower() for marker in _DEAD_CHAT_MARKERS):
                raise UserBlockedError(str(exc)) from exc
            raise NotifierError(str(exc)) from exc
        except TelegramAPIError as exc:             # сеть, 5xx и прочее
            raise NotifierError(str(exc)) from exc
