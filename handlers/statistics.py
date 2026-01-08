from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from utils.helpers import format_number


async def get_period_dates(period: str) -> Tuple[date, date]:
    today = date.today()

    if period == "day":
        return today, today

    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end

    if period == "month":
        start = today.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
        end = next_month - timedelta(days=1)
        return start, end

    if period == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)

    return date(1970, 1, 1), today


async def format_statistics(approved: int, rejected: int) -> str:
    return (
        "📊 Статистика:\n"
        f"Принято: {format_number(approved)} ✅\n"
        f"Отклонено: {format_number(rejected)} ❌"
    )
