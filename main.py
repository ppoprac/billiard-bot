import logging
from typing import Callable, Dict, Any, Awaitable
from aiohttp import web

from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BOT_TOKEN, PORT, WEBHOOK_PATH, WEBHOOK_URL
from database import init_db, close_pool, get_user_profile
from handlers import (
    common_router,
    rating_router,
    matches_router,
    challenges_router,
    admin_router,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user = await get_user_profile(event.from_user.id)
        if user and user['is_banned']:
            await event.answer("🚫 Вы заблокированы. Доступ к командам закрыт.")
            return

        return await handler(event, data)


dp.message.outer_middleware(BanCheckMiddleware())

dp.include_router(common_router)
dp.include_router(rating_router)
dp.include_router(matches_router)
dp.include_router(challenges_router)
dp.include_router(admin_router)


async def on_startup(bot: Bot):
    await init_db()
    logging.info("База данных инициализирована")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    logging.info("Закрываем пул соединений с БД...")
    await close_pool()


async def healthcheck(request: web.Request):
    return web.Response(text="OK")


def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", healthcheck)
    app.router.add_get("/healthcheck", healthcheck)
    setup_application(app, dp, bot=bot)
    logging.info(f"Запуск web-сервера на 0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
