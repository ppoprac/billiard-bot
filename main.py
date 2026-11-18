import os
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from database import (
    init_db, close_pool, get_or_create_user, get_user_profile, get_all_users,
    get_players_above, get_total_players, get_user_rank, get_players_upto,
    record_match, get_match_history, get_h2h_stats, create_challenge, get_challenge,
    update_challenge_status, create_pending_result, get_pending_result,
    delete_pending_result, admin_ban_user, admin_delete_user,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_ID = os.getenv("ADMIN_ID") # Добавь свой ID в Render (Environment Variables)
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

if not BOT_TOKEN:
    raise RuntimeError("Переменная BOT_TOKEN не установлена")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def display_name(row):
    return row['full_name'] or row['username'] or "Аноним"

def is_admin(user_id: int) -> bool:
    return ADMIN_ID and str(user_id) == str(ADMIN_ID)

# ================== БАЗОВЫЕ КОМАНДЫ ==================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username or "Не указан",
        message.from_user.full_name,
    )
    if user['is_banned']:
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return

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

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды</b>\n\n"
        "/start — Начать работу\n"
        "/profile — Твой профиль\n"
        "/top — Таблица рейтинга\n"
        "/match — Записать поражение\n"
        "/result — Записать победу\n"
        "/challenge — Вызвать игрока (до 10 позиций)\n"
        "/history — Твои последние 10 матчей\n"
        "/h2h — Статистика личных встреч\n"
        "/help — Эта справка",
        parse_mode="HTML",
    )

# Перехватываем все команды, чтобы забаненные не могли ими пользоваться
# (Ставим этот хэндлер после CommandStart и CommandHelp)
@dp.message(F.text.startswith("/"))
async def check_ban(message: types.Message):
    if message.text.startswith(("/start", "/help", "/admin")): 
        return # Пропускаем базовые и админские
    
    user = await get_user_profile(message.from_user.id)
    if user and user['is_banned']:
        await message.answer("🚫 Вы заблокированы. Доступ к командам закрыт.")
        return
    # Если не забанен, пропускаем дальше (aiogram продолжит искать нужный хэндлер)
    raise SkipHandler() 
    
# ВАЖНО: нужно импортировать SkipHandler из aiogram.dispatcher.event.bases
from aiogram.dispatcher.event.bases import SkipHandler

# ================== АДМИН-КОМАНДЫ ==================

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👑 <b>Админ-панель</b>\n\n"
        "Чтобы забанить или удалить игрока, отправьте команду:\n"
        "<code>/ban 123456789</code>\n"
        "<code>/unban 123456789</code>\n"
        "<code>/delete_user 123456789</code>\n\n"
        "Или просто <b>перешлите сообщение</b> от нарушителя боту с подписью <code>/ban</code> в ответ.",
        parse_mode="HTML"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    target_id = None
    
    # Если ответили на сообщение
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    # Если передали ID числом
    elif len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])
        except ValueError:
            pass
            
    if not target_id:
        await message.answer("Укажите ID игрока или ответьте на его сообщение.")
        return
        
    success = await admin_ban_user(target_id, True)
    if success:
        await message.answer(f"✅ Игрок {target_id} забанен. Он скрыт из топов и не может играть.")
        try:
            await bot.send_message(target_id, "🚫 Вы были заблокированы администратором за нарушение правил.")
        except Exception:
            pass
    else:
        await message.answer("❌ Игрок с таким ID не найден.")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])
        except ValueError:
            pass
            
    if not target_id:
        await message.answer("Укажите ID игрока или ответьте на его сообщение.")
        return
        
    success = await admin_ban_user(target_id, False)
    if success:
        await message.answer(f"✅ Игрок {target_id} разбанен.")
    else:
        await message.answer("❌ Игрок с таким ID не найден.")

@dp.message(Command("delete_user"))
async def cmd_delete_user(message: types.Message):
    if not is_admin(message.from_user.id): return
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])
        except ValueError:
            pass
            
    if not target_id:
        await message.answer("Укажите ID игрока или ответьте на его сообщение.")
        return
        
    success = await admin_delete_user(target_id)
    if success:
        await message.answer(f"🗑 Игрок {target_id} полностью удален. Его история матчей сохранена как 'Удаленный игрок'.")
    else:
        await message.answer("❌ Игрок с таким ID не найден.")
