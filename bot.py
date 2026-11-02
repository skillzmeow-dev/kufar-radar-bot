import asyncio
import logging
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import Database
from handlers import router
from admin import admin_router
from watcher import KufarWatcher
from channel_poster import ChannelAutoPoster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("kufar_bot")


async def handle_health(request):
    return web.json_response({
        "status": "ok",
        "service": "kufar_radar_by_bot",
        "channel": "@minsk_rent_live",
    })


async def start_health_server(port: int):
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/ping", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:%d for Render/Cloud", port)
    return runner


async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        logger.error(
            "❌ ОШИБКА: Токен бота не найден! Укажите BOT_TOKEN в файле .env (получите у @BotFather)"
        )
        print("\n" + "=" * 60)
        print("ВНИМАНИЕ: Для работы бота нужен Telegram токен!")
        print("1. Откройте @BotFather в Telegram и создайте бота (/newbot)")
        print("2. Вставьте полученный токен в файл .env в папке:")
        print(f"   {config.BASE_DIR / '.env'}")
        print("3. Запустите бота заново командой: python bot.py")
        print("=" * 60 + "\n")
        return

    # Инициализация базы данных
    db = Database(config.DB_PATH)
    await db.init_db()

    # Инициализация бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Внедрение зависимостей в хэндлеры
    dp["db"] = db

    # Регистрация роутеров
    dp.include_router(admin_router)
    dp.include_router(router)

    # Инициализация и запуск фонового чекера объявлений
    watcher = KufarWatcher(bot=bot, db=db, poll_interval=config.POLL_INTERVAL)
    watcher_task = asyncio.create_task(watcher.start())

    # Инициализация и запуск автопостера в канал
    channel_poster = ChannelAutoPoster(
        bot=bot,
        db=db,
        channel_username=config.CHANNEL_USERNAME,
        poll_interval=35,
    )
    channel_task = asyncio.create_task(channel_poster.start())

    # Запуск легковесного веб-сервера для Render / UptimeRobot
    port = int(os.getenv("PORT", "8080"))
    health_runner = await start_health_server(port)

    logger.info("Бот успешно запущен и готов к работе!")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        watcher.stop()
        channel_poster.stop()
        watcher_task.cancel()
        channel_task.cancel()
        if health_runner:
            await health_runner.cleanup()
        await bot.session.close()
        await watcher.client.close()
        await channel_poster.aggregator.close()
        await channel_poster.kufar_client.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа завершена пользователем.")
