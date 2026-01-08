from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from config import BOT_TOKEN, LOG_LEVEL, TIMEZONE
from database.models import init_database
from database.operations import get_pending_scheduled_tasks
from handlers import get_routers
from scheduler.tasks import scheduler_job_wrapper
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(LOG_LEVEL)

    await init_database()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    for r in get_routers():
        dp.include_router(r)

    try:
        timezone = ZoneInfo(TIMEZONE)
    except Exception:
        logger.warning("Invalid TIMEZONE '%s', falling back to UTC", TIMEZONE)
        timezone = ZoneInfo("UTC")

    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.start()

    dp.workflow_data.update({"scheduler": scheduler})

    pending_tasks = await get_pending_scheduled_tasks()
    now = datetime.now(tz=timezone)

    for task in pending_tasks:
        task_id = int(task["id"])
        channel_id = int(task["channel_id"])
        run_dt = task.get("scheduled_time")
        user_count = task.get("user_count")
        user_count_int = int(user_count) if user_count is not None else None

        if isinstance(run_dt, str):
            try:
                run_dt = datetime.fromisoformat(run_dt)
            except Exception:
                run_dt = now

        if run_dt.tzinfo is None:
            run_dt = run_dt.replace(tzinfo=timezone)

        if run_dt < now:
            run_dt = now + timedelta(seconds=5)

        job_id = f"task_{task_id}"

        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            scheduler_job_wrapper,
            trigger="date",
            run_date=run_dt,
            args=[channel_id, user_count_int, bot, task_id],
            id=job_id,
            replace_existing=True,
        )

    try:
        await dp.start_polling(bot)
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning("Failed to shutdown scheduler: %s", e)

        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
