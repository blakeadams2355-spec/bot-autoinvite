from __future__ import annotations

import logging
from typing import List

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from database.operations import (
    add_channel,
    disable_channel as db_disable_channel,
    get_channel_by_id,
    get_channels_by_user,
    upsert_discovered_channel,
)
from keyboards.channel_menu import get_channel_menu
from keyboards.utils import paginate_channels
from utils.permissions import can_manage_channel

logger = logging.getLogger(__name__)

router = Router()


def _append_back_to_main(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    markup.inline_keyboard.append([InlineKeyboardButton(text="← Назад", callback_data="back_main")])
    return markup


async def get_managed_channels(bot: Bot, user_id: int) -> List[dict]:
    channels = await get_channels_by_user(user_id)
    candidates = [c for c in channels if not bool(c.get("is_active"))]

    result: List[dict] = []
    for ch in candidates:
        try:
            if await validate_channel_permissions(bot, int(ch["channel_id"])):
                result.append(ch)
        except Exception as e:
            logger.warning("Failed to validate channel %s: %s", ch.get("channel_id"), e)

    return result


async def validate_channel_permissions(bot: Bot, channel_id: int) -> bool:
    return await can_manage_channel(bot, channel_id)


async def handle_add_channel(callback_query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(list_mode="add", page=0)

    channels = await get_managed_channels(bot, callback_query.from_user.id)

    if not channels:
        text = (
            "➕ Добавление канала\n\n"
            "Чтобы я мог принимать заявки, сначала добавьте меня в канал и выдайте админские права:\n"
            "• Приглашать пользователей\n"
            "• Банить/ограничивать пользователей\n\n"
            "После этого снова нажмите «Добавить канал»."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="add_channel")],
                [InlineKeyboardButton(text="← Назад", callback_data="back_main")],
            ]
        )
        try:
            await callback_query.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
        await callback_query.answer()
        return

    markup = _append_back_to_main(paginate_channels(channels, page=0, per_page=5))

    try:
        await callback_query.message.edit_text(
            "Выберите канал из списка (это каналы, где бот уже администратор):",
            reply_markup=markup,
        )
    except TelegramBadRequest:
        pass

    await callback_query.answer()


async def show_user_channels(callback_query: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(list_mode="settings", page=0)

    channels = [c for c in await get_channels_by_user(callback_query.from_user.id) if bool(c.get("is_active"))]

    if not channels:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
                [InlineKeyboardButton(text="← Назад", callback_data="back_main")],
            ]
        )
        try:
            await callback_query.message.edit_text(
                "⚙️ Настройки\n\nУ вас пока нет активных каналов. Добавьте канал:",
                reply_markup=markup,
            )
        except TelegramBadRequest:
            pass
        await callback_query.answer()
        return

    markup = _append_back_to_main(paginate_channels(channels, page=0, per_page=5))

    try:
        await callback_query.message.edit_text(
            "⚙️ Настройки\n\nВыберите канал:",
            reply_markup=markup,
        )
    except TelegramBadRequest:
        pass

    await callback_query.answer()


@router.callback_query(F.data.startswith("channels_page:"))
async def handle_channels_page(callback_query: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    list_mode = data.get("list_mode")

    try:
        page = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    if list_mode == "add":
        channels = await get_managed_channels(callback_query.bot, callback_query.from_user.id)
        title = "Выберите канал из списка (это каналы, где бот уже администратор):"
    else:
        channels = [
            c
            for c in await get_channels_by_user(callback_query.from_user.id)
            if bool(c.get("is_active"))
        ]
        title = "⚙️ Настройки\n\nВыберите канал:"

    markup = _append_back_to_main(paginate_channels(channels, page=page, per_page=5))

    try:
        await callback_query.message.edit_text(title, reply_markup=markup)
    except TelegramBadRequest:
        pass

    await callback_query.answer()


@router.callback_query(F.data.startswith("channel_select:"))
async def handle_channel_selection(callback_query: CallbackQuery, state: FSMContext) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer("Некорректный канал")
        return

    await handle_channel_selection_impl(callback_query, callback_query.bot, state, channel_id)


async def handle_channel_selection_impl(
    callback_query: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    channel_id: int,
) -> None:
    await state.clear()

    has_rights = await validate_channel_permissions(bot, channel_id)
    if not has_rights:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="add_channel")],
                [InlineKeyboardButton(text="← Назад", callback_data="back_main")],
            ]
        )
        try:
            await callback_query.message.edit_text(
                "❌ У бота недостаточно прав в этом канале.\n\n"
                "Нужно выдать права: приглашать пользователей и банить/ограничивать пользователей.",
                reply_markup=markup,
            )
        except TelegramBadRequest:
            pass
        await callback_query.answer()
        return

    ch = await get_channel_by_id(channel_id)
    if not ch:
        try:
            chat = await bot.get_chat(channel_id)
            channel_name = chat.username or ""
            channel_title = chat.title or ""
        except Exception:
            channel_name = ""
            channel_title = ""
    else:
        channel_name = ch.get("channel_name") or ""
        channel_title = ch.get("channel_title") or ""

    ok = await add_channel(channel_id, channel_name, channel_title, callback_query.from_user.id)
    if not ok:
        await callback_query.answer("Не удалось сохранить канал")
        return

    await show_channel_menu(callback_query, channel_id)
    await callback_query.answer()


async def show_channel_menu(callback_query: CallbackQuery, channel_id: int) -> None:
    ch = await get_channel_by_id(channel_id)
    if not ch:
        await callback_query.answer("Канал не найден")
        return

    title = ch.get("channel_title") or ch.get("channel_name") or str(channel_id)
    auto_approve = bool(ch.get("auto_approve"))

    text = (
        f"📣 Канал: {title}\n"
        f"ID: {channel_id}\n"
        f"Автопринятие: {'ВКЛ' if auto_approve else 'ВЫКЛ'}"
    )

    markup = get_channel_menu(title, auto_approve, channel_id)
    try:
        await callback_query.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("channel_menu:"))
async def open_channel_menu(callback_query: CallbackQuery) -> None:
    try:
        channel_id = int(callback_query.data.split(":", 1)[1])
    except Exception:
        await callback_query.answer()
        return

    await show_channel_menu(callback_query, channel_id)
    await callback_query.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback_query: CallbackQuery) -> None:
    await callback_query.answer()


@router.my_chat_member()
async def track_bot_admin_status(event: ChatMemberUpdated, bot: Bot) -> None:
    try:
        if event.chat.type != "channel":
            return

        me = await bot.me()
        if event.new_chat_member.user.id != me.id:
            return

        new_status = event.new_chat_member.status
        channel_id = event.chat.id

        channel_name = event.chat.username or ""
        channel_title = event.chat.title or ""
        user_id = event.from_user.id if event.from_user else 0

        if new_status in {"administrator", "member"}:
            await upsert_discovered_channel(channel_id, channel_name, channel_title, user_id)
        elif new_status in {"left", "kicked"}:
            await db_disable_channel(channel_id)
    except Exception as e:
        logger.exception("Failed to track my_chat_member event: %s", e)
