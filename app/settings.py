from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


@dataclass
class AppSettings:
    refresh_interval_hours: int = 6
    max_videos_per_channel: int = 12
    instagram_cookie_file: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_allowed_user_id: str = ""


SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.toml"
DOTENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_bot_username(value: str) -> str:
    return (value or "").strip().lstrip("@")


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv_file(DOTENV_FILE)


def _read_dotenv_map(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        result[key] = value
    return result


def write_auth_env_settings(telegram_bot_username: str, telegram_bot_token: str, telegram_allowed_user_id: str) -> None:
    env_map = _read_dotenv_map(DOTENV_FILE)
    env_map["TELEGRAM_BOT_USERNAME"] = _normalize_bot_username(telegram_bot_username or "")
    env_map["TELEGRAM_BOT_TOKEN"] = (telegram_bot_token or "").strip()
    env_map["TELEGRAM_ALLOWED_USER_ID"] = (telegram_allowed_user_id or "").strip()

    ordered_keys = [
        "TELEGRAM_BOT_USERNAME",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USER_ID",
        "TZ",
    ]
    extra_keys = sorted(key for key in env_map.keys() if key not in ordered_keys)
    final_keys = [key for key in ordered_keys if key in env_map] + extra_keys
    content = "".join(f"{key}={env_map[key]}\n" for key in final_keys)
    DOTENV_FILE.write_text(content, encoding="utf-8")

    for key in ["TELEGRAM_BOT_USERNAME", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_ID"]:
        os.environ[key] = env_map.get(key, "")


def load_settings() -> AppSettings:
    if not SETTINGS_FILE.exists():
        return AppSettings(
            telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip(),
            telegram_bot_username=_normalize_bot_username(os.getenv("TELEGRAM_BOT_USERNAME", "") or ""),
            telegram_allowed_user_id=(os.getenv("TELEGRAM_ALLOWED_USER_ID", "") or "").strip(),
        )

    with SETTINGS_FILE.open("rb") as fh:
        data = tomllib.load(fh)

    section = data.get("app", {})
    return AppSettings(
        refresh_interval_hours=int(section.get("refresh_interval_hours", 6)),
        max_videos_per_channel=int(section.get("max_videos_per_channel", 12)),
        instagram_cookie_file=str(section.get("instagram_cookie_file", "") or "").strip(),
        telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or str(section.get("telegram_bot_token", "")) or "").strip(),
        telegram_bot_username=_normalize_bot_username(
            os.getenv("TELEGRAM_BOT_USERNAME") or str(section.get("telegram_bot_username", "")) or ""
        ),
        telegram_allowed_user_id=(
            os.getenv("TELEGRAM_ALLOWED_USER_ID") or str(section.get("telegram_allowed_user_id", "")) or ""
        ).strip(),
    )


def update_settings(
    refresh_interval_hours: int,
    max_videos_per_channel: int,
    instagram_cookie_file: str,
    telegram_bot_token: str | None = None,
    telegram_bot_username: str | None = None,
    telegram_allowed_user_id: str | None = None,
) -> AppSettings:
    current = load_settings()
    safe_interval = max(1, min(int(refresh_interval_hours), 168))
    safe_videos = max(1, min(int(max_videos_per_channel), 100))
    safe_cookie_path = (instagram_cookie_file or "").strip()
    safe_bot_token = (
        current.telegram_bot_token if telegram_bot_token is None else (telegram_bot_token or "").strip()
    )
    safe_bot_username = (
        current.telegram_bot_username
        if telegram_bot_username is None
        else _normalize_bot_username(telegram_bot_username or "")
    )
    safe_allowed_user_id = (
        current.telegram_allowed_user_id
        if telegram_allowed_user_id is None
        else (telegram_allowed_user_id or "").strip()
    )

    new_settings = AppSettings(
        refresh_interval_hours=safe_interval,
        max_videos_per_channel=safe_videos,
        instagram_cookie_file=safe_cookie_path,
        telegram_bot_token=safe_bot_token,
        telegram_bot_username=safe_bot_username,
        telegram_allowed_user_id=safe_allowed_user_id,
    )
    content = (
        "[app]\n"
        f"refresh_interval_hours = {new_settings.refresh_interval_hours}\n"
        f"max_videos_per_channel = {new_settings.max_videos_per_channel}\n"
        f"instagram_cookie_file = \"{_toml_escape(new_settings.instagram_cookie_file)}\"\n"
    )
    if telegram_bot_token is not None or telegram_bot_username is not None or telegram_allowed_user_id is not None:
        content += (
            f"telegram_bot_token = \"{_toml_escape(new_settings.telegram_bot_token)}\"\n"
            f"telegram_bot_username = \"{_toml_escape(new_settings.telegram_bot_username)}\"\n"
            f"telegram_allowed_user_id = \"{_toml_escape(new_settings.telegram_allowed_user_id)}\"\n"
        )
    SETTINGS_FILE.write_text(content, encoding="utf-8")
    return new_settings


settings = load_settings()
