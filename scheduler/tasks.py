from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database.operations import (
    approve_request,
    get_pending_requests,
    mark_task_executed,
    update_statistics,
)

logger = logging.getLogger(__name__)


async def approve_scheduled_requests(channel_id: int, user_count: Optional[int], bot: Bot) -> None:
    pending = await get_pending_requests(channel_id)

    if user_count is not None:
        pending = pending[: max(user_count, 0)]

    approved_ok = 0

    for req in pending:
        user_id = int(req["user_id"])
        request_id = int(req["id"])

        try:
            await bot.approve_chat_join_request(chat_id=channel_id, user_id=user_id)
            await approve_request(request_id)
            await update_statistics(channel_id, "approve")
            approved_ok += 1
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning(
                "Scheduled approve failed: channel=%s user=%s request=%s error=%s",
                channel_id,
                user_id,
                request_id,
                e,
            )
        except Exception as e:  # pragma: no cover
            logger.exception(
                "Unexpected error in scheduled approve: channel=%s user=%s request=%s error=%s",
                channel_id,
                user_id,
                request_id,
                e,
            )

    logger.info(
        "Scheduled approval executed: channel=%s approved=%s total_candidates=%s",
        channel_id,
        approved_ok,
        len(pending),
    )


async def scheduler_job_wrapper(channel_id: int, user_count: Optional[int], bot: Bot, task_id: int) -> None:
    try:
        await approve_scheduled_requests(channel_id, user_count, bot)
    finally:
        await mark_task_executed(task_id)
