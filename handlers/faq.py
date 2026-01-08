from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.channel_menu import get_faq_menu

logger = logging.getLogger(__name__)

router = Router()

FAQ_TOPICS = {
    "connect": {
        "title": "🔌 Как подключить бота",
        "content": (
            "1) Добавьте бота в ваш канал.\n"
            "2) Выдайте боту админские права: \n"
            "   • Приглашать пользователей\n"
            "   • Банить/ограничивать пользователей\n"
            "3) Перейдите в бот и нажмите «➕ Добавить канал».\n"
            "4) Выберите канал из списка — после этого бот начнет учитывать заявки.\n\n"
            "Если канал не появился в списке — проверьте, что бот действительно администратор, "
            "и нажмите «Попробовать снова»."
        ),
    },
    "auto": {
        "title": "🤖 Как работает автопринятие",
        "content": (
            "Когда включено автопринятие, бот автоматически обрабатывает новые заявки на вступление.\n\n"
            "• Если у бота есть права — заявка будет одобрена сразу.\n"
            "• Если бот потерял права или Telegram вернул ошибку — заявка будет сохранена как «pending», "
            "чтобы вы могли принять ее вручную или по расписанию.\n\n"
            "Рекомендуется включать автопринятие только если вы уверены в правах бота и настройках канала."
        ),
    },
    "schedule": {
        "title": "📅 Настройка расписания",
        "content": (
            "Расписание позволяет принимать заявки автоматически в выбранное время.\n\n"
            "Как настроить:\n"
            "1) Откройте меню канала\n"
            "2) Нажмите «📅 По расписанию»\n"
            "3) Выберите дату, затем время, затем количество заявок (всех или N)\n"
            "4) Нажмите «Сохранить»\n\n"
            "В момент выполнения бот возьмет все «pending» заявки по этому каналу и попытается их одобрить."
        ),
    },
}

_TOPIC_ORDER = ["connect", "auto", "schedule"]


async def show_faq_menu(callback_query: CallbackQuery) -> None:
    try:
        await callback_query.message.edit_text("❓ FAQ\n\nВыберите тему:", reply_markup=get_faq_menu())
    except TelegramBadRequest:
        pass
    await callback_query.answer()


def _topic_nav_keyboard(topic: str) -> InlineKeyboardMarkup:
    idx = _TOPIC_ORDER.index(topic)
    prev_topic = _TOPIC_ORDER[idx - 1] if idx > 0 else _TOPIC_ORDER[-1]
    next_topic = _TOPIC_ORDER[idx + 1] if idx < len(_TOPIC_ORDER) - 1 else _TOPIC_ORDER[0]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️", callback_data=f"faq_topic:{prev_topic}"),
                InlineKeyboardButton(text="▶️", callback_data=f"faq_topic:{next_topic}"),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="faq")],
        ]
    )


async def show_faq_topic(callback_query: CallbackQuery, topic: str) -> None:
    item = FAQ_TOPICS.get(topic)
    if not item:
        await callback_query.answer("Тема не найдена")
        return

    text = f"{item['title']}\n\n{item['content']}"
    try:
        await callback_query.message.edit_text(text, reply_markup=_topic_nav_keyboard(topic))
    except TelegramBadRequest as e:
        logger.debug("FAQ edit failed: %s", e)

    await callback_query.answer()


@router.callback_query(F.data.startswith("faq_topic:"))
async def faq_topic_handler(callback_query: CallbackQuery) -> None:
    topic = callback_query.data.split(":", 1)[1]
    await show_faq_topic(callback_query, topic)
