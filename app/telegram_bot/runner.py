import asyncio
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    from app.telegram_bot.handlers import router
    dp.include_router(router)

    await bot.delete_webhook()
    logger.info("Starting bot polling...")

    # Запускаем поллинг в фоновой задаче
    polling_task = asyncio.create_task(dp.start_polling(bot))

    try:
        yield
    finally:
        # Останавливаем бота при завершении приложения
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot stopped")