import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from database import init_db, get_or_create_user, get_user_profile, get_top_players, get_user_by_username, record_match, get_all_users

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Не указан"
    full_name = message.from_user.full_name
    
    # Регистрируем или получаем пользователя из БД
    user = await get_or_create_user(user_id, username, full_name)
    
    await message.answer(
        f"Привет, {full_name}! 🎱\n\n"
        f"Я твой бильярдный помощник в Могилёве.\n\n"
        f"📊 Твой текущий рейтинг: **{user[3]}** ELO\n"
        f"🎮 Сыграно игр: {user[4]}\n"
        f"🏆 Побед: {user[5]}\n\n"
        f"Скоро здесь появится:\n"
        f"🏆 Лестница вызовов\n"
        f"📊 Турнирные сетки\n"
        f"📍 Поиск соперников\n\n"
        f"📍 Поиск соперников\n\n"
        f"👇 Быстрые команды:\n"
        f"/match — Записать поражение\n"
        f"/top — Таблица рейтинга\n"
        f"/profile — Твоя статистика"
    )
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await get_user_profile(user_id)
    
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start")
        return
    
    winrate = (user[5] / user[4] * 100) if user[4] > 0 else 0
    
    await message.answer(
        f"📊 **Твой профиль**\n\n"
        f"👤 Имя: {user[2]}\n"
        f"📈 Рейтинг ELO: **{user[3]}**\n"
        f"🎮 Сыграно игр: {user[4]}\n"
        f"🏆 Побед: {user[5]}\n"
        f"📉 Процент побед: {winrate:.1f}%\n"
        f"📅 Регистрация: {user[6]}"
    )

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    players = await get_top_players(10)
    
    if not players:
        await message.answer("Пока нет игроков в рейтинге")
        return
    
    text = "🏆 **Топ-10 игроков**\n\n"
    for i, player in enumerate(players, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {player[2]} — **{player[3]}** ELO\n"
    
    await message.answer(text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 **Список команд**\n\n"
        "/start — Начать работу с ботом\n"
        "/profile — Твой профиль и статистика\n"
        "/top — Топ-10 игроков по рейтингу\n"
        "/help — Эта справка\n\n"
        "🚧 В разработке:\n"
        "/challenge — Вызвать соперника\n"
        "/result — Ввести результат матча\n"
        "/ladder — Таблица лестницы"
    )

@dp.message(Command("match"))
async def cmd_match(message: types.Message):
    # Проверяем, зарегистрирован ли пользователь
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start, чтобы зарегистрироваться")
        return

    # Получаем список игроков (топ-30)
    players = await get_all_users(30)
    # Убираем из списка самого пользователя
    players = [p for p in players if p[0] != message.from_user.id]

    if not players:
        await message.answer("Пока не с кем играть. Попроси друга написать боту /start")
        return

    # Создаем кнопки с именами игроков
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for p in players:
        # Берем имя, если нет - берем никнейм
        name = p[2] if p[2] else (p[1] if p[1] else "Аноним")
        # Кнопка на всю ширину экрана
        btn = InlineKeyboardButton(text=f"🎱 {name} ({p[3]} ELO)", callback_data=f"select_opp_{p[0]}")
        keyboard.inline_keyboard.append([btn])

    await message.answer(
        "🎱 **Выбери соперника, которому ты проиграл:**", 
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Обработчик выбора соперника
@dp.callback_query(F.data.startswith("select_opp_"))
async def process_select_opponent(callback: CallbackQuery):
    opponent_id = int(callback.data.split("_")[2])
    loser_id = callback.from_user.id

    # Получаем данные для красивого отображения
    loser = await get_user_profile(loser_id)
    winner = await get_user_profile(opponent_id)

    loser_name = loser[2] if loser[2] else "Ты"
    winner_name = winner[2] if winner[2] else "Соперник"

    # Кнопка подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, я проиграл", callback_data=f"confirm_lose_{opponent_id}")]
    ])

    text = f"Ты ({loser_name}) проиграл {winner_name}?\nНажми кнопку для подтверждения."
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# Обработчик подтверждения поражения
@dp.callback_query(F.data.startswith("confirm_lose_"))
async def process_confirm_lose(callback: CallbackQuery):
    winner_id = int(callback.data.split("_")[2])
    loser_id = callback.from_user.id

    success, data = await record_match(winner_id, loser_id)

    if success:
        new_winner_elo = data[0]
        new_loser_elo = data[1]
        
        text = (f"✅ **Результат честно записан!**\n\n"
                f"📉 Твой новый рейтинг: **{new_loser_elo}** ELO\n"
                f"🏆 Рейтинг соперника: **{new_winner_elo}** ELO\n\n"
                f"Посмотри обновленный топ командой /top")
        await callback.message.edit_text(text)
    else:
        await callback.message.edit_text("❌ Ошибка при записи матча.")
        
    await callback.answer()

async def main():
    # Инициализируем базу данных
    await init_db()
    print("База данных инициализирована")
    print("Бот запущен и ожидает сообщения...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
