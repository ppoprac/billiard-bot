# keyboards/inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def disciplines_keyboard(disciplines, prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for d in disciplines:
        rows.append([InlineKeyboardButton(
            text=d['name'],
            callback_data=f"{prefix}_{d['id']}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
