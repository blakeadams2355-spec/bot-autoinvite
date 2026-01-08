import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from database import db
from handlers import admin, requests, schedule

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def scheduled_accept(bot: Bot):
    """Автоматический приём по расписанию"""
    now = datetime.now()
    current_day = now.weekday()
    current_time = now.strftime("%H:%M")

    channels = await db.get_channels_with_schedule()

    for channel in channels:
        sched = channel.get('schedule', {})

        if not sched.get('enabled'):
            continue

        days = sched.get('days', [])
        time = sched.get('time', '12:00')
        count = sched.get('count', 'all')

        # Проверяем день и время
        if current_day not in days:
            continue

        if current_time != time:
            continue

        # Получаем заявки
        pending = await db.get_pending_requests(channel['channel_id'])

        if not pending:
            continue

        to_accept = pending if count == 'all' else pending[:count]

        success = 0
        for req in to_accept:
            try:
                await bot.approve_chat_join_request(channel['channel_id'], req['user_id'])
                await db.update_request(req['id'], 'accepted', 0)
                await db.increment_accepted(channel['channel_id'])
                success += 1

                if channel.get('welcome_message'):
                    try:
                        await bot.send_message(req['user_id'], channel['welcome_message'], parse_mode="HTML")
                    except:
                        pass
            except:
                pass

        if success > 0:
            await db.update_stats(channel['channel_id'], accepted=success)
            logger.info(f"Расписание: принято {success} в {channel['title']}")


async def main():
    if not config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен")
        return

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(requests.router)
    dp.include_router(schedule.router)

    await db.init()
    logger.info("✅ БД готова")

    # Запускаем планировщик (проверка каждую минуту)
    scheduler.add_job(scheduled_accept, 'cron', minute='*', args=[bot])
    scheduler.start()
    logger.info("✅ Планировщик запущен")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        info = await bot.get_me()
        logger.info(f"🚀 @{info.username} запущен")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())