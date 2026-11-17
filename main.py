import os
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from database import (
    init_db,
    get_or_create_user,
    get_user_profile,
    get_top_players,
    get_all_users,
    record_match,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

if not BOT_TOKEN:
    raise RuntimeError("Переменная BOT_TOKEN не установлена")
if not BASE_URL:
    raise RuntimeError("Переменная RENDER_EXTERNAL_URL не установлена")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Не указан"
    full_name = message.from_user.full_name

    user = await get_or_create_user(user_id, username, full_name)

    await message.answer(
        f"Привет, {full_name}! 🎱\n\n"
        f"Я твой бильярдный помощник в Могилёве.\n\n"
        f"📊 Твой текущий рейтинг: <b>{user[3]}</b> ELO\n"
        f"🎮 Сыграно игр: {user[4]}\n"
        f"🏆 Побед: {user[5]}\n\n"
        f"Скоро здесь появится:\n"
        f"🏆 Лестница вызовов\n"
        f"📊 Турнирные сетки\n"
        f"📍 Поиск соперников\n\n"
        f"👇 Быстрые команды:\n"
        f"/match — Записать поражение\n"
        f"/top — Таблица рейтинга\n"
        f"/profile — Твоя статистика",
        parse_mode="HTML",
    )


@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = await get_user_profile(message.from_user.id)

    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start")
        return

    winrate = (user[5] / user[4] * 100) if user[4] > 0 else 0

    await message.answer(
        f"📊 <b>Твой профиль</b>\n\n"
        f"👤 Имя: {user[2]}\n"
        f"📈 Рейтинг ELO: <b>{user[3]}</b>\n"
        f"🎮 Сыграно игр: {user[4]}\n"
        f"🏆 Побед: {user[5]}\n"
        f"📉 Процент побед: {winrate:.1f}%\n"
        f"📅 Регистрация: {user[6]}",
        parse_mode="HTML",
    )


@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    players = await get_top_players(10)

    if not players:
        await message.answer("Пока нет игроков в рейтинге")
        return

    text = "🏆 <b>Топ-10 игроков</b>\n\n"
    for i, player in enumerate(players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {player[2]} — <b>{player[3]}</b> ELO\n"

    await message.answer(text, parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Список команд</b>\n\n"
        "/start — Начать работу с ботом\n"
        "/profile — Твой профиль и статистика\n"
        "/top — Топ-10 игроков по рейтингу\n"
        "/help — Эта справка\n\n"
        "🚧 В разработке:\n"
        "/challenge — Вызвать соперника\n"
        "/result — Ввести результат матча\n"
        "/ladder — Таблица лестницы",
        parse_mode="HTML",
    )


@dp.message(Command("match"))
async def cmd_match(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start, чтобы зарегистрироваться")
        return

    players = await get_all_users(30)
    players = [p for p in players if p[0] != message.from_user.id]

    if not players:
        await message.answer("Пока не с кем играть. Попроси друга написать боту /start")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for p in players:
        name = p[2] if p[2] else (p[1] if p[1] else "Аноним")
        btn = InlineKeyboardButton(
            text=f"🎱 {name} ({p[3]} ELO)",
            callback_data=f"select_opp_{p[0]}",
        )
        keyboard.inline_keyboard.append([btn])

    await message.answer(
        "🎱 <b>Выбери соперника, которому ты проиграл:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("select_opp_"))
async def process_select_opponent(callback: CallbackQuery):
    opponent_id = int(callback.data.removeprefix("select_opp_"))
    loser_id = callback.from_user.id

    loser = await get_user_profile(loser_id)
    winner = await get_user_profile(opponent_id)

    if not loser or not winner:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    loser_name = loser[2] or "Ты"
    winner_name = winner[2] or "Соперник"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, я проиграл",
            callback_data=f"confirm_lose_{opponent_id}",
        )]
    ])

    text = f"Ты ({loser_name}) проиграл {winner_name}?\nНажми кнопку для подтверждения."
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_lose_"))
async def process_confirm_lose(callback: CallbackQuery):
    winner_id = int(callback.data.removeprefix("confirm_lose_"))
    loser_id = callback.from_user.id

    if winner_id == loser_id:
        await callback.answer("Нельзя записать матч с самим собой", show_alert=True)
        return

    success, new_winner_elo, new_loser_elo = await record_match(winner_id, loser_id)

    if success:
        text = (
            f"✅ <b>Результат честно записан!</b>\n\n"
            f"📉 Твой новый рейтинг: <b>{new_loser_elo}</b> ELO\n"
            f"🏆 Рейтинг соперника: <b>{new_winner_elo}</b> ELO\n\n"
            f"Посмотри обновленный топ командой /top"
        )
        await callback.message.edit_text(text, parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ Ошибка при записи матча.")

    await callback.answer()


async def on_startup(bot: Bot):
    await init_db()
    logging.info("База данных инициализирована")
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")


async def healthcheck(request: web.Request):
    return web.Response(text="OK")


def main():
    dp.startup.register(on_startup)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/", healthcheck)
    app.router.add_get("/healthcheck", healthcheck)
    setup_application(app, dp, bot=bot)

    logging.info(f"Запуск web-сервера на 0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
