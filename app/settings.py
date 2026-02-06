from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass
class AppSettings:
    refresh_interval_hours: int = 6
    max_videos_per_channel: int = 12
    instagram_cookie_file: str = ""


SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.toml"


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_settings() -> AppSettings:
    if not SETTINGS_FILE.exists():
        return AppSettings()

    with SETTINGS_FILE.open("rb") as fh:
        data = tomllib.load(fh)

    section = data.get("app", {})
    return AppSettings(
        refresh_interval_hours=int(section.get("refresh_interval_hours", 6)),
        max_videos_per_channel=int(section.get("max_videos_per_channel", 12)),
        instagram_cookie_file=str(section.get("instagram_cookie_file", "") or "").strip(),
    )


def update_settings(
    refresh_interval_hours: int,
    max_videos_per_channel: int,
    instagram_cookie_file: str,
) -> AppSettings:
    safe_interval = max(1, min(int(refresh_interval_hours), 168))
    safe_videos = max(1, min(int(max_videos_per_channel), 100))
    safe_cookie_path = (instagram_cookie_file or "").strip()

    new_settings = AppSettings(
        refresh_interval_hours=safe_interval,
        max_videos_per_channel=safe_videos,
        instagram_cookie_file=safe_cookie_path,
    )
    content = (
        "[app]\n"
        f"refresh_interval_hours = {new_settings.refresh_interval_hours}\n"
        f"max_videos_per_channel = {new_settings.max_videos_per_channel}\n"
        f"instagram_cookie_file = \"{_toml_escape(new_settings.instagram_cookie_file)}\"\n"
    )
    SETTINGS_FILE.write_text(content, encoding="utf-8")
    return new_settings


settings = load_settings()
