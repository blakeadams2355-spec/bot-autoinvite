from __future__ import annotations

import logging
from typing import Optional

import aiosqlite
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatMember

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


async def get_bot_status_in_channel(bot: Bot, channel_id: int) -> Optional[ChatMember]:
    try:
        me = await bot.me()
        return await bot.get_chat_member(chat_id=channel_id, user_id=me.id)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning("Failed to get bot status in channel %s: %s", channel_id, e)
        return None
    except Exception as e:  # pragma: no cover
        logger.exception("Unexpected error while checking bot status in channel %s: %s", channel_id, e)
        return None


async def can_manage_channel(bot: Bot, channel_id: int) -> bool:
    member = await get_bot_status_in_channel(bot, channel_id)
    if not member:
        return False

    can_invite = bool(getattr(member, "can_invite_users", False))
    can_restrict = bool(getattr(member, "can_restrict_members", False))
    return can_invite and can_restrict


async def get_all_admin_channels(bot: Bot) -> list[int]:
    """Best-effort list of channels where bot is admin.

    Telegram Bot API can't list all channels globally. We return only channels known to the bot
    (previously discovered / saved to DB) and validated via getChatMember.
    """

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT DISTINCT channel_id FROM channels") as cursor:
                rows = await cursor.fetchall()

        channel_ids = [int(r[0]) for r in rows]
        result: list[int] = []

        for channel_id in channel_ids:
            try:
                if await can_manage_channel(bot, channel_id):
                    result.append(channel_id)
            except Exception as e:
                logger.warning("Failed to validate admin channel %s: %s", channel_id, e)

        return result
    except Exception as e:
        logger.exception("Failed to list admin channels: %s", e)
        return []
