from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in .env file")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./data/bot.db"))
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

_admin_id_env = os.getenv("ADMIN_ID")
if _admin_id_env:
    ADMIN_ID: int | None = int(_admin_id_env)
else:
    legacy_admin_ids = os.getenv("ADMIN_IDS", "")
    ADMIN_ID = int(legacy_admin_ids.split(",")[0]) if legacy_admin_ids.strip() else None

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TIMEZONE = os.getenv("TIMEZONE", "UTC")

logger = logging.getLogger(__name__)
