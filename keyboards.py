from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict


class Keyboards:

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📢 Каналы", callback_data="channels"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats_menu")
        )
        builder.row(
            InlineKeyboardButton(text="⏰ Расписание", callback_data="schedule_menu"),
            InlineKeyboardButton(text="❓ FAQ", callback_data="faq")
        )
        return builder.as_markup()

    @staticmethod
    def channels_list(channels: List[Dict]) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        row = []
        for ch in channels:
            icon = "🔴" if not ch['is_active'] else ("⚡" if ch['auto_accept'] else "🟢")
            btn = InlineKeyboardButton(
                text=f"{icon} {ch['title'][:20]}",
                callback_data=f"ch:{ch['channel_id']}"
            )
            row.append(btn)
            if len(row) == 2:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)

        builder.row(
            InlineKeyboardButton(text="➕ Добавить", callback_data="add_channel"),
            InlineKeyboardButton(text="← Меню", callback_data="menu")
        )
        return builder.as_markup()

    @staticmethod
    def channel_menu(channel: Dict, pending_count: int = 0) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        cid = channel['channel_id']

        # Строка 1: Авто + Принять
        auto_text = "⚡ Авто: ВКЛ" if channel['auto_accept'] else "✋ Авто: ВЫКЛ"
        accept_text = f"👥 Принять ({pending_count})" if pending_count > 0 else "📭 Нет заявок"
        accept_data = f"accept_menu:{cid}" if pending_count > 0 else "noop"

        builder.row(
            InlineKeyboardButton(text=auto_text, callback_data=f"auto:{cid}"),
            InlineKeyboardButton(text=accept_text, callback_data=accept_data)
        )

        # Строка 2: Приветствие + Расписание
        builder.row(
            InlineKeyboardButton(text="✉️ Приветствие", callback_data=f"welcome:{cid}"),
            InlineKeyboardButton(text="⏰ Расписание", callback_data=f"schedule:{cid}")
        )

        # Строка 3: Пиковые часы + Экспорт CSV
        builder.row(
            InlineKeyboardButton(text="📈 Пиковые часы", callback_data=f"peak:{cid}"),
            InlineKeyboardButton(text="📥 Экспорт CSV", callback_data=f"export:{cid}")
        )

        # Строка 4: Статистика + Ещё
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data=f"stat:{cid}"),
            InlineKeyboardButton(text="⚙️ Ещё", callback_data=f"more:{cid}")
        )

        # Строка 5: Назад
        builder.row(InlineKeyboardButton(text="← К каналам", callback_data="channels"))

        return builder.as_markup()

    @staticmethod
    def accept_menu(channel_id: int, pending_count: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        builder.row(InlineKeyboardButton(
            text=f"✅ Принять всех ({pending_count})",
            callback_data=f"accept:{channel_id}:all"
        ))

        buttons = []
        for num in [5, 10, 25, 50, 100, 250, 500]:
            if num <= pending_count:
                buttons.append(InlineKeyboardButton(
                    text=str(num),
                    callback_data=f"accept:{channel_id}:{num}"
                ))

        for i in range(0, len(buttons), 4):
            builder.row(*buttons[i:i + 4])

        builder.row(
            InlineKeyboardButton(text="✏️ Своё число", callback_data=f"accept_custom:{channel_id}"),
            InlineKeyboardButton(text="← Назад", callback_data=f"ch:{channel_id}")
        )

        return builder.as_markup()

    @staticmethod
    def welcome_menu(channel_id: int, has_welcome: bool) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        if has_welcome:
            builder.row(
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"welcome_edit:{channel_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"welcome_del:{channel_id}")
            )
        else:
            builder.row(InlineKeyboardButton(text="✏️ Добавить", callback_data=f"welcome_edit:{channel_id}"))

        builder.row(InlineKeyboardButton(text="← Назад", callback_data=f"ch:{channel_id}"))
        return builder.as_markup()

    @staticmethod
    def schedule_channel_menu(channel_id: int, schedule: dict = None) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        is_on = schedule and schedule.get('enabled')
        toggle_text = "🟢 ВКЛ" if is_on else "🔴 ВЫКЛ"
        builder.row(InlineKeyboardButton(text=toggle_text, callback_data=f"sched_toggle:{channel_id}"))

        builder.row(
            InlineKeyboardButton(text="📅 Дни", callback_data=f"sched_days:{channel_id}"),
            InlineKeyboardButton(text="🕐 Время", callback_data=f"sched_time:{channel_id}"),
            InlineKeyboardButton(text="👥 Кол-во", callback_data=f"sched_count:{channel_id}")
        )

        builder.row(InlineKeyboardButton(text="← Назад", callback_data=f"ch:{channel_id}"))
        return builder.as_markup()

    @staticmethod
    def schedule_days(channel_id: int, selected_days: list = None) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        days = [("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Вс", 6)]
        selected = selected_days or []

        row = []
        for name, num in days:
            icon = "✓" if num in selected else ""
            row.append(InlineKeyboardButton(
                text=f"{icon}{name}",
                callback_data=f"sched_day:{channel_id}:{num}"
            ))
        builder.row(*row)

        builder.row(
            InlineKeyboardButton(text="Все дни", callback_data=f"sched_day:{channel_id}:all"),
            InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")
        )
        return builder.as_markup()

    @staticmethod
    def schedule_time_options(channel_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        times = ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]

        for i in range(0, len(times), 3):
            row = [InlineKeyboardButton(text=t, callback_data=f"sched_settime:{channel_id}:{t}") for t in
                   times[i:i + 3]]
            builder.row(*row)

        builder.row(
            InlineKeyboardButton(text="✏️ Своё", callback_data=f"sched_customtime:{channel_id}"),
            InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")
        )
        return builder.as_markup()

    @staticmethod
    def schedule_count_options(channel_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        builder.row(InlineKeyboardButton(text="∞ Всех", callback_data=f"sched_setcount:{channel_id}:all"))

        counts = [5, 10, 25, 50, 100]
        row = [InlineKeyboardButton(text=str(c), callback_data=f"sched_setcount:{channel_id}:{c}") for c in counts]
        builder.row(*row)

        builder.row(
            InlineKeyboardButton(text="✏️ Своё", callback_data=f"sched_customcount:{channel_id}"),
            InlineKeyboardButton(text="← Назад", callback_data=f"schedule:{channel_id}")
        )
        return builder.as_markup()

    @staticmethod
    def more_settings(channel: Dict) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        cid = channel['channel_id']

        status = "🟢 Активен" if channel['is_active'] else "🔴 Неактивен"
        builder.row(
            InlineKeyboardButton(text=status, callback_data=f"toggle:{cid}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{cid}")
        )
        builder.row(InlineKeyboardButton(text="← Назад", callback_data=f"ch:{cid}"))
        return builder.as_markup()

    @staticmethod
    def confirm(action: str, data: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Да", callback_data=f"yes_{action}:{data}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"no_{action}:{data}")
        )
        return builder.as_markup()

    @staticmethod
    def back(callback_data: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="← Назад", callback_data=callback_data))
        return builder.as_markup()

    @staticmethod
    def faq_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="📢 Каналы", callback_data="faq:channels"),
            InlineKeyboardButton(text="⚡ Авто-приём", callback_data="faq:auto")
        )
        builder.row(
            InlineKeyboardButton(text="👥 Принятие", callback_data="faq:accept"),
            InlineKeyboardButton(text="⏰ Расписание", callback_data="faq:schedule")
        )
        builder.row(
            InlineKeyboardButton(text="✉️ Приветствие", callback_data="faq:welcome"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="faq:stats")
        )
        builder.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
        return builder.as_markup()

    @staticmethod
    def faq_back() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="← К списку FAQ", callback_data="faq"))
        return builder.as_markup()


kb = Keyboards()