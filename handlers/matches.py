# handlers/matches.py
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_user_profile,
    get_discipline_by_id,
    get_players_for_match,
    record_match,
    create_pending_result,
    get_pending_result,
    delete_pending_result,
)
from utils import display_name


router = Router()

MATCH_RANGE = 15  # ±15 позиций по рейтингу дисциплины


# ================== /match (проигравший инициирует) ==================

@router.message(Command("match"))
async def cmd_match(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)
    players = await get_players_for_match(disc_id, message.from_user.id, offset=MATCH_RANGE)
    if not players:
        await message.answer(
            "Некого выбрать: в этой дисциплине пока нет других игроков "
            f"в радиусе ±{MATCH_RANGE} позиций от тебя."
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎱 {fname or uname or 'Аноним'} ({elo} ELO)",
            callback_data=f"select_opp_{tid}",
        )] for rank, tid, uname, fname, elo in players
    ])
    await message.answer(
        f"🎱 <b>Выбери соперника, которому ты проиграл</b>\n"
        f"<i>Дисциплина: {discipline['name'] if discipline else '—'}. "
        f"Показаны игроки в радиусе ±{MATCH_RANGE} позиций.</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("select_opp_"))
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


@router.callback_query(F.data.startswith("confirm_lose_"))
async def process_confirm_lose(callback: CallbackQuery, bot: Bot):
    winner_id = int(callback.data.removeprefix("confirm_lose_"))
    loser_id = callback.from_user.id

    user = await get_user_profile(loser_id)
    if not user or user['current_discipline_id'] is None:
        await callback.answer("Сначала выбери дисциплину", show_alert=True)
        return
    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)

    success, data = await record_match(winner_id, loser_id, disc_id)
    if success:
        new_winner_elo, new_loser_elo, w_change, l_change = data
        await callback.message.edit_text(
            f"✅ <b>Результат записан ({discipline['name'] if discipline else '—'})!</b>\n\n"
            f"📉 Твой рейтинг: <b>{new_loser_elo}</b> ({l_change})\n"
            f"🏆 Рейтинг соперника: <b>{new_winner_elo}</b> (+{w_change})",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                winner_id,
                f"🎉 Тебе записали победу!\n"
                f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
                f"🏆 Твой новый рейтинг: <b>{new_winner_elo}</b> (+{w_change})",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text(f"❌ {data}")
    await callback.answer()


# ================== /result (победитель инициирует) ==================

@router.message(Command("result"))
async def cmd_result(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)
    players = await get_players_for_match(disc_id, message.from_user.id, offset=MATCH_RANGE)
    if not players:
        await message.answer(
            "Некого выбрать: в этой дисциплине пока нет других игроков "
            f"в радиусе ±{MATCH_RANGE} позиций от тебя."
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🏆 {fname or uname or 'Аноним'} ({elo} ELO)",
            callback_data=f"result_select_{tid}",
        )] for rank, tid, uname, fname, elo in players
    ])
    await message.answer(
        f"🏆 <b>Выбери соперника, которого ты победил</b>\n"
        f"<i>Дисциплина: {discipline['name'] if discipline else '—'}. "
        f"Показаны игроки в радиусе ±{MATCH_RANGE} позиций.</i>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("result_select_"))
async def process_result_select(callback: CallbackQuery, bot: Bot):
    loser_id = int(callback.data.removeprefix("result_select_"))
    winner_id = callback.from_user.id
    winner = await get_user_profile(winner_id)
    loser = await get_user_profile(loser_id)
    if not winner or not loser:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    if winner['current_discipline_id'] is None:
        await callback.answer("Сначала выбери дисциплину", show_alert=True)
        return

    disc_id = winner['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)

    success, data = await create_pending_result(winner_id, loser_id, disc_id)
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
            f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
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


@router.callback_query(F.data.startswith("result_confirm_"))
async def process_result_confirm(callback: CallbackQuery, bot: Bot):
    pending_id = int(callback.data.removeprefix("result_confirm_"))
    pending = await get_pending_result(pending_id)
    if not pending:
        await callback.message.edit_text("❌ Запрос устарел или уже обработан.")
        await callback.answer()
        return
    winner_id = pending['winner_id']
    loser_id = pending['loser_id']
    disc_id = pending['discipline_id']
    if callback.from_user.id != loser_id:
        await callback.answer("Это не твой запрос", show_alert=True)
        return

    discipline = await get_discipline_by_id(disc_id)

    await delete_pending_result(pending_id)
    success, data = await record_match(winner_id, loser_id, disc_id)
    if success:
        new_winner_elo, new_loser_elo, w_change, l_change = data
        await callback.message.edit_text(
            f"✅ <b>Подтверждено ({discipline['name'] if discipline else '—'})!</b>\n\n"
            f"📉 Твой рейтинг: <b>{new_loser_elo}</b> ({l_change})",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                winner_id,
                f"🎉 Соперник подтвердил твою победу!\n"
                f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
                f"🏆 Твой новый рейтинг: <b>{new_winner_elo}</b> (+{w_change})",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text(f"❌ {data}")
    await callback.answer()


@router.callback_query(F.data.startswith("result_decline_"))
async def process_result_decline(callback: CallbackQuery, bot: Bot):
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
