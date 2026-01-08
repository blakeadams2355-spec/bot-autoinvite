from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatJoinRequest

from database.operations import add_join_request, get_channel_by_id, update_statistics

logger = logging.getLogger(__name__)

router = Router()


@router.chat_join_request()
async def handle_chat_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    channel_id = event.chat.id
    user_id = event.from_user.id

    try:
        channel = await get_channel_by_id(channel_id)
        if not channel or not bool(channel.get("is_active")):
            return

        auto_approve = bool(channel.get("auto_approve"))

        user_name = event.from_user.full_name
        if event.from_user.username:
            user_name = f"{user_name} (@{event.from_user.username})"

        if auto_approve:
            try:
                await bot.approve_chat_join_request(chat_id=channel_id, user_id=user_id)
                await update_statistics(channel_id, "approve")
                logger.info("Auto-approved join request: channel=%s user=%s", channel_id, user_id)
            except (TelegramForbiddenError, TelegramBadRequest) as e:
                logger.warning(
                    "Auto-approve failed: channel=%s user=%s error=%s. Saving as pending.",
                    channel_id,
                    user_id,
                    e,
                )
                await add_join_request(channel_id, user_id, user_name)
            except Exception as e:  # pragma: no cover
                logger.exception("Unexpected error in auto-approve: %s", e)
                await add_join_request(channel_id, user_id, user_name)
        else:
            await add_join_request(channel_id, user_id, user_name)
            logger.info("Stored pending join request: channel=%s user=%s", channel_id, user_id)

    except Exception as e:  # pragma: no cover
        logger.exception("handle_chat_join_request failed: %s", e)
        return
