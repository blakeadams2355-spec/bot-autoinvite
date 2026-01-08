from __future__ import annotations

from typing import List

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def format_button_text(text: str, max_length: int = 50) -> str:
    if not text:
        return "(без названия)"
    text = text.strip().replace("\n", " ")
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"


def paginate_channels(channels: List[dict], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    total = len(channels)
    if total == 0:
        builder.button(text="(пусто)", callback_data="noop")
        return builder.as_markup()

    page = max(page, 0)
    start = page * per_page
    end = start + per_page
    items = channels[start:end]

    for ch in items:
        title = ch.get("channel_title") or ch.get("channel_name") or str(ch.get("channel_id"))
        builder.button(
            text=format_button_text(title),
            callback_data=f"channel_select:{ch['channel_id']}",
        )

    nav = InlineKeyboardBuilder()
    max_page = (total - 1) // per_page

    if page > 0:
        nav.button(text="◀️", callback_data=f"channels_page:{page - 1}")
    nav.button(text=f"{page + 1}/{max_page + 1}", callback_data="noop")
    if page < max_page:
        nav.button(text="▶️", callback_data=f"channels_page:{page + 1}")

    builder.adjust(1)
    nav.adjust(3)

    markup = builder.as_markup()
    markup.inline_keyboard.append(nav.as_markup().inline_keyboard[0])

    return markup
