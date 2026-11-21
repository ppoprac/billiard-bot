# handlers/rating.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_user_profile,
    get_all_users_paginated,
    get_discipline_by_id,
    get_total_players,
    get_user_rank,
    get_players_upto,
    get_match_history,
    get_h2h_stats,
)
from utils import display_name


router = Router()

H2H_PAGE_SIZE = 10


# ================== /top ==================

@router.message(Command("top"))
async def cmd_top(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    discipline = await get_discipline_by_id(user['current_discipline_id'])
    disc_id = user['current_discipline_id']

    total = await get_total_players(disc_id)
    if total == 0:
        await message.answer("Пока нет игроков в рейтинге этой дисциплины")
        return

    user_id = message.from_user.id
    user_rank = await get_user_rank(user_id, disc_id)

    if total <= 30 or user_rank <= 30:
        show_upto = min(30, total)
        players = await get_players_upto(disc_id, show_upto)
        display_ranks = list(range(1, len(players) + 1))
    else:
        show_upto = min(user_rank + 5, total)
        players = await get_players_upto(disc_id, show_upto)
        top_ranks = list(range(1, 11))
        above_from = max(11, user_rank - 10)
        above_to = user_rank - 1
        above_ranks = list(range(above_from, above_to + 1)) if above_from <= above_to else []
        me_rank = [user_rank]
        below_ranks = list(range(user_rank + 1, min(user_rank + 5, total) + 1))
        display_ranks = top_ranks + above_ranks + me_rank + below_ranks

    text = f"🏆 <b>Рейтинг — {discipline['name'] if discipline else '—'}</b>\n\n"
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

@router.message(Command("history"))
async def cmd_history(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)

    matches = await get_match_history(message.from_user.id, disc_id, limit=10)
    if not matches:
        await message.answer("📭 У тебя пока нет сыгранных матчей в этой дисциплине.")
        return

    text = f"📜 <b>Последние матчи — {discipline['name'] if discipline else '—'}</b>\n\n"
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

def _build_h2h_keyboard(players, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for p in players:
        rows.append([InlineKeyboardButton(
            text=f"🆚 {display_name(p)}",
            callback_data=f"h2h_select_{p['telegram_id']}",
        )])
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"h2h_page_{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"h2h_page_{page + 1}"))
        if nav:
            rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_h2h_text(page: int, total_pages: int) -> str:
    return (
        f"🆚 <b>С кем сравниваем?</b>\n"
        f"<i>Выбери соперника, чтобы увидеть статистику личных встреч в текущей дисциплине. "
        f"Стр. {page + 1}/{total_pages}</i>"
    )


@router.message(Command("h2h"))
async def cmd_h2h(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    total, players = await get_all_users_paginated(0, H2H_PAGE_SIZE, exclude_id=message.from_user.id)
    if not players:
        await message.answer("Пока нет других игроков для сравнения.")
        return

    total_pages = (total + H2H_PAGE_SIZE - 1) // H2H_PAGE_SIZE
    await message.answer(
        _build_h2h_text(0, total_pages),
        reply_markup=_build_h2h_keyboard(players, 0, total_pages),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("h2h_page_"))
async def process_h2h_page(callback: CallbackQuery):
    page = int(callback.data.removeprefix("h2h_page_"))
    total, players = await get_all_users_paginated(
        page * H2H_PAGE_SIZE, H2H_PAGE_SIZE, exclude_id=callback.from_user.id
    )
    if not players:
        await callback.answer("Страница пуста", show_alert=True)
        return
    total_pages = (total + H2H_PAGE_SIZE - 1) // H2H_PAGE_SIZE
    await callback.message.edit_text(
        _build_h2h_text(page, total_pages),
        reply_markup=_build_h2h_keyboard(players, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("h2h_select_"))
async def process_h2h_select(callback: CallbackQuery):
    opponent_id = int(callback.data.removeprefix("h2h_select_"))
    user_id = callback.from_user.id

    user = await get_user_profile(user_id)
    opponent = await get_user_profile(opponent_id)
    if not user or not opponent:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    if user['current_discipline_id'] is None:
        await callback.answer("Сначала выбери дисциплину", show_alert=True)
        return

    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)

    wins, losses = await get_h2h_stats(user_id, opponent_id, disc_id)
    total = wins + losses
    disc_name = discipline['name'] if discipline else "—"

    if total == 0:
        await callback.message.edit_text(
            f"🆚 Статистика с <b>{display_name(opponent)}</b> ({disc_name}):\n\n"
            f"Вы ещё не играли друг с другом в этой дисциплине.",
            parse_mode="HTML"
        )
    else:
        winrate = (wins / total) * 100
        await callback.message.edit_text(
            f"🆚 <b>Статистика с {display_name(opponent)}</b> ({disc_name})\n\n"
            f"Всего матчей: {total}\n"
            f"🏆 Твоих побед: <b>{wins}</b>\n"
            f"📉 Твоих поражений: <b>{losses}</b>\n"
            f"📊 Процент побед: {winrate:.1f}%",
            parse_mode="HTML"
        )
    await callback.answer()
