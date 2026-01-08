from __future__ import annotations

import re
from datetime import datetime


def format_number(num: int) -> str:
    return f"{num:,}".replace(",", " ")


def escape_markdown(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}.!\\])", r"\\\1", text)


def get_channel_link(channel_id: int, channel_name: str) -> str:
    if channel_name:
        if not channel_name.startswith("@"): 
            channel_name = f"@{channel_name}"
        return channel_name
    if str(channel_id).startswith("-100"):
        internal_id = str(channel_id)[4:]
        return f"https://t.me/c/{internal_id}"
    return str(channel_id)


def get_human_readable_date(date: datetime) -> str:
    return date.strftime("%d %b %Y")
