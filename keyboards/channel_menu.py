from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_channel_menu(channel_name: str, auto_approve: bool, channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    auto_text = "🟢 Автопринятие: ВКЛ" if auto_approve else "🔴 Автопринятие: ВЫКЛ"
    builder.button(text=auto_text, callback_data=f"toggle_auto:{channel_id}")
    builder.button(text="✋ Ручной режим", callback_data=f"manual:{channel_id}")
    builder.button(text="📅 По расписанию", callback_data=f"schedule:{channel_id}")
    builder.button(text="📊 Статистика", callback_data=f"stats_menu:{channel_id}")
    builder.button(text="❌ Отключить канал", callback_data=f"disable:{channel_id}")
    builder.button(text="🗑 Удалить канал", callback_data=f"delete_confirm:{channel_id}")
    builder.button(text="← Назад в главное меню", callback_data="back_main")

    builder.adjust(1)
    return builder.as_markup()


def get_manual_mode_menu(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Принять одного", callback_data=f"approve_one:{channel_id}")
    builder.button(text="✅ Принять всех", callback_data=f"approve_all:{channel_id}")
    builder.button(text="🔢 Принять N", callback_data=f"approve_n:{channel_id}")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_schedule_menu(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Выбрать дату", callback_data=f"schedule_date:{channel_id}")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_date_picker(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Завтра", callback_data=f"sched_date:{channel_id}:tomorrow")
    builder.button(text="+1 день", callback_data=f"sched_date:{channel_id}:1")
    builder.button(text="+2 дня", callback_data=f"sched_date:{channel_id}:2")
    builder.button(text="+7 дней", callback_data=f"sched_date:{channel_id}:7")
    builder.button(text="Пользовательская", callback_data=f"sched_date:{channel_id}:custom")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_time_picker(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in ["09:00", "12:00", "15:00", "18:00", "21:00"]:
        builder.button(text=t, callback_data=f"sched_time:{channel_id}:{t}")
    builder.button(text="Другое", callback_data=f"sched_time:{channel_id}:custom")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(3, 2, 1, 1)
    return builder.as_markup()


def get_count_picker(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Всех", callback_data=f"sched_count:{channel_id}:all")
    builder.button(text="Ввести число", callback_data=f"sched_count:{channel_id}:custom")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_statistics_menu(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📆 День", callback_data=f"stats:{channel_id}:day")
    builder.button(text="📅 Неделя", callback_data=f"stats:{channel_id}:week")
    builder.button(text="📊 Месяц", callback_data=f"stats:{channel_id}:month")
    builder.button(text="📈 Год", callback_data=f"stats:{channel_id}:year")
    builder.button(text="⏱ Всё время", callback_data=f"stats:{channel_id}:all")
    builder.button(text="← Назад", callback_data=f"channel_menu:{channel_id}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_faq_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔌 Как подключить", callback_data="faq_topic:connect")
    builder.button(text="🤖 Как работает", callback_data="faq_topic:auto")
    builder.button(text="📅 Расписание", callback_data="faq_topic:schedule")
    builder.button(text="← Назад", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()
