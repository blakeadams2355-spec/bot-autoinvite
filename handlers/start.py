from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.main_menu import get_main_menu

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text == "/start")
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Привет! Я помогу управлять заявками на вступление в ваши каналы.\n\n"
        "Выберите действие:",
        reply_markup=get_main_menu(),
    )


@router.callback_query(F.data == "back_main")
async def back_to_main_menu(callback_query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback_query.message.edit_text(
            "🏠 Главное меню:",
            reply_markup=get_main_menu(),
        )
    except Exception as e:
        logger.warning("Failed to edit main menu message: %s", e)
    await callback_query.answer()


@router.callback_query(F.data == "add_channel")
async def handle_add_channel(callback_query: CallbackQuery, state: FSMContext) -> None:
    from .channel_manager import handle_add_channel as _handle_add_channel

    await _handle_add_channel(callback_query, callback_query.bot, state)


@router.callback_query(F.data == "settings")
async def handle_settings(callback_query: CallbackQuery, state: FSMContext) -> None:
    from .channel_manager import show_user_channels

    await show_user_channels(callback_query, callback_query.bot, state)


@router.callback_query(F.data == "faq")
async def handle_faq(callback_query: CallbackQuery, state: FSMContext) -> None:
    from .faq import show_faq_menu

    await state.clear()
    await show_faq_menu(callback_query)
