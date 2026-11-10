"""Создание бота и диспетчера."""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from src.services import ServiceContainer

from . import texts
#from .handlers import router
from . import router


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _on_startup(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command=name, description=desc) for name, desc in texts.COMMANDS])


def create_dispatcher(container: ServiceContainer) -> Dispatcher:

    dispatcher = Dispatcher(storage=MemoryStorage(), container=container)
    dispatcher.include_router(router)
    dispatcher.startup.register(_on_startup)
    return dispatcher
