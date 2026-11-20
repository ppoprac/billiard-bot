# handlers/challenges.py
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_user_profile,
    get_players_above,
    get_discipline_by_id,
    get_user_rating,
    create_challenge,
    get_challenge,
    get_active_challenges_for_user,
    update_challenge_status,
)
from utils import display_name


router = Router()


def contact_line(user) -> str:
    """Строка для связи с игроком: @username, либо tg://user?id=..., либо имя."""
    if not user:
        return "—"
    if user['username'] and user['username'] != "Не указан":
        return f"@{user['username']}"
    name = user['full_name'] or "Аноним"
    return f'<a href="tg://user?id={user["telegram_id"]}">{name}</a>'


def contact_button(user) -> InlineKeyboardButton | None:
    """Кнопка «💬 Написать» (открывает чат с пользователем по tg://user?id=)."""
    if not user:
        return None
    return InlineKeyboardButton(
        text="💬 Написать",
        url=f"tg://user?id={user['telegram_id']}",
    )


def challenge_actions_keyboard(challenge, user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    if challenge['status'] == 'pending' and challenge['opponent_id'] == user_id:
        buttons.append([
            InlineKeyboardButton(text="✅ Принять", callback_data=f"challenge_accept_{challenge['id']}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"challenge_decline_{challenge['id']}"),
        ])
    if challenge['status'] in ('pending', 'accepted'):
        buttons.append([
            InlineKeyboardButton(text="🚫 Отменить", callback_data=f"challenge_cancel_{challenge['id']}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("challenge"))
async def cmd_challenge(message: types.Message):
    user = await get_user_profile(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start")
        return
    if user['current_discipline_id'] is None:
        await message.answer("Сначала выбери дисциплину через /discipline")
        return

    current_disc = await get_discipline_by_id(user['current_discipline_id'])
    active = await get_active_challenges_for_user(message.from_user.id)

    new_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"➕ Новый вызов ({current_disc['name'] if current_disc else '—'})",
            callback_data="challenge_new",
        )]
    ])

    if not active:
        await message.answer(
            "⚔️ <b>Активные вызовы</b>\n\nПока нет ни одного активного вызова.\n\n"
            f"Текущая дисциплина для новых вызовов: <b>{current_disc['name'] if current_disc else '—'}</b>",
            reply_markup=new_btn,
            parse_mode="HTML",
        )
        return

    await message.answer(
        "⚔️ <b>Твои активные вызовы (все дисциплины)</b>\n\n"
        f"Текущая дисциплина для новых вызовов: <b>{current_disc['name'] if current_disc else '—'}</b>",
        reply_markup=new_btn,
        parse_mode="HTML",
    )

    for c in active:
        if c['challenger_id'] == message.from_user.id:
            opponent_name = c['opponent_name'] or c['opponent_username'] or "Аноним"
            header = f"📤 Ты вызвал: <b>{opponent_name}</b>"
            contact_user = await get_user_profile(c['opponent_id'])
        else:
            challenger_name = c['challenger_name'] or c['challenger_username'] or "Аноним"
            header = f"📥 Тебя вызвал: <b>{challenger_name}</b>"
            contact_user = await get_user_profile(c['challenger_id'])

        status_text = "ожидает ответа" if c['status'] == 'pending' else "принят, ждём результат"
        disc_name = c['discipline_name'] or "—"

        # Кнопки: действия по вызову + «💬 Написать»
        rows = []
        if c['status'] == 'pending' and c['opponent_id'] == message.from_user.id:
            rows.append([
                InlineKeyboardButton(text="✅ Принять", callback_data=f"challenge_accept_{c['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"challenge_decline_{c['id']}"),
            ])
        if c['status'] in ('pending', 'accepted'):
            rows.append([
                InlineKeyboardButton(text="🚫 Отменить", callback_data=f"challenge_cancel_{c['id']}"),
            ])
        write_btn = contact_button(contact_user)
        if write_btn:
            rows.append([write_btn])

        await message.answer(
            f"{header}\n"
            f"🎯 Дисциплина: <b>{disc_name}</b>\n"
            f"📌 Статус: {status_text}\n"
            f"👤 Связаться: {contact_line(contact_user)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


@router.callback_query(F.data == "challenge_new")
async def process_challenge_new(callback: CallbackQuery):
    user = await get_user_profile(callback.from_user.id)
    if not user or user['current_discipline_id'] is None:
        await callback.answer("Сначала выбери дисциплину", show_alert=True)
        return

    disc_id = user['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)

    available = await get_players_above(callback.from_user.id, disc_id)
    if not available:
        await callback.answer("Некого вызывать: ты на вершине или мало игроков", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"#{rank} {fname or uname or 'Аноним'} ({elo} ELO)",
            callback_data=f"challenge_select_{tid}",
        )] for rank, tid, uname, fname, elo in available
    ])
    await callback.message.edit_text(
        f"⚔️ <b>Кого вызываешь?</b> ({discipline['name'] if discipline else '—'})\n"
        "Вызывать можно игроков выше тебя не более чем на 10 позиций.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("challenge_select_"))
async def process_challenge_select(callback: CallbackQuery, bot: Bot):
    opponent_id = int(callback.data.removeprefix("challenge_select_"))
    challenger_id = callback.from_user.id
    challenger = await get_user_profile(challenger_id)
    opponent = await get_user_profile(opponent_id)
    if not challenger or not opponent:
        await callback.answer("Игрок не найден", show_alert=True)
        return
    if challenger['current_discipline_id'] is None:
        await callback.answer("Сначала выбери дисциплину", show_alert=True)
        return

    disc_id = challenger['current_discipline_id']
    discipline = await get_discipline_by_id(disc_id)
    rating = await get_user_rating(challenger_id, disc_id)
    challenger_elo = rating['elo'] if rating else 1000

    success, data = await create_challenge(challenger_id, opponent_id, disc_id)
    if not success:
        await callback.message.edit_text(f"❌ {data}")
        await callback.answer()
        return
    challenge_id = data

    keyboard_opponent = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"challenge_accept_{challenge_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"challenge_decline_{challenge_id}")],
        [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={challenger_id}")],
    ])

    keyboard_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить вызов", callback_data=f"challenge_cancel_{challenge_id}")],
        [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={opponent_id}")],
    ])

    try:
        await bot.send_message(
            opponent_id,
            f"⚔️ <b>{display_name(challenger)}</b> вызывает тебя на матч!\n"
            f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
            f"Рейтинг вызывающего: <b>{challenger_elo}</b> ELO\n"
            f"👤 Связаться: {contact_line(challenger)}",
            reply_markup=keyboard_opponent,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        await callback.message.edit_text("❌ Не удалось отправить вызов (возможно, соперник заблокировал бота).")
        await update_challenge_status(challenge_id, "failed")
        await callback.answer()
        return
    await callback.message.edit_text(
        f"✅ Вызов отправлен игроку {display_name(opponent)}.\n"
        f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
        f"👤 Связаться: {contact_line(opponent)}",
        reply_markup=keyboard_cancel,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("challenge_accept_"))
async def process_challenge_accept(callback: CallbackQuery, bot: Bot):
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

    discipline = await get_discipline_by_id(challenge['discipline_id'])
    challenger = await get_user_profile(challenger_id)
    opponent = await get_user_profile(opponent_id)

    keyboard_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"challenge_cancel_{challenge_id}")],
        [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={challenger_id}")],
    ])

    await callback.message.edit_text(
        "✅ <b>Вызов принят!</b>\n\n"
        f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
        f"👤 Связаться с соперником: {contact_line(challenger)}\n\n"
        "Договоритесь о времени и месте. После игры введите результат:\n"
        "• Победитель → /result\n• Проигравший → /match",
        reply_markup=keyboard_cancel,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    try:
        keyboard_for_challenger = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить матч", callback_data=f"challenge_cancel_{challenge_id}")],
            [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={opponent_id}")],
        ])
        await bot.send_message(
            challenger_id,
            f"🎉 {display_name(opponent)} принял твой вызов!\n"
            f"🎯 Дисциплина: <b>{discipline['name'] if discipline else '—'}</b>\n"
            f"👤 Связаться с соперником: {contact_line(opponent)}\n\n"
            "Договоритесь о времени и месте. После игры введите результат через /result или /match.",
            reply_markup=keyboard_for_challenger,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("challenge_decline_"))
async def process_challenge_decline(callback: CallbackQuery, bot: Bot):
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
        await bot.send_message(challenger_id, f"❌ {display_name(opponent)} отклонил твой вызов.")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("challenge_cancel_"))
async def process_challenge_cancel(callback: CallbackQuery, bot: Bot):
    challenge_id = int(callback.data.removeprefix("challenge_cancel_"))
    challenge = await get_challenge(challenge_id)

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

    other_id = opponent_id if callback.from_user.id == challenger_id else challenger_id
    try:
        canceller = await get_user_profile(callback.from_user.id)
        await bot.send_message(other_id, f"❌ {display_name(canceller)} отменил вызов/матч.")
    except Exception:
        pass

    await callback.answer()
