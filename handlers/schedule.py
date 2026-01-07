from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import kb

router = Router()


class ScheduleStates(StatesGroup):
    waiting_time = State()
    waiting_count = State()


DAYS_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_schedule_info(schedule: dict) -> str:
    """Форматирование информации о расписании"""
    if not schedule:
        return "Расписание не настроено"

    days = schedule.get('days', [])
    time = schedule.get('time', '12:00')
    count = schedule.get('count', 'all')

    if len(days) == 7:
        days_str = "Каждый день"
    elif len(days) == 5 and all(d in days for d in [0, 1, 2, 3, 4]):
        days_str = "Будни (Пн-Пт)"
    elif len(days) == 2 and all(d in days for d in [5, 6]):
        days_str = "Выходные (Сб-Вс)"
    elif days:
        days_str = ", ".join(DAYS_NAMES[d] for d in sorted(days))
    else:
        days_str = "Дни не выбраны"

    count_str = "всех" if count == 'all' else f"{count} чел."

    return f"📅 {days_str}\n🕐 В {time}\n👥 Принимать: {count_str}"


async def edit_msg(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "schedule_menu")
async def schedule_menu_global(callback: CallbackQuery):
    """Общее меню расписания"""
    channels = await db.get_all_channels()

    if not channels:
        await callback.answer("Нет каналов", show_alert=True)
        return

    lines = ["⏰ <b>Расписание по каналам</b>", ""]

    for ch in channels:
        sched = ch.get('schedule', {})
        status = "🟢" if sched and sched.get('enabled') else "🔴"
        lines.append(f"{status} <b>{ch['title'][:25]}</b>")

        if sched and sched.get('enabled'):
            lines.append(f"   {format_schedule_info(sched)}")
        lines.append("")

    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.back("menu"))
    await callback.answer()


@router.callback_query(F.data.startswith("schedule:"))
async def schedule_menu(callback: CallbackQuery):
    """Меню расписания для канала"""
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    sched = channel.get('schedule', {})

    # Формируем текст без статуса (он в кнопке)
    if sched and sched.get('enabled'):
        text = f"⏰ <b>Расписание</b>\n\n{format_schedule_info(sched)}"
    else:
        text = "⏰ <b>Расписание</b>\n\nНастройте автоматический приём заявок по времени."

    await edit_msg(callback, text, kb.schedule_channel_menu(channel_id, sched))


@router.callback_query(F.data.startswith("sched_toggle:"))
async def toggle_schedule(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    sched = channel.get('schedule') or {}
    sched['enabled'] = not sched.get('enabled', False)

    if 'days' not in sched:
        sched['days'] = list(range(7))
    if 'time' not in sched:
        sched['time'] = '12:00'
    if 'count' not in sched:
        sched['count'] = 'all'

    await db.update_channel(channel_id, schedule=sched)

    status = "🟢 Расписание включено" if sched['enabled'] else "🔴 Расписание выключено"
    await callback.answer(status)

    if sched['enabled']:
        text = f"⏰ <b>Расписание</b>\n\n{format_schedule_info(sched)}"
    else:
        text = "⏰ <b>Расписание</b>\n\nНастройте автоматический приём заявок по времени."

    await edit_msg(callback, text, kb.schedule_channel_menu(channel_id, sched))


@router.callback_query(F.data.startswith("sched_days:"))
async def schedule_days(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    sched = channel.get('schedule') or {}
    selected = sched.get('days', [])

    text = "📅 <b>Выберите дни</b>\n\nНажмите на день чтобы включить/выключить:"
    await edit_msg(callback, text, kb.schedule_days(channel_id, selected))


@router.callback_query(F.data.startswith("sched_day:"))
async def toggle_day(callback: CallbackQuery):
    parts = callback.data.split(":")
    channel_id = int(parts[1])
    day = parts[2]

    channel = await db.get_channel(channel_id)
    sched = channel.get('schedule') or {}
    days = sched.get('days', [])

    if day == 'all':
        days = list(range(7))
    else:
        day_num = int(day)
        if day_num in days:
            days.remove(day_num)
        else:
            days.append(day_num)

    sched['days'] = days
    await db.update_channel(channel_id, schedule=sched)

    await edit_msg(callback, "📅 <b>Выберите дни</b>\n\nНажмите на день чтобы включить/выключить:",
                   kb.schedule_days(channel_id, days))


@router.callback_query(F.data.startswith("sched_time:"))
async def schedule_time(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    sched = channel.get('schedule') or {}
    current = sched.get('time', '12:00')

    text = f"🕐 <b>Время приёма</b>\n\nТекущее: <b>{current}</b>\n\nВыберите новое время:"
    await edit_msg(callback, text, kb.schedule_time_options(channel_id))


@router.callback_query(F.data.startswith("sched_settime:"))
async def set_time(callback: CallbackQuery):
    parts = callback.data.split(":")
    channel_id = int(parts[1])
    time = parts[2]

    channel = await db.get_channel(channel_id)
    sched = channel.get('schedule') or {}
    sched['time'] = time

    await db.update_channel(channel_id, schedule=sched)
    await callback.answer(f"✅ Установлено: {time}")

    text = f"⏰ <b>Расписание</b>\n\n{format_schedule_info(sched)}" if sched.get('enabled') else "⏰ <b>Расписание</b>"
    await edit_msg(callback, text, kb.schedule_channel_menu(channel_id, sched))


@router.callback_query(F.data.startswith("sched_customtime:"))
async def custom_time(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])

    await state.update_data(channel_id=channel_id)
    await state.set_state(ScheduleStates.waiting_time)

    await edit_msg(callback, "🕐 <b>Введите время</b>\n\nФормат: ЧЧ:ММ\nНапример: 14:30",
                   kb.back(f"sched_time:{channel_id}"))


@router.message(ScheduleStates.waiting_time)
async def process_time(message: Message, state: FSMContext):
    text = message.text.strip()

    try:
        parts = text.split(":")
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
        time = f"{h:02d}:{m:02d}"
    except:
        await message.answer("❌ Неверный формат. Используйте ЧЧ:ММ (например 14:30)")
        return

    data = await state.get_data()
    channel_id = data['channel_id']
    await state.clear()

    channel = await db.get_channel(channel_id)
    sched = channel.get('schedule') or {}
    sched['time'] = time

    await db.update_channel(channel_id, schedule=sched)

    await message.answer(f"✅ Время установлено: {time}", reply_markup=kb.schedule_channel_menu(channel_id, sched))


@router.callback_query(F.data.startswith("sched_count:"))
async def schedule_count(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    sched = channel.get('schedule') or {}
    current = sched.get('count', 'all')
    current_str = "всех" if current == 'all' else str(current)

    text = f"👥 <b>Количество за раз</b>\n\nТекущее: <b>{current_str}</b>\n\nСколько человек принимать по расписанию:"
    await edit_msg(callback, text, kb.schedule_count_options(channel_id))


@router.callback_query(F.data.startswith("sched_setcount:"))
async def set_count(callback: CallbackQuery):
    parts = callback.data.split(":")
    channel_id = int(parts[1])
    count = parts[2]

    if count != 'all':
        count = int(count)

    channel = await db.get_channel(channel_id)
    sched = channel.get('schedule') or {}
    sched['count'] = count

    await db.update_channel(channel_id, schedule=sched)

    count_str = "всех" if count == 'all' else str(count)
    await callback.answer(f"✅ Установлено: {count_str}")

    text = f"⏰ <b>Расписание</b>\n\n{format_schedule_info(sched)}" if sched.get('enabled') else "⏰ <b>Расписание</b>"
    await edit_msg(callback, text, kb.schedule_channel_menu(channel_id, sched))


@router.callback_query(F.data.startswith("sched_customcount:"))
async def custom_count(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])

    await state.update_data(channel_id=channel_id)
    await state.set_state(ScheduleStates.waiting_count)

    await edit_msg(callback, "👥 <b>Введите количество</b>\n\nСколько человек принимать за раз:",
                   kb.back(f"sched_count:{channel_id}"))


@router.message(ScheduleStates.waiting_count)
async def process_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        assert count > 0
    except:
        await message.answer("❌ Введите положительное число")
        return

    data = await state.get_data()
    channel_id = data['channel_id']
    await state.clear()

    channel = await db.get_channel(channel_id)
    sched = channel.get('schedule') or {}
    sched['count'] = count

    await db.update_channel(channel_id, schedule=sched)

    await message.answer(f"✅ Установлено: {count} чел.", reply_markup=kb.schedule_channel_menu(channel_id, sched))