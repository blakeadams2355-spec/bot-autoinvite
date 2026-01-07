from aiogram import Router, F, Bot
from aiogram.types import ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest
from database import db
from config import config

router = Router()


@router.chat_join_request()
async def handle_join_request(request: ChatJoinRequest, bot: Bot):
    """Обработка заявки на вступление"""
    channel_id = request.chat.id
    user_id = request.from_user.id
    username = request.from_user.username
    full_name = request.from_user.full_name

    # Получаем настройки канала
    channel = await db.get_channel(channel_id)

    if not channel:
        await db.add_channel(channel_id, request.chat.title)
        channel = await db.get_channel(channel_id)

    # Проверка чёрного списка
    if await db.is_blacklisted(user_id, channel_id):
        try:
            await request.decline()
        except:
            pass
        return

    # Проверка белого списка
    if await db.is_whitelisted(user_id, channel_id):
        try:
            await request.approve()
            await db.increment_accepted(channel_id)
            await db.update_stats(channel_id, accepted=1)

            if channel.get('welcome_message'):
                try:
                    await bot.send_message(user_id, channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass
        return

    # Сохраняем заявку
    req_id = await db.add_request(user_id, username, full_name, channel_id)

    # Автоприём
    if channel['auto_accept']:
        try:
            await request.approve()
            await db.increment_accepted(channel_id)
            await db.update_request(req_id, 'accepted', 0)
            await db.update_stats(channel_id, accepted=1)

            if channel.get('welcome_message'):
                try:
                    await bot.send_message(user_id, channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass