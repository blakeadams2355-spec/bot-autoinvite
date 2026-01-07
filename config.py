import os
from dotenv import load_dotenv
from dataclasses import dataclass, field

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x
    ])
    DATABASE_PATH: str = "bot_database.db"
    DEFAULT_WELCOME_MESSAGE: str = "🎉 Добро пожаловать!"


config = Config()