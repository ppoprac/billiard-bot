# handlers/admin.py
import logging

from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_ID
from database import (
    get_user_profile,
    get_all_users_paginated,
    admin_ban_user,
    admin_delete_user,
)
from states import ReportStates
from utils import display_name, is_admin


router = Router()

REPORT_PAGE_SIZE = 10


def _build_report_keyboard(players, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for p in players:
        rows.append([InlineKeyboardButton(
            text=f"⚠️ {display_name(p)}",
            callback_data=f"report_target_{p['telegram_id']}",
        )])
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"report_page_{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"report_page_{page + 1}"))
        if nav:
            rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_report_text(page: int, total_pages: int) -> str:
    return (
        f"🚨 <b>На кого жалуешься?</b>\n"
        f"<i>Выбери игрока из списка ниже. Стр. {page + 1}/{total_pages}</i>"
    )


# ================== /report ==================

@router.message(Command("report"))
async def cmd_report(message: types.Message, state: FSMContext):
    if not await get_user_profile(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return

    total, players = await get_all_users_paginated(0, REPORT_PAGE_SIZE, exclude_id=message.from_user.id)
    if not players:
        await message.answer("Некого жаловать, в базе нет других игроков.")
        return

    total_pages = (total + REPORT_PAGE_SIZE - 1) // REPORT_PAGE_SIZE
    await message.answer(
        _build_report_text(0, total_pages),
        reply_markup=_build_report_keyboard(players, 0, total_pages),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("report_page_"))
async def process_report_page(callback: CallbackQuery):
    page = int(callback.data.removeprefix("report_page_"))
    total, players = await get_all_users_paginated(
        page * REPORT_PAGE_SIZE, REPORT_PAGE_SIZE, exclude_id=callback.from_user.id
    )
    if not players:
        await callback.answer("Страница пуста", show_alert=True)
        return
    total_pages = (total + REPORT_PAGE_SIZE - 1) // REPORT_PAGE_SIZE
    await callback.message.edit_text(
        _build_report_text(page, total_pages),
        reply_markup=_build_report_keyboard(players, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_target_"))
async def process_report_target(callback: CallbackQuery, state: FSMContext):
    target_id = int(callback.data.removeprefix("report_target_"))

    if target_id == callback.from_user.id:
        await callback.answer("На себя жаловаться нельзя.", show_alert=True)
        return

    await state.update_data(target_id=target_id)
    await state.set_state(ReportStates.waiting_for_reason)

    await callback.message.edit_text(
        "📝 <b>Опиши причину жалобы</b> одним сообщением.\n\n"
        "Например: <i>«Оскорблял в личных сообщениях»</i> или <i>«Отказывается записывать результат»</i>.\n\n"
        "Чтобы отменить, напиши /cancel",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ReportStates.waiting_for_reason)
async def process_report_reason(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Пожалуйста, отправь текстовое сообщение с причиной.")
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    reason = message.text

    await state.clear()

    if not ADMIN_ID:
        await message.answer("❌ Ошибка: администратор не настроил систему жалоб (нет ADMIN_ID).")
        return

    target = await get_user_profile(target_id)
    target_name = display_name(target) if target else f"ID {target_id}"

    reporter = await get_user_profile(message.from_user.id)
    reporter_name = display_name(reporter)

    admin_text = (
        f"🚨 <b>НОВАЯ ЖАЛОБА</b>\n\n"
        f"👤 <b>От кого:</b> {reporter_name} (ID: <code>{message.from_user.id}</code>)\n"
        f"🎯 <b>На кого:</b> {target_name} (ID: <code>{target_id}</code>)\n"
        f"📝 <b>Причина:</b> {reason}\n\n"
        f"<i>Чтобы забанить нарушителя, отправь:</i>\n"
        f"<code>/ban {target_id}</code>"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        await message.answer("✅ Жалоба отправлена администратору. Спасибо за бдительность!")
    except Exception as e:
        logging.error(f"Не удалось отправить жалобу админу: {e}")
        await message.answer("❌ Не удалось отправить жалобу. Возможно, админ заблокировал бота.")


# ================== АДМИН-КОМАНДЫ ==================

@router.message(Command("admin"))
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


@router.message(Command("ban"))
async def cmd_ban(message: types.Message, bot: Bot):
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

    success = await admin_ban_user(target_id, True)
    if success:
        await message.answer(f"✅ Игрок {target_id} забанен. Он скрыт из топов и не может играть.")
        try:
            await bot.send_message(target_id, "🚫 Вы были заблокированы администратором за нарушение правил.")
        except Exception:
            pass
    else:
        await message.answer("❌ Игрок с таким ID не найден.")


@router.message(Command("unban"))
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


@router.message(Command("delete_user"))
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
