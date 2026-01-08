from typing import Optional


def format_user(user_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    parts = []
    if full_name:
        parts.append(f"<b>{full_name}</b>")
    if username:
        parts.append(f"@{username}")
    parts.append(f"<code>{user_id}</code>")
    return " | ".join(parts)