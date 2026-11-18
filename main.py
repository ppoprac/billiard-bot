import os
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from database import (
    init_db,
    close_pool,
    get_or_create_user,
    get_user_profile,
    get_all_users,
    get_players_above,
    get_total_players,
    get_user_rank,
    get_players_upto,
    record_match,
    get_match_history,
    get_h2h_stats,
    create_challenge,
    get_challenge,
    update_challenge_status,
    create_pending_result,
    get_pending_result,
    delete_pending_result,
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


def display_name(row):
    return row['full_name'] or row['username'] or "Аноним"


# ================== БАЗОВЫЕ КОМАНДЫ ==================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username or "Не указан",
        message.from_user.full_name,
    )
    await message.answer(
        f"Привет, {message.from_user.full_name}! 🎱\n\n"
        f"📊 Твой рейтинг: <b>{user['elo_rating']}</b> ELO\n"
        f"🎮 Игр: {user['games_played']} | 🏆 Побед: {user['wins']}\n\n"
        f"👇 Команды:\n"
        f"/match — Записать поражение\n"
        f"/result — Записать победу\n"
        f"/challenge — Вызвать соперника\n"
        f"/top — Таблица рейтинга\n"
        f"/profile — Твоя статистика\n"
        f"/history — История матчей\n"
        f"/h2h — Личные встречи\n"
        f"/help — Все команды",
        parse_mode="HTML",
    )


@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    winrate = (user['wins'] / user['games_played'] * 100) if user['games_played'] > 0 else 0
    await message.answer(
        f"📊 <b>Твой профиль</b>\n\n"
        f"👤 Имя: {user['full_name']}\n"
        f"📈 Рейтинг ELO: <b>{user['elo_rating']}</b>\n"
        f"🎮 Сыграно игр: {user['games_played']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"📉 Процент побед: {winrate:.1f}%\n"
        f"📅 Регистрация: {user['created_at'].strftime('%d.%m.%Y')}",
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды</b>\n\n"
        "/start — Начать работу\n"
        "/profile — Твой профиль\n"
        "/top — Таблица рейтинга\n"
        "/match — Записать поражение (ты проиграл)\n"
        "/result — Записать победу (ты выиграл)\n"
        "/challenge — Вызвать игрока выше тебя (до 10 позиций)\n"
        "/history — Твои последние 10 матчей\n"
        "/h2h — Статистика личных встреч\n"
        "/help — Эта справка",
        parse_mode="HTML",
    )


# ================== /top ==================

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return

    total = await get_total_players()
    if total == 0:
        await message.answer("Пока нет игроков в рейтинге")
        return

    user_id = message.from_user.id
    user_rank = await get_user_rank(user_id)
    if user_rank is None:
        await message.answer("Не могу определить твою позицию, попробуй позже")
        return

    if total <= 30 or user_rank <= 30:
        show_upto = min(30, total)
        players = await get_players_upto(show_upto)
        display_ranks = list(range(1, len(players) + 1))
    else:
        show_upto = min(user_rank + 5, total)
        players = await get_players_upto(show_upto)
        top_ranks = list(range(1, 11))
        above_from = max(11, user_rank - 10)
        above_to = user_rank - 1
        above_ranks = list(range(above_from, above_to + 1)) if above_from <= above_to else []
        me_rank = [user_rank]
        below_ranks = list(range(user_rank + 1, min(user_rank + 5, total) + 1))
        display_ranks = top_ranks + above_ranks + me_rank + below_ranks

    text = "🏆 <b>Рейтинг игроков</b>\n\n"
    prev_rank = 0
    for rank in display_ranks:
        if rank > prev_rank + 1:
            text += "   ⋮\n"
        prev_rank = rank

        if rank > len(players):
            continue
        _, tid, uname, fname, elo = players[rank - 1]

        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
        name = fname or uname or "Аноним"

        marker = ""
        if tid == user_id:
            marker = " 👈 ты"
        elif rank < user_rank and user_rank - rank <= 10:
            marker = " ⬆️"

        text += f"{medal} {name} — <b>{elo}</b> ELO{marker}\n"

    text += f"\n<i>Всего игроков: {total}</i>\n⬆️ — можешь вызвать через /challenge"
    await message.answer(text, parse_mode="HTML")


# ================== /history ==================

@dp.message(Command("history"))
async def cmd_history(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return

    matches = await get_match_history(message.from_user.id, limit=10)
    if not matches:
        await message.answer("📭 У тебя пока нет сыгранных матчей.")
        return

    text = "📜 <b>Твои последние матчи</b>\n\n"
    for m in matches:
        date_str = m['played_at'].strftime('%d.%m %H:%M')
        if m['winner_id'] == message.from_user.id:
            opp_name = m['loser_name'] or m['loser_username'] or "Аноним"
            change = m['winner_elo_change']
            sign = "+" if change >= 0 else ""
            text += f"✅ {date_str} — Победа над {opp_name} <b>({sign}{change})</b>\n"
        else:
            opp_name = m['winner_name'] or m['winner_username'] or "Аноним"
            change = m['loser_elo_change']
            text += f"❌ {date_str} — Поражение от {opp_name} <b>({change})</b>\n"

    await message.answer(text, parse_mode="HTML")


# ================== /h2h ==================

@dp.message(Command("h2h"))
async def cmd_h2h(message: types.Message):
    if not await get_user_profile(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return

    players = await get_all_users(30)
    players = [p for p in players if p['telegram_id'] != message.from_user.id]
    if not players:
        await message.answer("Пока нет других игроков для сравнения.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🆚 {display_name(p)}",
            callback_data=f"h2h_select_{p['telegram_id']}",
        )] for p in players
    ])
    await message.answer(
        "🆚 <b>С кем сравниваем?</b>\nВыбери соперника, чтобы увидеть статистику личных встреч.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("h2h_select_"))
async def process_h2h_select(callback: CallbackQuery):
    opponent_id = int(callback.data.removeprefix("h2h_select_"))
    user_id = callback.from_user.id

    user = await get_user_profile(user_id)
    opponent = await get_user_profile(opponent_id)
    if not user or not opponent:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    wins, losses = await get_h2h_stats(user_id, opponent_id)
    total = wins + losses

    if total == 0:
        await callback.message.edit_text(
            f"🆚 Статистика с <b>{display_name(opponent)}</b>:\n\n"
            f"Вы ещё не играли друг с другом.",
            parse_mode="HTML"
        )
    else:
        winrate = (wins / total) * 100
        await callback.message.edit_text(
            f"🆚 <b>Статистика с {display_name(opponent)}</b>\n\n"
            f"Всего матчей: {total}\n"
            f"🏆 Твоих побед: <b>{wins}</b>\n"
            f"📉 Твоих поражений: <b>{losses}</b>\n"
            f"📊 Процент побед: {winrate:.1f}%",
            parse_mode="HTML"
        )
    await callback.answer()


# ================== /match (проигравший инициирует) ==================

@dp.message(Command("match"))
async def cmd_match(message: types.Message):
    if not await get_user_profile(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return

    players = await get_all_users(30)
    players = [p for p in players if p['telegram_id'] != message.from_user.id]
    if not players:
        await message.answer("Пока не с кем играть")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎱 {display_name(p)} ({p['elo_rating']} ELO)",
            callback_data=f"select_opp_{p['telegram_id']}",
        )] for p in players
    ])
    await message.answer(
        "🎱 <b>Выбери соперника, которому ты проиграл:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("select_opp_"))
async def process_select_opponent(callback: CallbackQuery):
    opponent_id = int(callback.data.removeprefix("select_opp_"))
    loser = await get_user_profile(callback.from_user.id)
    winner = await get_user_profile(opponent_id)
    if not loser or not winner:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, я проиграл",
            callback_data=f"confirm_lose_{opponent_id}",
        )]
    ])
    await callback.message.edit_text(
        f"Ты ({display_name(loser)}) проиграл {display_name(winner)}?\n"
        f"Нажми для подтверждения.",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_lose_"))
async def process_confirm_lose(callback: CallbackQuery):
    winner_id = int(callback.data.removeprefix("confirm_lose_"))
    loser_id = callback.from_user.id
    success, data = await record_match(winner_id, loser_id)
    if success:
        new_winner_elo, new_loser_elo, w_change, l_change = data
        await callback.message.edit_text(
            f"✅ <b>Результат записан!</b>\n\n"
            f"📉 Твой рейтинг: <b>{new_loser_elo}</b> ({l_change})\n"
            f"🏆 Рейтинг соперника: <b>{new_winner_elo}</b> (+{w_change})",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                winner_id,
                f"🎉 Тебе записали победу!\n"
                f"🏆 Твой новый рейтинг: <b>{new_winner_elo}</b> (+{w_change})",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text(f"❌ {data}")
    await callback.answer()


# ================== /result (победитель инициирует) ==================

@dp.message(Command("result"))
async def cmd_result(message: types.Message):
    if not await get_user_profile(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return
    players = await get_all_users(30)
    players = [p for p in players if p['telegram_id'] != message.from_user.id]
    if not players:
        await message.answer("Пока нет других игроков")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🏆 {display_name(p)} ({p['elo_rating']} ELO)",
            callback_data=f"result_select_{p['telegram_id']}",
        )] for p in players
    ])
    await message.answer(
        "🏆 <b>Выбери соперника, которого ты победил:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("result_select_"))
async def process_result_select(callback: CallbackQuery):
    loser_id = int(callback.data.removeprefix("result_select_"))
    winner_id = callback.from_user.id
    winner = await get_user_profile(winner_id)
    loser = await get_user_profile(loser_id)
    if not winner or not loser:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    success, data = await create_pending_result(winner_id, loser_id)
    if not success:
        await callback.message.edit_text(f"❌ {data}")
        await callback.answer()
        return
    pending_id = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Подтвердить поражение",
            callback_data=f"result_confirm_{pending_id}",
        )],
        [InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"result_decline_{pending_id}",
        )],
    ])
    try:
        await bot.send_message(
            loser_id,
            f"🎱 <b>{display_name(winner)}</b> записал победу над тобой.\n"
            f"Подтверди, если это правда.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            "❌ Не удалось отправить запрос сопернику (возможно, заблокировал бота)."
        )
        await delete_pending_result(pending_id)
        await callback.answer()
        return
    await callback.message.edit_text(
        f"✅ Запрос отправлен игроку {display_name(loser)}. Ждём подтверждения."
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("result_confirm_"))
async def process_result_confirm(callback: CallbackQuery):
    pending_id = int(callback.data.removeprefix("result_confirm_"))
    pending = await get_pending_result(pending_id)
    if not pending:
        await callback.message.edit_text("❌ Запрос устарел или уже обработан.")
        await callback.answer()
        return
    winner_id = pending['winner_id']
    loser_id = pending['loser_id']
    if callback.from_user.id != loser_id:
        await callback.answer("Это не твой запрос", show_alert=True)
        return
    await delete_pending_result(pending_id)
    success, data = await record_match(winner_id, loser_id)
    if success:
        new_winner_elo, new_loser_elo, w_change, l_change = data
        await callback.message.edit_text(
            f"✅ <b>Подтверждено!</b>\n\n"
            f"📉 Твой рейтинг: <b>{new_loser_elo}</b> ({l_change})",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                winner_id,
                f"🎉 Соперник подтвердил твою победу!\n"
                f"🏆 Твой новый рейтинг: <b>{new_winner_elo}</b> (+{w_change})",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text(f"❌ {data}")
    await callback.answer()


@dp.callback_query(F.data.startswith("result_decline_"))
async def process_result_decline(callback: CallbackQuery):
    pending_id = int(callback.data.removeprefix("result_decline_"))
    pending = await get_pending_result(pending_id)
    if not pending:
        await callback.message.edit_text("❌ Запрос устарел.")
        await callback.answer()
        return
    winner_id = pending['winner_id']
    loser_id = pending['loser_id']
    if callback.from_user.id != loser_id:
        await callback.answer("Это не твой запрос", show_alert=True)
        return
    await delete_pending_result(pending_id)
    await callback.message.edit_text("❌ Ты отклонил запрос. Результат не записан.")
    try:
        await bot.send_message(
            winner_id, "❌ Соперник отклонил запрос на победу."
        )
    except Exception:
        pass
    await callback.answer()


# ================== /challenge ==================

@dp.message(Command("challenge"))
async def cmd_challenge(message: types.Message):
    if not await get_user_profile(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return
    available = await get_players_above(message.from_user.id)
    if not available:
        await message.answer(
            "🚀 Некого вызывать: ты на вершине или пока мало игроков.\n"
            "Смотри /top"
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"#{rank} {fname or uname or 'Аноним'} ({elo} ELO)",
            callback_data=f"challenge_select_{tid}",
        )] for rank, tid, uname, fname, elo in available
    ])
    await message.answer(
        "⚔️ <b>Кого вызываешь?</b>\n"
        "Вызывать можно игроков выше тебя не более чем на 10 позиций.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("challenge_select_"))
async def process_challenge_select(callback: CallbackQuery):
    opponent_id = int(callback.data.removeprefix("challenge_select_"))
    challenger_id = callback.from_user.id
    challenger = await get_user_profile(challenger_id)
    opponent = await get_user_profile(opponent_id)
    if not challenger or not opponent:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    success, data = await create_challenge(challenger_id, opponent_id)
    if not success:
        await callback.message.edit_text(f"❌ {data}")
        await callback.answer()
        return
    challenge_id = data
    
    # Кнопки для соперника
    keyboard_opponent = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Принять",
            callback_data=f"challenge_accept_{challenge_id}",
        )],
        [InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"challenge_decline_{challenge_id}",
        )],
    ])
    
    # Кнопка отмены для инициатора
    keyboard_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Отменить вызов",
            callback_data=f"challenge_cancel_{challenge_id}",
        )]
    ])

    try:
        await bot.send_message(
            opponent_id,
            f"⚔️ <b>{display_name(challenger)}</b> вызывает тебя на матч!\n"
            f"Рейтинг вызывающего: <b>{challenger['elo_rating']}</b> ELO",
            reply_markup=keyboard_opponent,
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.edit_text(
            "❌ Не удалось отправить вызов (возможно, соперник заблокировал бота)."
        )
        await update_challenge_status(challenge_id, "failed")
        await callback.answer()
        return
    await callback.message.edit_text(
        f"✅ Вызов отправлен игроку {display_name(opponent)}. Ждём ответа.",
        reply_markup=keyboard_cancel
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("challenge_accept_"))
async def process_challenge_accept(callback: CallbackQuery):
    challenge_id = int(callback.data.removeprefix("challenge_accept_"))
    challenge = await get_challenge(challenge_id)
    if not challenge or challenge['status'] != "pending":
        await callback.message.edit_text("❌ Вызов устарел или уже обработан.")
        await callback.answer()
        return
    challenger_id = challenge['challenger_id']
    opponent_id = challenge['opponent_id']
    if callback.from_user.id != opponent_id:
        await callback.answer("Это не твой вызов", show_alert=True)
        return
    await update_challenge_status(challenge_id, "accepted")
    
    keyboard_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Отменить матч",
            callback_data=f"challenge_cancel_{challenge_id}",
        )]
    ])
    
    await callback.message.edit_text(
        "✅ <b>Вызов принят!</b>\n\n"
        "Сыграйте матч, затем введите результат:\n"
        "• Победитель → /result\n"
        "• Проигравший → /match",
        reply_markup=keyboard_cancel,
        parse_mode="HTML",
    )
    try:
        opponent = await get_user_profile(opponent_id)
        await bot.send_message(
            challenger_id,
            f"🎉 {display_name(opponent)} принял твой вызов!\n"
            f"После игры введите результат через /result или /match.",
            reply_markup=keyboard_cancel,
        )
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("challenge_decline_"))
async def process_challenge_decline(callback: CallbackQuery):
    challenge_id = int(callback.data.removeprefix("challenge_decline_"))
    challenge = await get_challenge(challenge_id)
    if not challenge or challenge['status'] != "pending":
        await callback.message.edit_text("❌ Вызов устарел или уже обработан.")
        await callback.answer()
        return
    challenger_id = challenge['challenger_id']
    opponent_id = challenge['opponent_id']
    if callback.from_user.id != opponent_id:
        await callback.answer("Это не твой вызов", show_alert=True)
        return
    await update_challenge_status(challenge_id, "declined")
    await callback.message.edit_text("❌ Ты отклонил вызов.")
    try:
        opponent = await get_user_profile(opponent_id)
        await bot.send_message(
            challenger_id,
            f"❌ {display_name(opponent)} отклонил твой вызов.",
        )
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("challenge_cancel_"))
async def process_challenge_cancel(callback: CallbackQuery):
    challenge_id = int(callback.data.removeprefix("challenge_cancel_"))
    challenge = await get_challenge(challenge_id)
    
    # Отменить можно только активный вызов (pending) или уже принятый матч (accepted)
    if not challenge or challenge['status'] not in ('pending', 'accepted'):
        await callback.message.edit_text("❌ Этот вызов уже обработан, завершен или отменен.")
        await callback.answer()
        return
        
    challenger_id = challenge['challenger_id']
    opponent_id = challenge['opponent_id']
    
    if callback.from_user.id not in (challenger_id, opponent_id):
        await callback.answer("Это не твой вызов", show_alert=True)
        return
        
    await update_challenge_status(challenge_id, "cancelled")
    
    await callback.message.edit_text("❌ Вы отменили вызов/матч.")
    
    # Оповещаем второго участника
    other_id = opponent_id if callback.from_user.id == challenger_id else challenger_id
    try:
        canceller = await get_user_profile(callback.from_user.id)
        await bot.send_message(
            other_id,
            f"❌ {display_name(canceller)} отменил вызов/матч.",
        )
    except Exception:
        pass
        
    await callback.answer()


# ================== Webhook ==================

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
