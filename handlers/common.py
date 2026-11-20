# handlers/common.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import COMMUNITY_CHAT_URL
from database import (
    get_or_create_user,
    get_user_profile,
    get_all_disciplines,
    get_discipline_by_id,
    set_user_current_discipline,
    ensure_user_rating,
    get_user_rating,
)
from keyboards.inline import disciplines_keyboard


router = Router()


def community_line_html() -> str:
    """Строка про группу для HTML-сообщений. Пустая, если ссылка не задана."""
    if not COMMUNITY_CHAT_URL:
        return ""
    return f"\n\n💬 Поиск соперников и общение — в нашей группе: {COMMUNITY_CHAT_URL}"


def community_button() -> InlineKeyboardButton | None:
    """Кнопка «💬 Группа» для клавиатур. None, если ссылка не задана."""
    if not COMMUNITY_CHAT_URL:
        return None
    return InlineKeyboardButton(text="💬 Группа", url=COMMUNITY_CHAT_URL)


COMMANDS_HELP = (
    "👇 <b>Команды</b>\n\n"
    "👤 <b>Профиль и рейтинг</b>\n"
    "/profile — Твоя статистика\n"
    "/top — Таблица рейтинга\n\n"
    "🎱 <b>Записать результат матча</b>\n"
    "/result — Я победил\n"
    "/match — Я проиграл\n\n"
    "⚔️ <b>Найти соперника</b>\n"
    "/challenge — Мои вызовы и новый вызов\n\n"
    "📜 <b>История</b>\n"
    "/history — Последние матчи\n"
    "/h2h — Личные встречи\n\n"
    "⚙️ <b>Настройки и сервис</b>\n"
    "/discipline — Сменить дисциплину\n"
    "/report — Пожаловаться на игрока\n"
    "/help — Все команды\n"
    "/start — Перезапустить бота"
)


async def get_active_discipline(user):
    if not user or user['current_discipline_id'] is None:
        return None, None
    discipline = await get_discipline_by_id(user['current_discipline_id'])
    rating = await ensure_user_rating(user['telegram_id'], user['current_discipline_id'])
    return discipline, rating


async def send_welcome(message: types.Message, user):
    discipline, rating = await get_active_discipline(user)
    elo = rating['elo'] if rating else 1000
    games = rating['games_played'] if rating else 0
    wins = rating['wins'] if rating else 0
    disc_name = discipline['name'] if discipline else "—"

    text = (
        f"Привет, {user['full_name']}! 🎱\n\n"
        f"🎯 Дисциплина: <b>{disc_name}</b>\n"
        f"📊 Твой рейтинг: <b>{elo}</b> ELO\n"
        f"🎮 Игр: {games} | 🏆 Побед: {wins}\n\n"
        f"{COMMANDS_HELP}"
        f"{community_line_html()}"
    )

    btn = community_button()
    if btn:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username or "Не указан",
        message.from_user.full_name,
    )
    if user['is_banned']:
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return

    if user['current_discipline_id'] is None:
        disciplines = await get_all_disciplines()
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Перед началом выбери дисциплину, в которой будешь играть.\n"
            "Позже её можно сменить командой /discipline.",
            reply_markup=disciplines_keyboard(disciplines, "pick_disc"),
        )
        return

    await ensure_user_rating(user['telegram_id'], user['current_discipline_id'])
    await send_welcome(message, user)


@router.callback_query(F.data.startswith("pick_disc_"))
async def process_pick_discipline(callback: CallbackQuery):
    discipline_id = int(callback.data.removeprefix("pick_disc_"))
    discipline = await get_discipline_by_id(discipline_id)
    if not discipline:
        await callback.answer("Дисциплина не найдена", show_alert=True)
        return

    user = await get_user_profile(callback.from_user.id)
    if not user:
        await callback.answer("Сначала напиши /start", show_alert=True)
        return

    await ensure_user_rating(callback.from_user.id, discipline_id)
    await set_user_current_discipline(callback.from_user.id, discipline_id)

    rating = await get_user_rating(callback.from_user.id, discipline_id)
    elo = rating['elo'] if rating else 1000

    text = (
        f"✅ Дисциплина выбрана: <b>{discipline['name']}</b>\n\n"
        f"📊 Твой рейтинг: <b>{elo}</b> ELO\n\n"
        f"Можешь начинать! Список команд — /help"
        f"{community_line_html()}"
    )

    btn = community_button()
    if btn:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
            disable_web_page_preview=True,
        )
    else:
        await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = COMMANDS_HELP + community_line_html()

    btn = community_button()
    if btn:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


@router.message(Command("discipline"))
async def cmd_discipline(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return

    if user['current_discipline_id'] is None:
        disciplines = await get_all_disciplines()
        await message.answer(
            "Перед началом выбери дисциплину:",
            reply_markup=disciplines_keyboard(disciplines, "pick_disc"),
        )
        return

    current = await get_discipline_by_id(user['current_discipline_id'])
    disciplines = await get_all_disciplines()
    await message.answer(
        f"🎯 Текущая дисциплина: <b>{current['name'] if current else '—'}</b>\n\n"
        f"Выбери новую:",
        reply_markup=disciplines_keyboard(disciplines, "switch_disc"),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("switch_disc_"))
async def process_switch_discipline(callback: CallbackQuery):
    discipline_id = int(callback.data.removeprefix("switch_disc_"))
    discipline = await get_discipline_by_id(discipline_id)
    if not discipline:
        await callback.answer("Дисциплина не найдена", show_alert=True)
        return

    user = await get_user_profile(callback.from_user.id)
    if not user:
        await callback.answer("Сначала напиши /start", show_alert=True)
        return

    await ensure_user_rating(callback.from_user.id, discipline_id)
    await set_user_current_discipline(callback.from_user.id, discipline_id)

    rating = await get_user_rating(callback.from_user.id, discipline_id)
    elo = rating['elo'] if rating else 1000

    await callback.message.edit_text(
        f"✅ Дисциплина переключена: <b>{discipline['name']}</b>\n\n"
        f"📊 Твой рейтинг здесь: <b>{elo}</b> ELO",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    discipline, rating = await get_active_discipline(user)
    elo = rating['elo'] if rating else 1000
    games = rating['games_played'] if rating else 0
    wins = rating['wins'] if rating else 0
    winrate = (wins / games * 100) if games > 0 else 0

    await message.answer(
        f"📊 <b>Твой профиль</b>\n\n"
        f"👤 Имя: {user['full_name']}\n"
        f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
        f"📈 Рейтинг ELO: <b>{elo}</b>\n"
        f"🎮 Сыграно игр: {games}\n"
        f"🏆 Побед: {wins}\n"
        f"📉 Процент побед: {winrate:.1f}%\n"
        f"📅 Регистрация: {user['created_at'].strftime('%d.%m.%Y')}",
        parse_mode="HTML",
    )
