import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from database import init_db, get_or_create_user, get_user_profile, get_top_players, get_user_by_username, record_match

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
        f"Используй /help для списка команд"
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
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer("⚠️ Напиши ник соперника. Пример: `/match @ivan`", parse_mode="Markdown")
        return

    opponent_username = args[1]
    opponent = await get_user_by_username(opponent_username)
    
    if not opponent:
        await message.answer(f"❌ Игрок {opponent_username} не найден. Пусть он сначала напишет боту /start")
        return

    if opponent[0] == message.from_user.id:
        await message.answer("❌ Нельзя играть сам с собой! 😄")
        return

    # Создаем красивые кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Я выиграл", callback_data=f"match_win_{opponent[0]}"),
            InlineKeyboardButton(text="❌ Я проиграл", callback_data=f"match_lose_{opponent[0]}")
        ]
    ])

    await message.answer(
        f"🎱 **Матч против:** {opponent[2]}\n"
        f"📊 Его рейтинг: **{opponent[3]}** ELO\n\n"
        f"Как прошел матч?",
        reply_markup=keyboard
    )

# Обработчик нажатий на кнопки
@dp.callback_query(F.data.startswith("match_"))
async def process_match_result(callback: CallbackQuery):
    # Разбираем данные кнопки (например, match_win_123456789)
    parts = callback.data.split("_")
    result = parts[1]  # win или lose
    opponent_id = int(parts[2])
    
    winner_id = callback.from_user.id if result == "win" else opponent_id
    loser_id = opponent_id if result == "win" else callback.from_user.id

    success, data = await record_match(winner_id, loser_id)
    
    if success:
        new_winner_elo = data[0]
        new_loser_elo = data[1]
        
        winner_name = callback.from_user.full_name if result == "win" else "Соперник"
        loser_name = "Соперник" if result == "win" else callback.from_user.full_name
        
        text = (f"✅ **Результат записан!**\n\n"
                f"🏆 Победитель: {winner_name} (теперь **{new_winner_elo}** ELO)\n"
                f"📉 Проигравший: {loser_name} (теперь **{new_loser_elo}** ELO)")
        
        # Заменяем сообщение с кнопками на текст результата
        await callback.message.edit_text(text)
    else:
        await callback.answer("❌ Ошибка при записи матча", show_alert=True)
        
    await callback.answer() # Убираем "часики" на кнопке

async def main():
    # Инициализируем базу данных
    await init_db()
    print("База данных инициализирована")
    print("Бот запущен и ожидает сообщения...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
