from aiogram import Bot, Dispatcher

from src.core.config import settings


api_token = settings.tg.API_TOKEN

bot = Bot(token=api_token)
dp = Dispatcher()


async def run_bot():
    print("bot is running...")
    
    try:
        await dp.start_polling(bot)
    finally:
        print("Closing bot session...")
        await bot.session.close()
        print("Bot stopped successfully.")
    
