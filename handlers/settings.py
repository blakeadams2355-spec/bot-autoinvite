from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import kb

router = Router()


class SettingsStates(StatesGroup):
    waiting_batch_count = State()
    waiting_welcome = State()
    waiting_bl_user = State()
    waiting_bl_reason = State()


async def safe_edit_or_send(callback: CallbackQuery, text: str, reply_markup=None):
    """Безопасное редактирование или отправка сообщения"""
    try:
        # Пробуем редактировать caption (для фото)
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except:
        try:
            # Пробуем редактировать текст
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except:
            # Удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )


# ==========================================
# Авто-приём
# ==========================================

@router.callback_query(F.data.startswith("toggle_auto:"))
async def toggle_auto(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    new_value = not channel['auto_accept']
    await db.update_channel(channel_id, auto_accept=new_value)

    status = "включён ⚡" if new_value else "выключен ✋"
    await callback.answer(f"Авто-приём {status}")

    from handlers.admin import show_channel_card
    await show_channel_card(callback, bot, channel_id)


# ==========================================
# Принять N человек
# ==========================================

@router.callback_query(F.data.startswith("set_batch:"))
async def set_batch_menu(callback: CallbackQuery):
    """Меню выбора количества для приёма"""
    channel_id = int(callback.data.split(":")[1])

    pending = await db.get_pending_requests(channel_id)
    pending_count = len(pending)

    if pending_count == 0:
        await callback.answer("📭 Нет ожидающих заявок", show_alert=True)
        return

    text = (
        f"👥 <b>Принять пользователей</b>\n\n"
        f"Ожидают одобрения: <b>{pending_count}</b>\n\n"
        f"Выберите сколько принять:"
    )

    await safe_edit_or_send(callback, text, kb.batch_options(channel_id, pending_count))


@router.callback_query(F.data.startswith("batch:"))
async def process_batch(callback: CallbackQuery, bot: Bot):
    """Принять выбранное количество"""
    parts = callback.data.split(":")
    channel_id = int(parts[1])
    count = parts[2]

    pending = await db.get_pending_requests(channel_id)

    if not pending:
        await callback.answer("📭 Нет заявок", show_alert=True)
        return

    if count == "all":
        to_accept = pending
    else:
        to_accept = pending[:int(count)]

    await safe_edit_or_send(callback, f"⏳ Принимаю {len(to_accept)} заявок...", None)

    success = 0
    channel = await db.get_channel(channel_id)

    for req in to_accept:
        try:
            await bot.approve_chat_join_request(
                chat_id=channel_id,
                user_id=req['user_id']
            )
            await db.update_request(req['id'], 'accepted', callback.from_user.id)
            await db.increment_accepted(channel_id)
            success += 1

            if channel and channel.get('welcome_message'):
                try:
                    await bot.send_message(
                        req['user_id'],
                        channel['welcome_message'],
                        parse_mode="HTML"
                    )
                except:
                    pass
        except:
            pass

    await db.update_stats(channel_id, accepted=success)

    await callback.answer(f"✅ Принято: {success}")

    from handlers.admin import show_channel_card
    await show_channel_card(callback, bot, channel_id)


@router.callback_query(F.data.startswith("batch_custom:"))
async def batch_custom(callback: CallbackQuery, state: FSMContext):
    """Ввод своего количества"""
    channel_id = int(callback.data.split(":")[1])

    pending = await db.get_pending_requests(channel_id)

    await state.update_data(channel_id=channel_id)
    await state.set_state(SettingsStates.waiting_batch_count)

    text = (
        f"✏️ <b>Введите количество</b>\n\n"
        f"Ожидают: {len(pending)}\n"
        f"Отправьте число от 1 до {len(pending)}:"
    )

    await safe_edit_or_send(callback, text, kb.back_button(f"set_batch:{channel_id}"))


@router.message(SettingsStates.waiting_batch_count)
async def process_batch_count(message: Message, state: FSMContext, bot: Bot):
    """Обработка введённого количества"""
    try:
        count = int(message.text)
        if count < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число")
        return

    data = await state.get_data()
    channel_id = data['channel_id']

    pending = await db.get_pending_requests(channel_id)

    if count > len(pending):
        count = len(pending)

    await state.clear()

    msg = await message.answer(f"⏳ Принимаю {count} заявок...")

    success = 0
    channel = await db.get_channel(channel_id)

    for req in pending[:count]:
        try:
            await bot.approve_chat_join_request(
                chat_id=channel_id,
                user_id=req['user_id']
            )
            await db.update_request(req['id'], 'accepted', message.from_user.id)
            await db.increment_accepted(channel_id)
            success += 1

            if channel and channel.get('welcome_message'):
                try:
                    await bot.send_message(req['user_id'], channel['welcome_message'], parse_mode="HTML")
                except:
                    pass
        except:
            pass

    await db.update_stats(channel_id, accepted=success)

    try:
        await msg.delete()
    except:
        pass

    channel = await db.get_channel(channel_id)
    await message.answer(
        f"✅ <b>Принято: {success}</b>",
        parse_mode="HTML",
        reply_markup=kb.channel_menu(channel)
    )


# ==========================================
# Приветственное сообщение
# ==========================================

@router.callback_query(F.data.startswith("welcome:"))
async def welcome_menu(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    current = channel.get('welcome_message') or 'Не установлено'

    await state.update_data(channel_id=channel_id)
    await state.set_state(SettingsStates.waiting_welcome)

    text = (
        f"✉️ <b>Приветственное сообщение</b>\n\n"
        f"<i>Текущее:</i>\n{current[:500]}\n\n"
        f"Отправьте новое сообщение\n"
        f"или /skip для отмены:"
    )

    await safe_edit_or_send(callback, text, kb.back_button(f"channel:{channel_id}"))


@router.message(SettingsStates.waiting_welcome)
async def process_welcome(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    channel_id = data['channel_id']

    if message.text != "/skip":
        await db.update_channel(channel_id, welcome_message=message.text)
        await message.answer("✅ Приветствие обновлено!")
    else:
        await message.answer("❌ Отменено")

    await state.clear()

    channel = await db.get_channel(channel_id)
    await message.answer(
        f"📢 <b>{channel['title']}</b>",
        parse_mode="HTML",
        reply_markup=kb.channel_menu(channel)
    )


# ==========================================
# Списки (ЧС и белый)
# ==========================================

@router.callback_query(F.data.startswith("lists:"))
async def lists_menu(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])

    bl = await db.get_blacklist(channel_id)
    wl = await db.get_whitelist(channel_id)

    text = (
        f"🔒 <b>Списки доступа</b>\n\n"
        f"⚫ Чёрный список: {len(bl)} чел.\n"
        f"⚪ Белый список: {len(wl)} чел."
    )

    await safe_edit_or_send(callback, text, kb.lists_menu(channel_id))


@router.callback_query(F.data.startswith("blacklist:"))
async def show_blacklist(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    users = await db.get_blacklist(channel_id)

    if users:
        text = f"⚫ <b>Чёрный список</b>\n\nВсего: {len(users)}"
    else:
        text = "⚫ <b>Чёрный список пуст</b>"

    await safe_edit_or_send(callback, text, kb.blacklist_view(users, channel_id))


@router.callback_query(F.data.startswith("whitelist:"))
async def show_whitelist(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    users = await db.get_whitelist(channel_id)

    if users:
        text = f"⚪ <b>Белый список</b>\n\nВсего: {len(users)}"
    else:
        text = "⚪ <b>Белый список пуст</b>"

    await safe_edit_or_send(callback, text, kb.whitelist_view(users, channel_id))


@router.callback_query(F.data.startswith("bl_add:"))
async def bl_add(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])

    await state.update_data(channel_id=channel_id)
    await state.set_state(SettingsStates.waiting_bl_user)

    text = "🚫 <b>Добавление в ЧС</b>\n\nОтправьте ID пользователя\nили перешлите его сообщение:"

    await safe_edit_or_send(callback, text, kb.back_button(f"blacklist:{channel_id}"))


@router.message(SettingsStates.waiting_bl_user)
async def process_bl_user(message: Message, state: FSMContext):
    user_id = None

    if message.forward_from:
        user_id = message.forward_from.id
    else:
        try:
            user_id = int(message.text)
        except:
            await message.answer("❌ Неверный формат")
            return

    await state.update_data(bl_user=user_id)
    await state.set_state(SettingsStates.waiting_bl_reason)

    await message.answer(
        f"👤 ID: <code>{user_id}</code>\n\nУкажите причину (или /skip):",
        parse_mode="HTML"
    )


@router.message(SettingsStates.waiting_bl_reason)
async def process_bl_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data['channel_id']
    user_id = data['bl_user']
    reason = message.text if message.text != "/skip" else "Не указана"

    await db.add_to_blacklist(user_id, channel_id, reason, message.from_user.id)
    await state.clear()

    await message.answer(f"✅ Пользователь {user_id} добавлен в ЧС")

    users = await db.get_blacklist(channel_id)

    await message.answer(
        f"⚫ <b>Чёрный список</b>\n\nВсего: {len(users)}",
        parse_mode="HTML",
        reply_markup=kb.blacklist_view(users, channel_id)
    )


@router.callback_query(F.data.startswith("bl_remove:"))
async def bl_remove(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id, channel_id = int(parts[1]), int(parts[2])

    await db.remove_from_blacklist(user_id, channel_id)
    await callback.answer("✅ Удалён из ЧС")

    users = await db.get_blacklist(channel_id)

    text = f"⚫ <b>Чёрный список</b>\n\nВсего: {len(users)}" if users else "⚫ <b>Чёрный список пуст</b>"

    await safe_edit_or_send(callback, text, kb.blacklist_view(users, channel_id))


@router.callback_query(F.data.startswith("wl_remove:"))
async def wl_remove(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id, channel_id = int(parts[1]), int(parts[2])

    await db.remove_from_whitelist(user_id, channel_id)
    await callback.answer("✅ Удалён из белого списка")

    users = await db.get_whitelist(channel_id)

    text = f"⚪ <b>Белый список</b>\n\nВсего: {len(users)}" if users else "⚪ <b>Белый список пуст</b>"

    await safe_edit_or_send(callback, text, kb.whitelist_view(users, channel_id))


# ==========================================
# Дополнительные настройки
# ==========================================

@router.callback_query(F.data.startswith("advanced:"))
async def advanced_settings(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    await safe_edit_or_send(callback, "⚙️ <b>Дополнительные настройки</b>", kb.advanced_settings(channel))


@router.callback_query(F.data.startswith("toggle_active:"))
async def toggle_active(callback: CallbackQuery, bot: Bot):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)

    new_value = not channel['is_active']
    await db.update_channel(channel_id, is_active=new_value)

    status = "активирован 🟢" if new_value else "деактивирован 🔴"
    await callback.answer(f"Канал {status}")

    channel = await db.get_channel(channel_id)
    await safe_edit_or_send(callback, "⚙️ <b>Дополнительные настройки</b>", kb.advanced_settings(channel))


@router.callback_query(F.data.startswith("stats:"))
async def channel_stats(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await db.get_channel(channel_id)
    stats = await db.get_total_stats(channel_id)

    text = (
        f"📊 <b>Статистика канала</b>\n\n"
        f"📢 {channel['title']}\n\n"
        f"✅ Всего принято: <b>{stats['total_accepted']}</b>"
    )

    await safe_edit_or_send(callback, text, kb.back_button(f"channel:{channel_id}"))