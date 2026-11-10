import asyncio
import logging

from src.core.config import settings, ServiceSettings
from src.db.db_connection import async_engine
from src.services import ServiceContainer
from src.tg_bot_interface.bot import create_bot, create_dispatcher
from src.tg_bot_interface.telegram_notifier import TelegramNotifier


def get_bot_token() -> str:
    return settings.tg.API_TOKEN

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    bot = create_bot(get_bot_token())
    container = ServiceContainer(
        notifier=TelegramNotifier(bot),
        settings=ServiceSettings(),
    )
    dispatcher = create_dispatcher(container)

    await container.start()           # фоновый опрос сайтов и отправка уведомлений
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await container.stop()
        await bot.session.close()
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
