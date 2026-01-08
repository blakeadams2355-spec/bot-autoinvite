from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить канал", callback_data="add_channel")
    builder.button(text="⚙️ Настройки", callback_data="settings")
    builder.button(text="❓ FAQ", callback_data="faq")
    builder.adjust(1)
    return builder.as_markup()
