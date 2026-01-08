from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Tuple

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


async def _connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


def _period_range(period: str) -> tuple[date | None, date | None]:
    today = date.today()

    if period in {"all", "all_time", "alltime"}:
        return None, None

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
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        return start, end

    raise ValueError(f"Unknown period: {period}")


async def add_channel(channel_id: int, channel_name: str, channel_title: str, user_id: int) -> bool:
    try:
        async with await _connect() as db:
            await db.execute(
                """
                INSERT INTO channels (channel_id, channel_name, channel_title, user_id, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(channel_id) DO UPDATE SET
                    channel_name = excluded.channel_name,
                    channel_title = excluded.channel_title,
                    user_id = excluded.user_id,
                    is_active = 1
                """,
                (channel_id, channel_name, channel_title, user_id),
            )
            await db.commit()
        logger.info("Channel %s added/activated for user %s", channel_id, user_id)
        return True
    except Exception as e:
        logger.exception("Failed to add channel %s: %s", channel_id, e)
        return False


async def upsert_discovered_channel(channel_id: int, channel_name: str, channel_title: str, user_id: int) -> bool:
    try:
        async with await _connect() as db:
            await db.execute(
                """
                INSERT INTO channels (channel_id, channel_name, channel_title, user_id, is_active)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(channel_id) DO UPDATE SET
                    channel_name = excluded.channel_name,
                    channel_title = excluded.channel_title,
                    user_id = excluded.user_id
                """,
                (channel_id, channel_name, channel_title, user_id),
            )
            await db.commit()
        logger.info("Discovered channel %s saved for user %s", channel_id, user_id)
        return True
    except Exception as e:
        logger.exception("Failed to save discovered channel %s: %s", channel_id, e)
        return False


async def get_channels_by_user(user_id: int) -> List[dict]:
    try:
        async with await _connect() as db:
            async with db.execute(
                "SELECT * FROM channels WHERE user_id = ? ORDER BY channel_title, channel_name",
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.exception("Failed to get channels for user %s: %s", user_id, e)
        return []


async def get_channel_by_id(channel_id: int) -> Optional[dict]:
    try:
        async with await _connect() as db:
            async with db.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.exception("Failed to get channel %s: %s", channel_id, e)
        return None


async def toggle_auto_approve(channel_id: int, enabled: bool) -> bool:
    try:
        if not await channel_exists(channel_id):
            logger.warning("toggle_auto_approve: channel %s not found", channel_id)
            return False

        async with await _connect() as db:
            await db.execute(
                "UPDATE channels SET auto_approve = ? WHERE channel_id = ?",
                (1 if enabled else 0, channel_id),
            )
            await db.commit()
        logger.info("Auto approve for channel %s set to %s", channel_id, enabled)
        return True
    except Exception as e:
        logger.exception("Failed to toggle auto approve for channel %s: %s", channel_id, e)
        return False


async def disable_channel(channel_id: int) -> bool:
    try:
        if not await channel_exists(channel_id):
            logger.warning("disable_channel: channel %s not found", channel_id)
            return False

        async with await _connect() as db:
            await db.execute("UPDATE channels SET is_active = 0 WHERE channel_id = ?", (channel_id,))
            await db.commit()
        logger.info("Channel %s disabled", channel_id)
        return True
    except Exception as e:
        logger.exception("Failed to disable channel %s: %s", channel_id, e)
        return False


async def delete_channel(channel_id: int) -> bool:
    try:
        if not await channel_exists(channel_id):
            logger.warning("delete_channel: channel %s not found", channel_id)
            return False

        async with await _connect() as db:
            await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            await db.commit()
        logger.info("Channel %s deleted", channel_id)
        return True
    except Exception as e:
        logger.exception("Failed to delete channel %s: %s", channel_id, e)
        return False


async def channel_exists(channel_id: int) -> bool:
    try:
        async with await _connect() as db:
            async with db.execute("SELECT 1 FROM channels WHERE channel_id = ? LIMIT 1", (channel_id,)) as cursor:
                return await cursor.fetchone() is not None
    except Exception as e:
        logger.exception("Failed to check channel exists %s: %s", channel_id, e)
        return False


async def add_join_request(channel_id: int, user_id: int, user_name: str) -> bool:
    try:
        async with await _connect() as db:
            async with db.execute(
                """
                SELECT 1 FROM join_requests
                WHERE channel_id = ? AND user_id = ? AND status = 'pending'
                LIMIT 1
                """,
                (channel_id, user_id),
            ) as cursor:
                if await cursor.fetchone() is not None:
                    logger.info("Join request already pending for user %s in channel %s", user_id, channel_id)
                    return True

            await db.execute(
                """
                INSERT INTO join_requests (channel_id, user_id, user_name, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (channel_id, user_id, user_name),
            )
            await db.commit()
        logger.info("Join request stored: channel=%s user=%s", channel_id, user_id)
        return True
    except Exception as e:
        logger.exception("Failed to add join request: channel=%s user=%s error=%s", channel_id, user_id, e)
        return False


async def get_pending_requests(channel_id: int) -> List[dict]:
    try:
        async with await _connect() as db:
            async with db.execute(
                """
                SELECT * FROM join_requests
                WHERE channel_id = ? AND status = 'pending'
                ORDER BY created_at, id
                """,
                (channel_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.exception("Failed to get pending requests for channel %s: %s", channel_id, e)
        return []


async def get_request_by_id(request_id: int) -> Optional[dict]:
    try:
        async with await _connect() as db:
            async with db.execute("SELECT * FROM join_requests WHERE id = ?", (request_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.exception("Failed to get request %s: %s", request_id, e)
        return None


async def approve_request(request_id: int) -> bool:
    try:
        if not await request_exists(request_id):
            logger.warning("approve_request: request %s not found", request_id)
            return False

        async with await _connect() as db:
            await db.execute(
                "UPDATE join_requests SET status = 'approved' WHERE id = ?",
                (request_id,),
            )
            await db.commit()
        logger.info("Request %s marked as approved", request_id)
        return True
    except Exception as e:
        logger.exception("Failed to approve request %s: %s", request_id, e)
        return False


async def reject_request(request_id: int) -> bool:
    try:
        if not await request_exists(request_id):
            logger.warning("reject_request: request %s not found", request_id)
            return False

        async with await _connect() as db:
            await db.execute(
                "UPDATE join_requests SET status = 'rejected' WHERE id = ?",
                (request_id,),
            )
            await db.commit()
        logger.info("Request %s marked as rejected", request_id)
        return True
    except Exception as e:
        logger.exception("Failed to reject request %s: %s", request_id, e)
        return False


async def request_exists(request_id: int) -> bool:
    try:
        async with await _connect() as db:
            async with db.execute("SELECT 1 FROM join_requests WHERE id = ? LIMIT 1", (request_id,)) as cursor:
                return await cursor.fetchone() is not None
    except Exception as e:
        logger.exception("Failed to check request exists %s: %s", request_id, e)
        return False


async def get_statistics(channel_id: int, period: str) -> Tuple[int, int]:
    try:
        start, end = _period_range(period)
        async with await _connect() as db:
            if start is None or end is None:
                query = "SELECT COALESCE(SUM(approved_count), 0), COALESCE(SUM(rejected_count), 0) FROM statistics WHERE channel_id = ?"
                params: tuple[Any, ...] = (channel_id,)
            else:
                query = """
                    SELECT COALESCE(SUM(approved_count), 0), COALESCE(SUM(rejected_count), 0)
                    FROM statistics
                    WHERE channel_id = ? AND period_date BETWEEN ? AND ?
                """
                params = (channel_id, start.isoformat(), end.isoformat())

            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return 0, 0
                return int(row[0] or 0), int(row[1] or 0)
    except Exception as e:
        logger.exception("Failed to get statistics for channel %s period=%s: %s", channel_id, period, e)
        return 0, 0


async def update_statistics(channel_id: int, action: str) -> bool:
    try:
        if action not in {"approve", "reject"}:
            raise ValueError("action must be 'approve' or 'reject'")

        today = date.today().isoformat()
        approved_delta = 1 if action == "approve" else 0
        rejected_delta = 1 if action == "reject" else 0

        async with await _connect() as db:
            await db.execute(
                """
                INSERT INTO statistics (channel_id, approved_count, rejected_count, period_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id, period_date) DO UPDATE SET
                    approved_count = approved_count + excluded.approved_count,
                    rejected_count = rejected_count + excluded.rejected_count
                """,
                (channel_id, approved_delta, rejected_delta, today),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.exception("Failed to update statistics: channel=%s action=%s error=%s", channel_id, action, e)
        return False


async def schedule_task(
    channel_id: int,
    action_type: str,
    scheduled_time: datetime,
    user_count: Optional[int],
) -> bool:
    try:
        if action_type not in {"approve_all", "approve_n"}:
            raise ValueError("Invalid action_type")

        async with await _connect() as db:
            await db.execute(
                """
                INSERT INTO scheduled_tasks (channel_id, action_type, scheduled_time, user_count, is_executed)
                VALUES (?, ?, ?, ?, 0)
                """,
                (channel_id, action_type, scheduled_time.isoformat(), user_count),
            )
            await db.commit()
        logger.info(
            "Scheduled task created: channel=%s type=%s time=%s count=%s",
            channel_id,
            action_type,
            scheduled_time.isoformat(),
            user_count,
        )
        return True
    except Exception as e:
        logger.exception("Failed to schedule task for channel %s: %s", channel_id, e)
        return False


async def get_pending_scheduled_tasks() -> List[dict]:
    try:
        async with await _connect() as db:
            async with db.execute(
                "SELECT * FROM scheduled_tasks WHERE is_executed = 0 ORDER BY scheduled_time, id"
            ) as cursor:
                rows = await cursor.fetchall()

        result: List[dict] = []
        for row in rows:
            d = dict(row)
            try:
                d["scheduled_time"] = datetime.fromisoformat(d["scheduled_time"])
            except Exception:
                pass
            result.append(d)
        return result
    except Exception as e:
        logger.exception("Failed to get pending scheduled tasks: %s", e)
        return []


async def mark_task_executed(task_id: int) -> bool:
    try:
        if not await get_task_by_id(task_id):
            logger.warning("mark_task_executed: task %s not found", task_id)
            return False

        async with await _connect() as db:
            await db.execute("UPDATE scheduled_tasks SET is_executed = 1 WHERE id = ?", (task_id,))
            await db.commit()
        logger.info("Scheduled task %s marked as executed", task_id)
        return True
    except Exception as e:
        logger.exception("Failed to mark task executed %s: %s", task_id, e)
        return False


async def get_task_by_id(task_id: int) -> Optional[dict]:
    try:
        async with await _connect() as db:
            async with db.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        d = dict(row)
        try:
            d["scheduled_time"] = datetime.fromisoformat(d["scheduled_time"])
        except Exception:
            pass
        return d
    except Exception as e:
        logger.exception("Failed to get task %s: %s", task_id, e)
        return None


async def get_last_scheduled_task_id(channel_id: int, scheduled_time: datetime) -> Optional[int]:
    try:
        async with await _connect() as db:
            async with db.execute(
                """
                SELECT id FROM scheduled_tasks
                WHERE channel_id = ? AND scheduled_time = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (channel_id, scheduled_time.isoformat()),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else None
    except Exception as e:
        logger.exception("Failed to get last task id: channel=%s error=%s", channel_id, e)
        return None
