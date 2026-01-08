from __future__ import annotations

import logging
from datetime import datetime, time as time_type, timedelta
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from config import TIMEZONE
from database.operations import (
    approve_request,
    delete_channel,
    disable_channel as db_disable_channel,
    get_channel_by_id,
    get_last_scheduled_task_id,
    get_pending_requests,
    get_statistics,
    reject_request,
    schedule_task,
    toggle_auto_approve as db_toggle_auto_approve,
    update_statistics,
)
from keyboards.channel_menu import (
    get_channel_menu,
    get_count_picker,
    get_date_picker,
    get_manual_mode_menu,
    get_statistics_menu,
    get_time_picker,
)
from keyboards.main_menu import get_main_menu
from scheduler.tasks import scheduler_job_wrapper

logger = logging.getLogger(__name__)

router = Router()


class ApproveNStates(StatesGroup):
    waiting_number = State()


class ScheduleStates(StatesGroup):
    waiting_custom_date = State()
    waiting_custom_time = State()
    waiting_custom_count = State()


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


async def _safe_edit(
    callback_query: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    try:
        await callback_query.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("Failed to edit message: %s", e)


async def _remember_menu_message(callback_query: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        menu_chat_id=callback_query.message.chat.id,
        menu_message_id=callback_query.message.message_id,
    )


async def _edit_menu_from_state(
    bot: Bot,
    state: FSMContext,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    data = await state.get_data()
    chat_id = data.get("menu_chat_id")
    message_id = data.get("menu_message_id")

    if not chat_id or not message_id:
        return False

    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("Failed to edit menu message: %s", e)
        return False


@router.callback_query(F.data.startswith("toggle_auto:"))
async def toggle_auto_approve(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    ch = await get_channel_by_id(channel_id)
    if not ch:
        await callback_query.answer("Канал не найден")
        return

    enabled = not bool(ch.get("auto_approve"))

    ok = await db_toggle_auto_approve(channel_id, enabled)
    if not ok:
        await callback_query.answer("Не удалось обновить настройку")
        return

    ch = await get_channel_by_id(channel_id)
    title = (ch or {}).get("channel_title") or (ch or {}).get("channel_name") or str(channel_id)
    auto_approve = bool((ch or {}).get("auto_approve"))

    await _safe_edit(
        callback_query,
        f"📣 Канал: {title}\nID: {channel_id}\nАвтопринятие: {'ВКЛ' if auto_approve else 'ВЫКЛ'}",
        reply_markup=get_channel_menu(title, auto_approve, channel_id),
    )
    await callback_query.answer("Готово")


@router.callback_query(F.data.startswith("manual:"))
async def show_manual_mode_menu(callback_query: CallbackQuery, state: FSMContext) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await state.clear()
    await _remember_menu_message(callback_query, state)

    await _safe_edit(
        callback_query,
        "✋ Ручной режим\n\nВыберите действие:",
        reply_markup=get_manual_mode_menu(channel_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("approve_one:"))
async def approve_one(callback_query: CallbackQuery, bot: Bot) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    pending = await get_pending_requests(channel_id)
    if not pending:
        await _safe_edit(
            callback_query,
            "✅ Очередь пуста — нет заявок на одобрение.",
            reply_markup=get_manual_mode_menu(channel_id),
        )
        await callback_query.answer()
        return

    req = pending[0]
    user_id = int(req["user_id"])
    request_id = int(req["id"])
    user_name = req.get("user_name") or str(user_id)

    try:
        await bot.approve_chat_join_request(chat_id=channel_id, user_id=user_id)
        await approve_request(request_id)
        await update_statistics(channel_id, "approve")
        result_text = f"✅ Одобрено: {user_name}"
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.warning("Approve one failed: channel=%s user=%s error=%s", channel_id, user_id, e)
        await reject_request(request_id)
        result_text = (
            "⚠️ Не удалось одобрить заявку (возможно, бот потерял права или заявка устарела). "
            "Переходим к следующей."
        )
    except Exception as e:  # pragma: no cover
        logger.exception("Unexpected approve_one error: %s", e)
        result_text = "⚠️ Ошибка при обработке заявки."

    pending_next = await get_pending_requests(channel_id)
    if pending_next:
        next_user = pending_next[0].get("user_name") or str(pending_next[0].get("user_id"))
        result_text += f"\n\nСледующая заявка: {next_user}"
    else:
        result_text += "\n\nОчередь пуста."

    await _safe_edit(callback_query, result_text, reply_markup=get_manual_mode_menu(channel_id))
    await callback_query.answer()


@router.callback_query(F.data.startswith("approve_all:"))
async def approve_all(callback_query: CallbackQuery, bot: Bot) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    pending = await get_pending_requests(channel_id)
    if not pending:
        await _safe_edit(
            callback_query,
            "✅ Очередь пуста — нет заявок на одобрение.",
            reply_markup=get_manual_mode_menu(channel_id),
        )
        await callback_query.answer()
        return

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
            logger.warning("Approve all failed for one: channel=%s user=%s error=%s", channel_id, user_id, e)
        except Exception as e:  # pragma: no cover
            logger.exception("Unexpected error approving request: %s", e)

    await _safe_edit(
        callback_query,
        f"✅ Одобрено {approved_ok} заявок.",
        reply_markup=get_manual_mode_menu(channel_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("approve_n:"))
async def approve_n_start(callback_query: CallbackQuery, state: FSMContext) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await state.clear()
    await _remember_menu_message(callback_query, state)
    await state.update_data(channel_id=channel_id)
    await state.set_state(ApproveNStates.waiting_number)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"manual:{channel_id}")]]
    )

    await _safe_edit(callback_query, "🔢 Введите число N (сколько заявок одобрить):", reply_markup=markup)
    await callback_query.answer()


@router.message(ApproveNStates.waiting_number)
async def approve_n_process(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    channel_id = int(data.get("channel_id", 0))

    try:
        n = int((message.text or "").strip())
    except Exception:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"manual:{channel_id}")]]
        )
        await _edit_menu_from_state(bot, state, "Введите целое число.", reply_markup=markup)
        return

    if n <= 0:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"manual:{channel_id}")]]
        )
        await _edit_menu_from_state(bot, state, "Число должно быть больше 0.", reply_markup=markup)
        return

    pending = await get_pending_requests(channel_id)
    to_process = pending[:n]

    approved_ok = 0

    for req in to_process:
        user_id = int(req["user_id"])
        request_id = int(req["id"])

        try:
            await bot.approve_chat_join_request(chat_id=channel_id, user_id=user_id)
            await approve_request(request_id)
            await update_statistics(channel_id, "approve")
            approved_ok += 1
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning("Approve N failed: channel=%s user=%s error=%s", channel_id, user_id, e)
        except Exception as e:  # pragma: no cover
            logger.exception("Unexpected error in approve N: %s", e)

    text = f"✅ Одобрено {approved_ok} заявок из {len(to_process)}."

    await _edit_menu_from_state(bot, state, text, reply_markup=get_manual_mode_menu(channel_id))
    await state.clear()


@router.callback_query(F.data.startswith("schedule:"))
async def show_schedule_menu(callback_query: CallbackQuery, state: FSMContext) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await state.clear()
    await _remember_menu_message(callback_query, state)
    await state.update_data(channel_id=channel_id)

    await _safe_edit(
        callback_query,
        "📅 Расписание\n\nВыберите дату выполнения:",
        reply_markup=get_date_picker(channel_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("sched_date:"))
async def select_date(callback_query: CallbackQuery, state: FSMContext) -> None:
    parts = callback_query.data.split(":")
    if len(parts) < 3:
        await callback_query.answer()
        return

    channel_id = int(parts[1])
    choice = parts[2]

    await _remember_menu_message(callback_query, state)
    await state.update_data(channel_id=channel_id)

    today = datetime.now(tz=_tz()).date()

    if choice == "tomorrow":
        selected = today + timedelta(days=1)
    elif choice == "custom":
        await state.set_state(ScheduleStates.waiting_custom_date)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _safe_edit(
            callback_query,
            "Введите дату в формате YYYY-MM-DD (например, 2026-01-30):",
            reply_markup=markup,
        )
        await callback_query.answer()
        return
    else:
        try:
            delta = int(choice)
        except Exception:
            delta = 1
        selected = today + timedelta(days=max(delta, 0))

    await state.update_data(schedule_date=selected.isoformat())

    await _safe_edit(
        callback_query,
        f"Выбрана дата: {selected.isoformat()}\n\nТеперь выберите время:",
        reply_markup=get_time_picker(channel_id),
    )
    await callback_query.answer()


@router.message(ScheduleStates.waiting_custom_date)
async def schedule_custom_date(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    channel_id = int(data.get("channel_id", 0))

    text = (message.text or "").strip()
    try:
        selected = datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _edit_menu_from_state(
            bot,
            state,
            "Некорректный формат. Введите дату как YYYY-MM-DD.",
            reply_markup=markup,
        )
        return

    await state.update_data(schedule_date=selected.isoformat())
    await state.set_state(None)

    await _edit_menu_from_state(
        bot,
        state,
        f"Выбрана дата: {selected.isoformat()}\n\nТеперь выберите время:",
        reply_markup=get_time_picker(channel_id),
    )


@router.callback_query(F.data.startswith("sched_time:"))
async def select_time(callback_query: CallbackQuery, state: FSMContext) -> None:
    parts = callback_query.data.split(":")
    if len(parts) < 3:
        await callback_query.answer()
        return

    channel_id = int(parts[1])
    choice = parts[2]

    await _remember_menu_message(callback_query, state)
    await state.update_data(channel_id=channel_id)

    if choice == "custom":
        await state.set_state(ScheduleStates.waiting_custom_time)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _safe_edit(
            callback_query,
            "Введите время в формате HH:MM (например, 18:30):",
            reply_markup=markup,
        )
        await callback_query.answer()
        return

    await state.update_data(schedule_time=choice)

    await _safe_edit(
        callback_query,
        f"Выбрано время: {choice}\n\nТеперь выберите количество заявок:",
        reply_markup=get_count_picker(channel_id),
    )
    await callback_query.answer()


@router.message(ScheduleStates.waiting_custom_time)
async def schedule_custom_time(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    channel_id = int(data.get("channel_id", 0))

    text = (message.text or "").strip()

    try:
        datetime.strptime(text, "%H:%M")
    except Exception:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _edit_menu_from_state(
            bot,
            state,
            "Некорректный формат. Введите время как HH:MM.",
            reply_markup=markup,
        )
        return

    await state.update_data(schedule_time=text)
    await state.set_state(None)

    await _edit_menu_from_state(
        bot,
        state,
        f"Выбрано время: {text}\n\nТеперь выберите количество заявок:",
        reply_markup=get_count_picker(channel_id),
    )


@router.callback_query(F.data.startswith("sched_count:"))
async def select_count(callback_query: CallbackQuery, state: FSMContext) -> None:
    parts = callback_query.data.split(":")
    if len(parts) < 3:
        await callback_query.answer()
        return

    channel_id = int(parts[1])
    choice = parts[2]

    await _remember_menu_message(callback_query, state)
    await state.update_data(channel_id=channel_id)

    if choice == "custom":
        await state.set_state(ScheduleStates.waiting_custom_count)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _safe_edit(callback_query, "Введите число (сколько заявок одобрить):", reply_markup=markup)
        await callback_query.answer()
        return

    await state.update_data(user_count=None)

    await _show_schedule_confirmation(callback_query, state, channel_id)
    await callback_query.answer()


@router.message(ScheduleStates.waiting_custom_count)
async def schedule_custom_count(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    channel_id = int(data.get("channel_id", 0))

    text = (message.text or "").strip()

    try:
        count = int(text)
    except Exception:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _edit_menu_from_state(bot, state, "Введите целое число.", reply_markup=markup)
        return

    if count <= 0:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")]]
        )
        await _edit_menu_from_state(bot, state, "Число должно быть больше 0.", reply_markup=markup)
        return

    await state.update_data(user_count=count)
    await state.set_state(None)

    schedule_data = await state.get_data()
    schedule_date_str = schedule_data.get("schedule_date")
    schedule_time_str = schedule_data.get("schedule_time")

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Сохранить", callback_data=f"sched_save:{channel_id}")],
            [InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")],
        ]
    )

    await _edit_menu_from_state(
        bot,
        state,
        f"📅 План: {schedule_date_str} {schedule_time_str}\nКоличество: {count}\n\nСохранить задачу?",
        reply_markup=markup,
    )


async def _show_schedule_confirmation(callback_query: CallbackQuery, state: FSMContext, channel_id: int) -> None:
    data = await state.get_data()

    schedule_date_str = data.get("schedule_date")
    schedule_time_str = data.get("schedule_time")
    user_count = data.get("user_count")

    if not schedule_date_str or not schedule_time_str:
        await _safe_edit(
            callback_query,
            "⚠️ Не удалось собрать данные расписания. Начните заново.",
            reply_markup=get_date_picker(channel_id),
        )
        return

    count_text = "все" if user_count is None else str(user_count)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Сохранить", callback_data=f"sched_save:{channel_id}")],
            [InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")],
        ]
    )

    await _safe_edit(
        callback_query,
        f"📅 План: {schedule_date_str} {schedule_time_str}\nКоличество: {count_text}\n\nСохранить задачу?",
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("sched_save:"))
async def save_schedule(
    callback_query: CallbackQuery,
    state: FSMContext,
    scheduler: AsyncIOScheduler,
    bot: Bot,
) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await _remember_menu_message(callback_query, state)

    data = await state.get_data()
    schedule_date_str = data.get("schedule_date")
    schedule_time_str = data.get("schedule_time")

    if not schedule_date_str or not schedule_time_str:
        await callback_query.answer("Нет данных расписания")
        return

    selected_date = datetime.fromisoformat(schedule_date_str).date()

    try:
        hh, mm = schedule_time_str.split(":")
        selected_time = time_type(hour=int(hh), minute=int(mm))
    except Exception:
        await callback_query.answer("Некорректное время")
        return

    user_count = data.get("user_count")
    user_count_int: Optional[int] = int(user_count) if user_count is not None else None

    run_dt = datetime.combine(selected_date, selected_time).replace(tzinfo=_tz())

    action_type = "approve_all" if user_count_int is None else "approve_n"

    ok = await schedule_task(channel_id, action_type, run_dt, user_count_int)
    if not ok:
        await callback_query.answer("Не удалось сохранить задачу")
        return

    task_id = await get_last_scheduled_task_id(channel_id, run_dt)
    if task_id is None:
        await callback_query.answer("Не удалось получить ID задачи")
        return

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

    ch = await get_channel_by_id(channel_id)
    title = (ch or {}).get("channel_title") or (ch or {}).get("channel_name") or str(channel_id)
    auto_approve = bool((ch or {}).get("auto_approve"))

    await state.clear()

    await _safe_edit(
        callback_query,
        f"✅ Задача сохранена и будет выполнена: {run_dt.isoformat()}\n"
        f"Количество: {'все' if user_count_int is None else user_count_int}",
        reply_markup=get_channel_menu(title, auto_approve, channel_id),
    )
    await callback_query.answer("Сохранено")


@router.callback_query(F.data.startswith("stats_menu:"))
async def show_statistics_menu(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await _safe_edit(
        callback_query,
        "📊 Статистика\n\nВыберите период:",
        reply_markup=get_statistics_menu(channel_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("stats:"))
async def show_statistics(callback_query: CallbackQuery) -> None:
    parts = callback_query.data.split(":")
    if len(parts) < 3:
        await callback_query.answer()
        return

    channel_id = int(parts[1])
    period = parts[2]

    approved, rejected = await get_statistics(channel_id, period)

    period_name = {
        "day": "день",
        "week": "неделю",
        "month": "месяц",
        "year": "год",
        "all": "всё время",
    }.get(period, period)

    text = (
        f"📊 Статистика за {period_name}:\n"
        f"Принято: {approved} ✅\n"
        f"Отклонено: {rejected} ❌"
    )

    await _safe_edit(callback_query, text, reply_markup=get_statistics_menu(channel_id))
    await callback_query.answer()


@router.callback_query(F.data.startswith("disable:"))
async def disable_channel(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    ok = await db_disable_channel(channel_id)
    if not ok:
        await callback_query.answer("Не удалось отключить канал")
        return

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад в главное меню", callback_data="back_main")],
            [InlineKeyboardButton(text="➕ Добавить канал (включить)", callback_data="add_channel")],
        ]
    )

    await _safe_edit(callback_query, "❌ Канал отключен. Заявки будут игнорироваться.", reply_markup=markup)
    await callback_query.answer("Отключено")


@router.callback_query(F.data.startswith("delete_confirm:"))
async def delete_channel_confirm(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data=f"delete_yes:{channel_id}")],
            [InlineKeyboardButton(text="❌ Нет", callback_data=f"channel_menu:{channel_id}")],
        ]
    )

    await _safe_edit(callback_query, "🗑 Вы уверены, что хотите удалить канал?", reply_markup=markup)
    await callback_query.answer()


@router.callback_query(F.data.startswith("delete_yes:"))
async def delete_channel_confirmed(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    ok = await delete_channel(channel_id)
    if not ok:
        await callback_query.answer("Не удалось удалить канал")
        return

    await _safe_edit(callback_query, "✅ Канал удалён.", reply_markup=get_main_menu())
    await callback_query.answer("Удалено")
