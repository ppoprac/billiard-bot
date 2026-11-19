# middlewares/ban_check.py
from typing import Callable, Dict, Any, Awaitable

from aiogram import types, BaseMiddleware

from database import get_user_profile


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        # /start пропускаем — чтобы забаненный увидел сообщение о бане
        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user = await get_user_profile(event.from_user.id)
        if user and user['is_banned']:
            await event.answer("🚫 Вы заблокированы. Доступ к командам закрыт.")
            return

        return await handler(event, data)
