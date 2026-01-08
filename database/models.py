from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


async def init_database() -> None:
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")

            async with db.execute("PRAGMA user_version") as cursor:
                row = await cursor.fetchone()
                user_version = int(row[0]) if row else 0

            if user_version == 0:
                await db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                logger.info("Database schema version set to %s", SCHEMA_VERSION)
            elif user_version != SCHEMA_VERSION:
                logger.warning(
                    "Database schema version mismatch: current=%s expected=%s. "
                    "Migrations are not implemented yet.",
                    user_version,
                    SCHEMA_VERSION,
                )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER UNIQUE NOT NULL,
                    channel_name TEXT,
                    channel_title TEXT,
                    user_id INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    auto_approve BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            await db.execute(
                """
                CREATE TRIGGER IF NOT EXISTS channels_updated_at
                AFTER UPDATE ON channels
                FOR EACH ROW
                BEGIN
                    UPDATE channels SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END;
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS join_requests (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    status TEXT CHECK(status IN ('pending', 'approved', 'rejected')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    action_type TEXT CHECK(action_type IN ('approve_all', 'approve_n')),
                    scheduled_time TIMESTAMP NOT NULL,
                    user_count INTEGER,
                    is_executed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    approved_count INTEGER DEFAULT 0,
                    rejected_count INTEGER DEFAULT 0,
                    period_date DATE NOT NULL,
                    UNIQUE(channel_id, period_date),
                    FOREIGN KEY(channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
                )
                """
            )

            await db.commit()

        logger.info("Database initialized successfully at %s", db_path)
    except Exception as e:  # pragma: no cover
        logger.exception("Failed to initialize database: %s", e)
        raise
