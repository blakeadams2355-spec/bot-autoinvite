from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from database import db
from keyboards import kb
from config import config
import asyncio
import time
import csv
import io
from datetime import datetime

router = Router()


class States(StatesGroup):
    waiting_accept_count = State()
    waiting_welcome = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# === Кэш ===
photo_cache: dict = {}
info_cache: dict = {}
CACHE_TTL = 300


async def download_channel_photo(bot: Bot, channel_id: int) -> bytes | None:
    try:
        chat = await bot.get_chat(channel_id)
        if chat.photo:
            file = await bot.get_file(chat.photo.big_file_id)
            photo_bytes = await bot.download_file(file.file_path)
            return photo_bytes.read()
    except Exception as e:
        print(f"❌ Ошибка скачивания фото: {e}")
    return None


async def get_channel_photo_bytes(bot: Bot, channel_id: int) -> bytes | None:
    now = time.time()
    cache_key = f"photo_{channel_id}"

    if cache_key in photo_cache:
        cached = photo_cache[cache_key]
        if cached.get('bytes') and now - cached['time'] < CACHE_TTL:
            return cached['bytes']

    photo_bytes = await download_channel_photo(bot, channel_id)

    if photo_bytes:
        photo_cache[cache_key] = {'bytes': photo_bytes, 'time': now}

    return photo_bytes


async def get_channel_info(bot: Bot, channel_id: int) -> dict:
    now = time.time()

    if channel_id in info_cache:
        cached = info_cache[channel_id]
        if now - cached['time'] < 60:
            return cached['data']

    try:
        chat = await bot.get_chat(channel_id)
        data = {
            'title': chat.title,
            'description': chat.description,
            'members_count': chat.member_count if hasattr(chat, 'member_count') else None,
        }
        info_cache[channel_id] = {'data': data, 'time': now}
    except:
        data = {'title': None, 'description': None, 'members_count': None}

    return data


def build_channel_text(title: str, description: str | None, members: int | None,
                       pending: int, accepted: int, auto_accept: bool) -> str:
    lines = [f"<b>{title}</b>", ""]

    if description:
        desc = description[:120] + "..." if len(description) > 120 else description
        lines.append(f"<blockquote>{desc}</blockquote>")
        lines.append("")

    if members:
        lines.append(f"👥 Подписчиков: <b>{members:,}</b>".replace(",", " "))
    lines.append(f"📬 Ожидают принятия: <b>{pending}</b>")
    lines.append(f"✅ Всего принято: <b>{accepted}</b>")

    lines.append("")
    lines.append("⚡ Авто-приём включён" if auto_accept else "✋ Ручной режим")

    return "\n".join(lines)


async def send_channel_card(callback: CallbackQuery, bot: Bot, channel_id: int):
    channel, pending_count, stats, info, photo_bytes = await asyncio.gather(
        db.get_channel(channel_id),
        db.get_pending_count(channel_id),
        db.get_total_stats(channel_id),
        get_channel_info(bot, channel_id),
        get_channel_photo_bytes(bot, channel_id)
    )

    if not channel:
        await callback.answer("❌ Канал не найден", show_alert=True)
        return

    title = info['title'] or channel['title']
    text = build_channel_text(
        title, info['description'], info['members_count'],
        pending_count, stats['total_accepted'], channel['auto_accept']
    )
    menu = kb.channel_menu(channel, pending_count)

    try:
        await callback.message.delete()
    except:
        pass

    if photo_bytes:
        try:
            photo = BufferedInputFile(photo_bytes, filename="photo.jpg")
            await callback.message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=menu)
            await callback.answer()
            return
        except Exception as e:
            print(f"❌ Ошибка отправки фото: {e}")

    await callback.message.answer(text, parse_mode="HTML", reply_markup=menu)
    await callback.answer()


async def update_channel_card(callback: CallbackQuery, bot: Bot, channel_id: int):
    channel, pending_count, stats, info = await asyncio.gather(
        db.get_channel(channel_id),
        db.get_pending_count(channel_id),
        db.get_total_stats(channel_id),
        get_channel_info(bot, channel_id)
    )

    if not channel:
        return

    title = info['title'] or channel['title']
    text = build_channel_text(
        title, info['description'], info['members_count'],
        pending_count, stats['total_accepted'], channel['auto_accept']
    )
    menu = kb.channel_menu(channel, pending_count)

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=menu)
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=menu)
    except:
        pass

    await callback.answer()


async def edit_menu(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except:
        pass
    await callback.answer()


async def send_new(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    await callback.answer()


# === Быстрые команды ===

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    channels = await db.get_all_channels()

    if not channels:
        await message.answer("📊 Нет каналов")
        return

    total_accepted = 0
    total_pending = 0
    lines = ["📊 <b>Статистика</b>", ""]

    for ch in channels:
        stats = await db.get_total_stats(ch['channel_id'])
        pending = await db.get_pending_count(ch['channel_id'])
        total_accepted += stats['total_accepted']
        total_pending += pending

        icon = "⚡" if ch['auto_accept'] else "✋"
        lines.append(f"{icon} <b>{ch['title'][:22]}</b>")
        lines.append(f"   📬 {pending} ожидают • ✅ {stats['total_accepted']} принято")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━",
        f"📬 Всего ожидают: <b>{total_pending}</b>",
        f"✅ Всего принято: <b>{total_accepted}</b>"
    ])

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("accept"))
async def cmd_accept(message: Message, bot: Bot):
    """Принятие: /accept <число> или /accept <число> <channel_id>"""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]

    if not args:
        # Показываем справку
        channels = await db.get_all_channels()

        lines = [
            "📋 <b>Использование:</b>",
            "",
            "<code>/accept 50</code> — принять 50 человек",
            "<code>/accept all</code> — принять всех",
            ""
        ]

        if len(channels) > 1:
            lines.append("<b>Для конкретного канала:</b>")
            lines.append("<code>/accept 50 ID_КАНАЛА</code>")
            lines.append("")
            lines.append("<b>Ваши каналы:</b>")
            for ch in channels:
                pending = await db.get_pending_count(ch['channel_id'])
                lines.append(f"• {ch['title'][:25]}")
                lines.append(f"  ID: <code>{ch['channel_id']}</code> ({pending} ожидают)")

        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Парсим количество
    count_str = args[0].lower()
    if count_str == "all":
        count = None
    elif count_str.isdigit():
        count = int(count_str)
        if count <= 0:
            await message.answer("❌ Число должно быть больше 0")
            return
    else:
        await message.answer("❌ Укажите число или 'all'")
        return

    # Определяем канал
    channels = await db.get_all_channels()

    if len(args) > 1:
        try:
            channel_id = int(args[1])
            channel = await db.get_channel(channel_id)
            if not channel:
                await message.answer("❌ Канал не найден")
                return
        except:
            await message.answer("❌ Неверный ID канала")
            return
    elif len(channels) == 1:
        channel = channels[0]
        channel_id = channel['channel_id']
    elif len(channels) == 0:
        await message.answer("❌ Нет добавленных каналов")
        return
    else:
        lines = ["📢 <b>Укажите канал:</b>", ""]
        for ch in channels:
            pending = await db.get_pending_count(ch['channel_id'])
            lines.append(f"<code>/accept {count_str} {ch['channel_id']}</code>")
            lines.append(f"   {ch['title'][:25]} ({pending} ожидают)")
            lines.append("")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Принимаем
    pending = await db.get_pending_requests(channel_id)

    if not pending:
        await message.answer("📭 Нет заявок в этом канале")
        return

    to_accept = pending if count is None else pending[:count]

    msg = await message.answer(f"⏳ Принимаю {len(to_accept)} из {len(pending)}...")

    success = 0
    for req in to_accept:
        try:
            await bot.approve_chat_join_request(channel_id, req['user_id'])
            await db.update_request(req['id'], 'accepted', message.from_user.id)
            await db.increment_accepted(channel_id)
            success += 1

            if channel.get('welcome_message'):
                try:
                    await bot.send_message(req['user_id'], channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass

    await db.update_stats(channel_id, accepted=success)

    if channel_id in info_cache:
        del info_cache[channel_id]

    remaining = len(pending) - success

    await msg.edit_text(
        f"✅ <b>Готово!</b>\n\n"
        f"📢 {channel['title']}\n"
        f"👥 Принято: <b>{success}</b>\n"
        f"📬 Осталось в очереди: <b>{remaining}</b>",
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = (
        "📋 <b>Команды</b>\n\n"

        "<b>Основные:</b>\n"
        "/start — главное меню\n"
        "/stats — статистика по каналам\n\n"

        "<b>Принятие:</b>\n"
        "/accept 50 — принять 50 человек\n"
        "/accept 100 — принять 100 человек\n"
        "/accept all — принять всех\n\n"

        "<b>Справка:</b>\n"
        "/help — список команд"
    )

    await message.answer(text, parse_mode="HTML")


# === Основные обработчики ===

@router.my_chat_member()
async def on_bot_added(update, bot: Bot):
    chat = update.chat
    status = update.new_chat_member.status

    if chat.type not in ['channel', 'supergroup']:
        return

    if status in ['administrator', 'member']:
        await db.save_discovered_channel(chat.id, chat.title)
    elif status in ['left', 'kicked']:
        await db.mark_channel_removed(chat.id)


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("👋 Бот для управления заявками.")
        return

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Управляйте заявками в каналы.",
        parse_mode="HTML",
        reply_markup=kb.main_menu()
    )


@router.callback_query(F.data == "menu")
async def main_menu(callback: CallbackQuery):
    await send_new(callback, "🏠 <b>Главное меню</b>", kb.main_menu())


@router.callback_query(F.data == "channels")
async def channels_list(callback: CallbackQuery):
    channels = await db.get_all_channels()
    text = f"📢 <b>Каналы</b> ({len(channels)})" if channels else "📢 <b>Нет каналов</b>"
    await send_new(callback, text, kb.channels_list(channels))


@router.callback_query(F.data == "add_channel")
async def add_channel_menu(callback: CallbackQuery, bot: Bot):
    active_ids = {ch['channel_id'] for ch in await db.get_all_channels()}
    discovered = await db.get_discovered_channels()

    available = []
    for ch in discovered:
        if ch['channel_id'] in active_ids:
            continue
        try:
            member = await bot.get_chat_member(ch['channel_id'], bot.id)
            if member.status == 'administrator' and getattr(member, 'can_invite_users', False):
                chat = await bot.get_chat(ch['channel_id'])
                available.append({'id': ch['channel_id'], 'title': chat.title})
        except:
            continue

    builder = InlineKeyboardBuilder()

    if available:
        text = "📢 <b>Выберите канал</b>"
        for ch in available:
            builder.row(InlineKeyboardButton(text=f"➕ {ch['title'][:35]}", callback_data=f"add:{ch['id']}"))
    else:
        text = "📢 <b>Нет каналов</b>\n\nДобавьте бота админом."

    builder.row(InlineKeyboardButton(text="← Назад", callback_data="channels"))
    await send_new(callback, text, builder.as_markup())


@router.callback_query(F.data.startswith("add:"))
async def add_channel(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])

    try:
        chat = await bot.get_chat(channel_id)
        await db.add_channel(channel_id, chat.title)

        cache_key = f"photo_{channel_id}"
        if cache_key in photo_cache:
            del photo_cache[cache_key]
        if channel_id in info_cache:
            del info_cache[channel_id]

        await callback.answer("✅ Добавлено!")
        await send_channel_card(callback, bot, channel_id)
    except Exception as e:
        await callback.answer(f"❌ {str(e)[:50]}", show_alert=True)


@router.callback_query(F.data.startswith("ch:"))
async def channel_callback(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])
    await send_channel_card(callback, bot, channel_id)


@router.callback_query(F.data.startswith("auto:"))
async def toggle_auto(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    await db.update_channel(channel_id, auto_accept=not channel['auto_accept'])
    await update_channel_card(callback, bot, channel_id)


@router.callback_query(F.data.startswith("accept_menu:"))
async def accept_menu(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    pending = await db.get_pending_count(channel_id)

    if pending == 0:
        await callback.answer("📭 Нет заявок", show_alert=True)
        return

    text = f"👥 <b>Принять пользователей</b>\n\nОжидают: <b>{pending}</b>"
    await edit_menu(callback, text, kb.accept_menu(channel_id, pending))


@router.callback_query(F.data.startswith("accept:"))
async def accept_users(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    channel_id = int(parts[1])
    count = parts[2]

    pending = await db.get_pending_requests(channel_id)
    if not pending:
        await callback.answer("📭 Нет заявок", show_alert=True)
        return

    to_accept = pending if count == "all" else pending[:int(count)]
    await callback.answer(f"⏳ Принимаю {len(to_accept)}...")

    success = 0
    channel = await db.get_channel(channel_id)

    for req in to_accept:
        try:
            await bot.approve_chat_join_request(channel_id, req['user_id'])
            await db.update_request(req['id'], 'accepted', callback.from_user.id)
            await db.increment_accepted(channel_id)
            success += 1

            if channel.get('welcome_message'):
                try:
                    await bot.send_message(req['user_id'], channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass

    await db.update_stats(channel_id, accepted=success)

    if channel_id in info_cache:
        del info_cache[channel_id]

    await update_channel_card(callback, bot, channel_id)


@router.callback_query(F.data.startswith("accept_custom:"))
async def accept_custom(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    pending = await db.get_pending_count(channel_id)

    await state.update_data(channel_id=channel_id)
    await state.set_state(States.waiting_accept_count)
    await edit_menu(callback, f"✏️ Введите число (доступно: {pending}):", kb.back(f"accept_menu:{channel_id}"))


@router.message(States.waiting_accept_count)
async def process_accept_count(message: Message, state: FSMContext, bot: Bot):
    try:
        count = int(message.text)
        assert count > 0
    except:
        await message.answer("❌ Введите число > 0")
        return

    data = await state.get_data()
    channel_id = data['channel_id']
    await state.clear()

    pending = await db.get_pending_requests(channel_id)
    to_accept = pending[:count]

    msg = await message.answer(f"⏳ Принимаю {len(to_accept)}...")

    success = 0
    channel = await db.get_channel(channel_id)

    for req in to_accept:
        try:
            await bot.approve_chat_join_request(channel_id, req['user_id'])
            await db.update_request(req['id'], 'accepted', message.from_user.id)
            await db.increment_accepted(channel_id)
            success += 1

            if channel.get('welcome_message'):
                try:
                    await bot.send_message(req['user_id'], channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass

    await db.update_stats(channel_id, accepted=success)
    await msg.delete()

    if channel_id in info_cache:
        del info_cache[channel_id]

    channel = await db.get_channel(channel_id)
    pending_count = await db.get_pending_count(channel_id)
    await message.answer(f"✅ Принято: {success}", reply_markup=kb.channel_menu(channel, pending_count))


# === Пиковые часы (inline кнопка в меню канала) ===

@router.callback_query(F.data.startswith("peak:"))
async def peak_hours(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])

    hour_stats = await db.get_hourly_stats(channel_id)

    if not hour_stats:
        await callback.answer("📊 Недостаточно данных", show_alert=True)
        return

    total = sum(hour_stats.values())
    sorted_hours = sorted(hour_stats.items(), key=lambda x: x[1], reverse=True)

    lines = ["📈 <b>Пиковые часы подачи заявок</b>", ""]

    # Топ-5 часов
    lines.append("<b>🔥 Самые активные:</b>")
    for hour, count in sorted_hours[:5]:
        percent = (count / total * 100) if total > 0 else 0
        bar_len = int(percent / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"<code>{hour:02d}:00</code> {bar} {count}")

    lines.append("")

    # По времени суток
    periods = {
        "🌅 Утро (6-12)": sum(hour_stats.get(h, 0) for h in range(6, 12)),
        "☀️ День (12-18)": sum(hour_stats.get(h, 0) for h in range(12, 18)),
        "🌆 Вечер (18-24)": sum(hour_stats.get(h, 0) for h in range(18, 24)),
        "🌙 Ночь (0-6)": sum(hour_stats.get(h, 0) for h in range(0, 6)),
    }

    lines.append("<b>📊 По времени суток:</b>")
    for period, count in periods.items():
        percent = (count / total * 100) if total > 0 else 0
        lines.append(f"{period}: {count} ({percent:.0f}%)")

    lines.extend(["", f"📝 Всего заявок: <b>{total}</b>"])

    await edit_menu(callback, "\n".join(lines), kb.back(f"ch:{channel_id}"))


# === Экспорт в CSV (inline кнопка в меню канала) ===

@router.callback_query(F.data.startswith("export:"))
async def export_csv(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    if not channel:
        await callback.answer("❌ Канал не найден", show_alert=True)
        return

    # Получаем все заявки канала
    all_requests = await db.get_all_requests(channel_id)
    stats = await db.get_total_stats(channel_id)
    pending = await db.get_pending_count(channel_id)

    # Создаём CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Заголовки
    writer.writerow([
        "ID пользователя", "Username", "Имя", "Статус",
        "Дата заявки", "Дата обработки"
    ])

    for req in all_requests:
        writer.writerow([
            req['user_id'],
            req['username'] or "",
            req['full_name'] or "",
            req['status'],
            req['created_at'],
            req['processed_at'] or ""
        ])

    # Добавляем сводку
    writer.writerow([])
    writer.writerow(["=== СВОДКА ==="])
    writer.writerow(["Канал", channel['title']])
    writer.writerow(["Всего принято", stats['total_accepted']])
    writer.writerow(["Ожидают", pending])
    writer.writerow(["Дата экспорта", datetime.now().strftime("%Y-%m-%d %H:%M")])

    output.seek(0)
    csv_bytes = output.getvalue().encode('utf-8-sig')

    filename = f"{channel['title'][:20]}_{datetime.now().strftime('%Y%m%d')}.csv"
    # Убираем недопустимые символы из имени файла
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")

    file = BufferedInputFile(csv_bytes, filename=filename)

    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer_document(
        file,
        caption=f"📊 <b>Экспорт: {channel['title']}</b>\n\n"
                f"✅ Принято: {stats['total_accepted']}\n"
                f"📬 Ожидают: {pending}",
        parse_mode="HTML",
        reply_markup=kb.back(f"ch:{channel_id}")
    )
    await callback.answer()


# === Приветствие ===

@router.callback_query(F.data.startswith("welcome:"))
async def welcome_menu(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    current = channel.get('welcome_message')

    if current:
        text = f"✉️ <b>Приветствие</b>\n\n<blockquote>{current[:400]}</blockquote>"
    else:
        text = "✉️ <b>Не установлено</b>"

    await edit_menu(callback, text, kb.welcome_menu(channel_id, bool(current)))


@router.callback_query(F.data.startswith("welcome_edit:"))
async def welcome_edit(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    await state.update_data(channel_id=channel_id)
    await state.set_state(States.waiting_welcome)
    await edit_menu(callback, "✏️ Отправьте текст или /cancel", kb.back(f"welcome:{channel_id}"))


@router.callback_query(F.data.startswith("welcome_del:"))
async def welcome_delete(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])
    await db.update_channel(channel_id, welcome_message=None)
    await callback.answer("🗑 Удалено")
    await update_channel_card(callback, bot, channel_id)


@router.message(States.waiting_welcome)
async def process_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data['channel_id']
    await state.clear()

    if message.text != "/cancel":
        await db.update_channel(channel_id, welcome_message=message.text)
        await message.answer("✅ Сохранено!")
    else:
        await message.answer("❌ Отменено")

    channel = await db.get_channel(channel_id)
    pending = await db.get_pending_count(channel_id)
    await message.answer("📢 Канал:", reply_markup=kb.channel_menu(channel, pending))


# === Статистика ===

@router.callback_query(F.data == "stats_menu")
async def stats_menu(callback: CallbackQuery):
    channels = await db.get_all_channels()

    if not channels:
        await callback.answer("Нет каналов", show_alert=True)
        return

    total = 0
    lines = ["📊 <b>Статистика</b>", ""]

    for ch in channels:
        stats = await db.get_total_stats(ch['channel_id'])
        total += stats['total_accepted']
        lines.append(f"• {ch['title'][:25]}: <b>{stats['total_accepted']}</b>")

    lines.extend(["", f"📈 Всего: <b>{total}</b>"])

    await send_new(callback, "\n".join(lines), kb.back("menu"))


@router.callback_query(F.data.startswith("stat:"))
async def channel_stats(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    stats = await db.get_total_stats(channel_id)

    text = f"📊 <b>{channel['title']}</b>\n\n✅ Принято: <b>{stats['total_accepted']}</b>"
    await edit_menu(callback, text, kb.back(f"ch:{channel_id}"))


# === Настройки ===

@router.callback_query(F.data.startswith("more:"))
async def more_settings(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    await edit_menu(callback, "⚙️ <b>Настройки</b>", kb.more_settings(channel))


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_active(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    await db.update_channel(channel_id, is_active=not channel['is_active'])
    await callback.answer("🟢 Активен" if not channel['is_active'] else "🔴 Неактивен")

    channel = await db.get_channel(channel_id)
    await edit_menu(callback, "⚙️ <b>Настройки</b>", kb.more_settings(channel))


@router.callback_query(F.data.startswith("del:"))
async def delete_channel(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    await edit_menu(callback, f"🗑 Удалить <b>{channel['title']}</b>?", kb.confirm("del", str(channel_id)))


@router.callback_query(F.data.startswith("yes_del:"))
async def confirm_delete(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    await db.update_channel(channel_id, is_active=False)
    await callback.answer("✅ Удалено")

    channels = await db.get_all_channels()
    await send_new(callback, f"📢 <b>Каналы</b> ({len(channels)})", kb.channels_list(channels))


@router.callback_query(F.data.startswith("no_"))
async def cancel_action(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    if len(parts) > 1:
        await update_channel_card(callback, bot, int(parts[1]))
    else:
        await callback.answer("❌ Отменено")


# === FAQ ===

@router.callback_query(F.data == "faq")
async def faq_menu(callback: CallbackQuery):
    await send_new(callback, "❓ <b>FAQ — Справочник</b>\n\nВыберите тему для подробной информации:", kb.faq_menu())


@router.callback_query(F.data.startswith("faq:"))
async def faq_topic(callback: CallbackQuery):
    topic = callback.data.split(":")[1]

    topics = {
        "channels": (
            "📢 <b>Управление каналами</b>\n\n"
            "<b>Что это:</b>\n"
            "Раздел для добавления и управления вашими приватными каналами. "
            "Бот может работать с несколькими каналами одновременно.\n\n"

            "<b>Как добавить канал:</b>\n"
            "1. Откройте ваш приватный канал в Telegram\n"
            "2. Перейдите в Настройки → Администраторы\n"
            "3. Добавьте этого бота как администратора\n"
            "4. Обязательно дайте право «Приглашение пользователей»\n"
            "5. Вернитесь в бота: Каналы → Добавить\n"
            "6. Выберите канал из списка\n\n"

            "<b>Иконки статуса:</b>\n"
            "⚡ — авто-приём включён (заявки принимаются автоматически)\n"
            "🟢 — ручной режим (вы сами решаете кого принять)\n"
            "🔴 — канал деактивирован (заявки не обрабатываются)"
        ),

        "auto": (
            "⚡ <b>Авто-приём заявок</b>\n\n"
            "<b>Что это:</b>\n"
            "Режим автоматического одобрения всех входящих заявок на вступление в канал.\n\n"

            "<b>Когда авто-приём ВКЛЮЧЁН:</b>\n"
            "• Все новые заявки принимаются мгновенно\n"
            "• Новые участники сразу получают приветственное сообщение\n"
            "• Вам не нужно ничего делать вручную\n"
            "• Идеально для открытых наборов\n\n"

            "<b>Когда авто-приём ВЫКЛЮЧЕН:</b>\n"
            "• Заявки накапливаются в очереди ожидания\n"
            "• Вы полностью контролируете кого и когда принять\n"
            "• Можно принимать по расписанию или вручную\n"
            "• Подходит для контролируемых наборов\n\n"

            "<b>Как переключить:</b>\n"
            "Нажмите кнопку «⚡ Авто: ВКЛ» или «✋ Авто: ВЫКЛ» в меню канала."
        ),

        "accept": (
            "👥 <b>Принятие заявок вручную</b>\n\n"
            "<b>Что это:</b>\n"
            "Функция для ручного одобрения заявок когда авто-приём выключен.\n\n"

            "<b>Способы принятия:</b>\n\n"
            "1️⃣ <b>Через меню (кнопки):</b>\n"
            "• «Принять всех» — одобрить все заявки\n"
            "• Быстрые кнопки: 5, 10, 25, 50, 100...\n"
            "• «Своё число» — ввести любое количество\n\n"

            "2️⃣ <b>Через команду:</b>\n"
            "• <code>/accept 50</code> — принять 50 человек\n"
            "• <code>/accept 100</code> — принять 100 человек\n"
            "• <code>/accept all</code> — принять всех\n\n"

            "<b>Важно знать:</b>\n"
            "• Заявки обрабатываются в порядке поступления (FIFO)\n"
            "• Повторные заявки от одного человека игнорируются\n"
            "• После принятия участникам отправляется приветствие\n"
            "• Статистика обновляется автоматически"
        ),

        "schedule": (
            "⏰ <b>Расписание автоприёма</b>\n\n"
            "<b>Что это:</b>\n"
            "Автоматический приём заявок по заданному расписанию. "
            "Бот сам будет принимать людей в указанное время.\n\n"

            "<b>Настройки расписания:</b>\n\n"
            "📅 <b>Дни недели</b>\n"
            "Выберите в какие дни работает расписание.\n"
            "Можно выбрать отдельные дни или все сразу.\n\n"

            "🕐 <b>Время</b>\n"
            "Укажите во сколько принимать заявки.\n"
            "Доступны готовые варианты или своё время.\n\n"

            "👥 <b>Количество</b>\n"
            "Сколько человек принимать за один раз:\n"
            "• «Всех» — все накопившиеся заявки\n"
            "• Число — только указанное количество\n\n"

            "<b>Пример использования:</b>\n"
            "Пн, Ср, Пт в 12:00 принимать по 50 человек.\n"
            "Это создаст контролируемый набор с равномерным притоком.\n\n"

            "<b>Важно:</b>\n"
            "Расписание работает независимо от режима авто-приёма."
        ),

        "welcome": (
            "✉️ <b>Приветственное сообщение</b>\n\n"
            "<b>Что это:</b>\n"
            "Сообщение, которое автоматически отправляется каждому "
            "новому участнику сразу после принятия в канал.\n\n"

            "<b>Возможности:</b>\n"
            "• Поддержка HTML-форматирования\n"
            "• Ссылки, эмодзи, форматирование текста\n"
            "• Можно изменить или удалить в любой момент\n\n"

            "<b>Пример приветствия:</b>\n"
            "<code>🎉 Добро пожаловать в наш канал!\n\n"
            "📌 Правила: ссылка\n"
            "💬 Чат: @chat</code>\n\n"

            "<b>Поддерживаемые теги:</b>\n"
            "<code>&lt;b&gt;жирный&lt;/b&gt;</code>\n"
            "<code>&lt;i&gt;курсив&lt;/i&gt;</code>\n"
            "<code>&lt;a href=\"url\"&gt;ссылка&lt;/a&gt;</code>\n\n"

            "<b>Если приветствие не установлено:</b>\n"
            "Новые участники не получают никаких сообщений от бота."
        ),

        "stats": (
            "📊 <b>Статистика и аналитика</b>\n\n"
            "<b>Что это:</b>\n"
            "Раздел для отслеживания активности ваших каналов.\n\n"

            "<b>Доступные метрики:</b>\n\n"
            "👥 <b>Подписчиков</b>\n"
            "Текущее количество участников в канале.\n"
            "Данные берутся напрямую из Telegram.\n\n"

            "📬 <b>Ожидают принятия</b>\n"
            "Количество заявок в очереди на одобрение.\n"
            "Актуально для ручного режима.\n\n"

            "✅ <b>Всего принято</b>\n"
            "Сколько человек было принято через бота.\n"
            "Считается с момента добавления канала.\n\n"

            "<b>📈 Пиковые часы:</b>\n"
            "Анализ в какое время суток поступает больше всего заявок.\n"
            "Помогает оптимизировать расписание приёма.\n\n"

            "<b>📥 Экспорт в CSV:</b>\n"
            "Выгрузка всех данных в файл для анализа в Excel.\n"
            "Содержит список всех заявок с датами и статусами.\n\n"

            "<b>Команда /stats:</b>\n"
            "Быстрый просмотр статистики по всем каналам."
        )
    }

    text = topics.get(topic, "Раздел не найден")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.faq_back())
    except:
        pass

    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()