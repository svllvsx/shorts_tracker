from __future__ import annotations

import csv
import http.cookiejar
import io
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote_plus, urlparse
import urllib.request
import urllib.error
import re
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, delete, func, select

from app.db import engine, get_session, init_db
from app.models import Channel, ChannelSnapshot, Video
from app.services.ytdlp_service import YtDlpFetchError, fetch_channel_data
from app.settings import settings, update_settings

app = FastAPI(title="YT Analytics")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
COOKIE_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "cookies"
COOKIE_STORE_FILE = COOKIE_STORE_DIR / "instagram_cookies.txt"
AVATAR_STORE_DIR = Path(__file__).resolve().parent / "static" / "avatars"
REFRESH_JOBS: dict[str, dict[str, Any]] = {}
REFRESH_JOBS_LOCK = Lock()
REFRESH_JOB_TTL_HOURS = 24
REFRESH_JOB_MAX_STORED = 200

SUPPORTED_LANGS = {"en", "ru"}
SUPPORTED_THEMES = {"light", "dark"}
SUPPORTED_SECTIONS = {"overview", "charts", "settings"}
SUPPORTED_VIDEO_SORTS = {"upload_date", "views", "likes", "comments", "title"}
SUPPORTED_VIDEO_ORDERS = {"asc", "desc"}
PLATFORM_ORDER = ["youtube", "tiktok", "instagram", "twitch", "x", "other"]

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "brand": "YT Analytics",
        "title_dashboard": "Dashboard",
        "nav_dashboard": "Dashboard",
        "menu_overview": "Overview",
        "menu_charts": "Charts",
        "menu_settings": "Settings",
        "menu_export": "Export CSV",
        "refresh_interval": "Refresh interval: {hours}h. Max videos per channel: {videos}.",
        "placeholder_channel_url": "https://www.youtube.com/@yourhandle",
        "add_channel": "Add channel",
        "global_refresh": "Refresh all",
        "global_refresh_stop": "Stop refresh",
        "force_global_refresh": "Force global refresh",
        "no_channels": "No channels yet. Add one above.",
        "last_refresh": "Last refresh: {value}",
        "refresh": "Refresh",
        "force": "Force",
        "total_views": "Total views",
        "average_views": "Average views",
        "median_views": "Median views",
        "top_video_views": "Top video views",
        "latest_videos": "Latest videos",
        "preview": "Preview",
        "video_title": "Title",
        "upload_date": "Upload date",
        "duration": "Duration",
        "views": "Views",
        "likes": "Likes",
        "comments": "Comments",
        "no_videos": "No videos stored yet.",
        "never": "never",
        "no_image": "No image",
        "theme_toggle_to_dark": "Dark",
        "theme_toggle_to_light": "Light",
        "settings_title": "Settings",
        "settings_refresh_interval": "Refresh interval (hours)",
        "settings_max_videos": "Latest videos per channel",
        "settings_instagram_cookie_file": "Instagram cookies file (.txt)",
        "settings_instagram_cookie_current": "Current file: {name}",
        "msg_settings_cookie_upload_failed": "Failed to save Instagram cookies file",
        "settings_check_instagram_cookies": "Check cookies",
        "settings_cookie_status_loading": "Cookie status: checking...",
        "settings_cookie_status_ok": "Cookie status: valid",
        "settings_cookie_status_invalid": "Cookie status: invalid",
        "settings_cookie_status_missing": "Cookie status: missing",
        "settings_cookie_uploading": "Uploading cookie file...",
        "settings_cookie_upload_ok": "Cookie file uploaded",
        "msg_settings_cookie_check_missing": "Instagram cookies file is missing. Upload it first.",
        "msg_settings_cookie_check_ok": "Instagram cookies are valid",
        "msg_settings_cookie_check_invalid": "Instagram cookies check failed: {reason}",
        "video_sort_label": "Sort videos by",
        "video_sort_upload_date": "Upload date",
        "video_sort_views": "Views",
        "video_sort_likes": "Likes",
        "video_sort_comments": "Comments",
        "video_sort_title": "Title",
        "video_sort_order": "Order",
        "video_sort_order_desc": "Descending",
        "video_sort_order_asc": "Ascending",
        "save_settings": "Save settings",
        "charts_title": "Channel Charts",
        "chart_total_views": "Total views by channel",
        "chart_average_views": "Average views by channel",
        "chart_no_data": "Not enough data to draw charts yet.",
        "platform_youtube": "YouTube",
        "platform_tiktok": "TikTok",
        "platform_instagram": "Instagram",
        "platform_twitch": "Twitch",
        "platform_x": "X / Twitter",
        "platform_other": "Other",
        "msg_channel_url_required": "Channel URL is required",
        "msg_channel_exists": "Channel already exists",
        "msg_channel_not_found": "Channel not found",
        "msg_no_channels_to_refresh": "No channels to refresh",
        "msg_settings_saved": "Settings saved",
        "msg_settings_invalid": "Settings values must be numbers",
        "refresh_progress_title": "Refresh progress",
        "refresh_progress_wait": "Preparing refresh job...",
        "refresh_progress_running": "Refreshing: {done}/{total}",
        "refresh_progress_done": "Refresh completed",
        "refresh_progress_stopping": "Stopping refresh...",
        "refresh_progress_start_failed": "Failed to start refresh job",
        "refresh_progress_invalid_start": "Invalid refresh job response",
        "refresh_progress_poll_failed": "Refresh polling failed",
        "refresh_progress_stop_failed": "Failed to stop refresh job",
        "stats_24h_title": "Last 24h by channel",
        "stats_24h_empty": "Not enough snapshots yet. Run refresh and come back in 24h for deltas.",
        "stats_24h_views": "Views",
        "stats_24h_likes": "Likes",
        "stats_24h_comments": "Comments",
        "stats_24h_subscribers": "Subscribers",
        "stats_24h_views_short": "Views",
        "stats_24h_likes_short": "Likes",
        "stats_24h_comments_short": "Comms",
        "stats_24h_subscribers_short": "Subs",
        "stats_24h_no_data": "n/a",
        "msg_skipped_cache": "Skipped (cache active)",
        "msg_refreshed_channel": "Refreshed {title} ({count} videos)",
        "msg_done_summary": "Done. Refreshed={refreshed}, Skipped={skipped}, Failed={failed}",
        "msg_done_cancelled_summary": "Stopped. Progress {done}/{total}. Refreshed={refreshed}, Skipped={skipped}, Failed={failed}",
        "msg_refresh_kept_old": "Refresh failed to return usable data. Previous cached data was kept.",
        "summary_refreshed": "Refreshed",
        "summary_skipped": "Skipped",
        "summary_failed": "Failed",
    },
    "ru": {
        "brand": "YT Analytics",
        "title_dashboard": "Дашборд",
        "nav_dashboard": "Дашборд",
        "menu_overview": "Общее",
        "menu_charts": "Графики",
        "menu_settings": "Настройки",
        "menu_export": "Экспорт CSV",
        "refresh_interval": "Интервал обновления: {hours}ч. Макс. видео на канал: {videos}.",
        "placeholder_channel_url": "https://www.youtube.com/@yourhandle",
        "add_channel": "Добавить канал",
        "global_refresh": "Обновить все",
        "force_global_refresh": "Принудительно обновить все",
        "no_channels": "Каналов пока нет. Добавьте канал выше.",
        "last_refresh": "Последнее обновление: {value}",
        "refresh": "Обновить",
        "force": "Форс",
        "total_views": "Всего просмотров",
        "average_views": "Средние просмотры",
        "median_views": "Медиана просмотров",
        "top_video_views": "Лучшее видео (просмотры)",
        "latest_videos": "Последние видео",
        "preview": "Превью",
        "video_title": "Название",
        "upload_date": "Дата загрузки",
        "duration": "Длительность",
        "views": "Просмотры",
        "likes": "Лайки",
        "comments": "Комментарии",
        "no_videos": "Видео пока не сохранены.",
        "never": "никогда",
        "no_image": "Нет фото",
        "theme_toggle_to_dark": "Темная",
        "theme_toggle_to_light": "Светлая",
        "settings_title": "Настройки",
        "settings_refresh_interval": "Интервал обновления (часы)",
        "settings_max_videos": "Последних видео на канал",
        "settings_instagram_cookie_file": "Путь к cookie-файлу Instagram (.txt)",
        "settings_instagram_cookie_current": "Текущий файл: {name}",
        "msg_settings_cookie_upload_failed": "Не удалось сохранить cookie-файл Instagram",
        "video_sort_label": "Сортировать видео по",
        "video_sort_upload_date": "Дата загрузки",
        "video_sort_views": "Просмотры",
        "video_sort_likes": "Лайки",
        "video_sort_comments": "Комментарии",
        "video_sort_title": "Название",
        "video_sort_order": "Порядок",
        "video_sort_order_desc": "По убыванию",
        "video_sort_order_asc": "По возрастанию",
        "save_settings": "Сохранить настройки",
        "charts_title": "Графики по каналам",
        "chart_total_views": "Всего просмотров по каналам",
        "chart_average_views": "Средние просмотры по каналам",
        "chart_no_data": "Пока недостаточно данных для графиков.",
        "platform_youtube": "YouTube",
        "platform_tiktok": "TikTok",
        "platform_instagram": "Instagram",
        "platform_twitch": "Twitch",
        "platform_x": "X / Twitter",
        "platform_other": "Другое",
        "msg_channel_url_required": "Нужно указать URL канала",
        "msg_channel_exists": "Канал уже добавлен",
        "msg_channel_not_found": "Канал не найден",
        "msg_no_channels_to_refresh": "Нет каналов для обновления",
        "msg_settings_saved": "Настройки сохранены",
        "msg_settings_invalid": "Значения настроек должны быть числами",
        "refresh_progress_title": "Прогресс обновления",
        "refresh_progress_wait": "Подготовка задачи обновления...",
        "refresh_progress_running": "Обновление: {done}/{total}",
        "refresh_progress_done": "Обновление завершено",
        "stats_24h_title": "Последние 24ч по каналам",
        "stats_24h_empty": "Пока недостаточно срезов. Обновите и вернитесь через 24ч.",
        "stats_24h_views": "Просмотры",
        "stats_24h_likes": "Лайки",
        "stats_24h_comments": "Комментарии",
        "stats_24h_subscribers": "Подписчики",
        "stats_24h_views_short": "Просм.",
        "stats_24h_likes_short": "Лайки",
        "stats_24h_comments_short": "Комм.",
        "stats_24h_subscribers_short": "Подп.",
        "stats_24h_no_data": "н/д",
        "msg_skipped_cache": "Пропущено (активен кэш)",
        "msg_refreshed_channel": "Обновлен {title} ({count} видео)",
        "msg_done_summary": "Готово. Обновлено={refreshed}, Пропущено={skipped}, Ошибок={failed}",
        "msg_refresh_kept_old": "Не удалось получить корректные данные при обновлении. Сохранены предыдущие кэшированные данные.",
        "summary_refreshed": "Обновлено",
        "summary_skipped": "Пропущено",
        "summary_failed": "Ошибок",
    },
}

# Force canonical brand/title labels to stay language-correct even if source file encoding
# of legacy RU literals was altered earlier.
TRANSLATIONS["en"]["brand"] = "Analytics"
TRANSLATIONS["en"]["title_dashboard"] = "Analytics"
TRANSLATIONS["en"]["nav_dashboard"] = "Analytics"
TRANSLATIONS["ru"]["brand"] = "Аналитика"
TRANSLATIONS["ru"]["title_dashboard"] = "Аналитика"
TRANSLATIONS["ru"]["nav_dashboard"] = "Аналитика"
TRANSLATIONS["ru"]["settings_instagram_cookie_file"] = "Файл cookies Instagram (.txt)"
TRANSLATIONS["ru"]["settings_check_instagram_cookies"] = "Проверить cookie"
TRANSLATIONS["ru"]["settings_cookie_status_loading"] = "Статус cookie: проверка..."
TRANSLATIONS["ru"]["settings_cookie_status_ok"] = "Статус cookie: валидны"
TRANSLATIONS["ru"]["settings_cookie_status_invalid"] = "Статус cookie: невалидны"
TRANSLATIONS["ru"]["settings_cookie_status_missing"] = "Статус cookie: отсутствуют"
TRANSLATIONS["ru"]["settings_cookie_uploading"] = "Загрузка cookie-файла..."
TRANSLATIONS["ru"]["settings_cookie_upload_ok"] = "Cookie-файл загружен"
TRANSLATIONS["ru"]["msg_settings_cookie_check_missing"] = "Нет cookie-файла Instagram. Сначала загрузите его."
TRANSLATIONS["ru"]["msg_settings_cookie_check_ok"] = "Instagram cookie валидны"
TRANSLATIONS["ru"]["msg_settings_cookie_check_invalid"] = "Проверка cookie не пройдена: {reason}"


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _get_lang(request: Request) -> str:
    lang = (request.cookies.get("lang") or "en").lower()
    return lang if lang in SUPPORTED_LANGS else "en"


def _get_theme(request: Request) -> str:
    theme = (request.cookies.get("theme") or "light").lower()
    return theme if theme in SUPPORTED_THEMES else "light"


def _safe_section(section: str | None) -> str:
    if section in SUPPORTED_SECTIONS:
        return section
    return "overview"


def _safe_video_sort(video_sort: str | None) -> str:
    if video_sort in SUPPORTED_VIDEO_SORTS:
        return video_sort
    return "upload_date"


def _safe_video_order(video_order: str | None) -> str:
    if video_order in SUPPORTED_VIDEO_ORDERS:
        return video_order
    return "desc"


def _t(lang: str, key: str, **kwargs: Any) -> str:
    dictionary = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    text = dictionary.get(key, TRANSLATIONS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def _fmt_date_ru(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    parsed = str(value).strip()
    if not parsed:
        return "-"
    try:
        return datetime.fromisoformat(parsed).strftime("%d.%m.%Y")
    except ValueError:
        return parsed


def _fmt_datetime_ru(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    parsed = str(value).strip()
    if not parsed:
        return "-"
    try:
        dt = datetime.fromisoformat(parsed)
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return parsed


def _safe_next(next_url: str | None) -> str:
    if not next_url:
        return "/dashboard"
    return next_url if next_url.startswith("/") else "/dashboard"


def _dashboard_url(section: str, msg: str | None = None, error: str | None = None) -> str:
    safe_section = _safe_section(section)
    params = [f"section={quote_plus(safe_section)}"]
    if msg:
        params.append(f"msg={quote_plus(msg)}")
    if error:
        params.append(f"error={quote_plus(error)}")
    return f"/dashboard?{'&'.join(params)}"


def _extract_summary_counts(message: str | None) -> dict[str, int] | None:
    if not message:
        return None
    import re

    matches = re.findall(r"([A-Za-zА-Яа-яЁё_]+)\s*=\s*(\d+)", message)
    if not matches:
        return None

    lowered = {key.lower(): int(value) for key, value in matches}
    refreshed = lowered.get("refreshed", lowered.get("обновлено"))
    skipped = lowered.get("skipped", lowered.get("пропущено"))
    failed = lowered.get("failed", lowered.get("ошибок"))
    if refreshed is None or skipped is None or failed is None:
        return None
    return {"refreshed": refreshed, "skipped": skipped, "failed": failed}


def _set_refresh_job(job_id: str, **kwargs: Any) -> None:
    with REFRESH_JOBS_LOCK:
        job = REFRESH_JOBS.get(job_id)
        if not job:
            return
        job.update(kwargs)


def _is_refresh_job_cancel_requested(job_id: str) -> bool:
    with REFRESH_JOBS_LOCK:
        job = REFRESH_JOBS.get(job_id)
        if not job:
            return True
        return bool(job.get("cancel_requested"))


def _cleanup_refresh_jobs() -> None:
    now = datetime.utcnow()
    expiry = now - timedelta(hours=REFRESH_JOB_TTL_HOURS)

    def _parse_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    with REFRESH_JOBS_LOCK:
        stale_ids: list[str] = []
        for job_id, job in REFRESH_JOBS.items():
            if not job.get("finished"):
                continue
            finished_at = _parse_iso(job.get("finished_at"))
            started_at = _parse_iso(job.get("started_at"))
            timestamp = finished_at or started_at
            if timestamp and timestamp < expiry:
                stale_ids.append(job_id)

        for job_id in stale_ids:
            REFRESH_JOBS.pop(job_id, None)

        overflow = len(REFRESH_JOBS) - REFRESH_JOB_MAX_STORED
        if overflow <= 0:
            return

        sortable: list[tuple[datetime, str]] = []
        for job_id, job in REFRESH_JOBS.items():
            if not job.get("finished"):
                continue
            finished_at = _parse_iso(job.get("finished_at"))
            started_at = _parse_iso(job.get("started_at"))
            timestamp = finished_at or started_at or datetime.min
            sortable.append((timestamp, job_id))

        for _, job_id in sorted(sortable)[:overflow]:
            REFRESH_JOBS.pop(job_id, None)


def _run_refresh_all_job(job_id: str, force: bool, lang: str, section: str) -> None:
    try:
        with Session(engine) as session:
            channels = session.exec(select(Channel)).all()
            total = len(channels)
            _set_refresh_job(job_id, total=total)

            if total == 0:
                msg = _t(lang, "msg_no_channels_to_refresh")
                _set_refresh_job(
                    job_id,
                    finished=True,
                    finished_at=datetime.utcnow().isoformat(),
                    cancelled=False,
                    done=0,
                    refreshed=0,
                    skipped=0,
                    failed=0,
                    current="",
                    message=msg,
                    redirect_url=_dashboard_url(section, msg=msg),
                )
                return

            refreshed = 0
            skipped = 0
            failed = 0
            done = 0

            for channel in channels:
                if _is_refresh_job_cancel_requested(job_id):
                    summary = _t(
                        lang,
                        "msg_done_cancelled_summary",
                        done=done,
                        total=total,
                        refreshed=refreshed,
                        skipped=skipped,
                        failed=failed,
                    )
                    _set_refresh_job(
                        job_id,
                        finished=True,
                        finished_at=datetime.utcnow().isoformat(),
                        cancelled=True,
                        current="",
                        message=summary,
                        redirect_url=_dashboard_url(section, msg=summary),
                    )
                    return
                _set_refresh_job(job_id, current=channel.title, done=done)
                ok, text = _refresh_channel(session, channel, lang=lang, force=force)
                if ok and text == _t(lang, "msg_skipped_cache"):
                    skipped += 1
                elif ok:
                    refreshed += 1
                else:
                    failed += 1
                done += 1
                _set_refresh_job(job_id, done=done, refreshed=refreshed, skipped=skipped, failed=failed)

            summary = _t(lang, "msg_done_summary", refreshed=refreshed, skipped=skipped, failed=failed)
            _set_refresh_job(
                job_id,
                finished=True,
                finished_at=datetime.utcnow().isoformat(),
                cancelled=False,
                current="",
                message=summary,
                redirect_url=_dashboard_url(section, msg=summary),
            )
    except Exception as exc:
        _set_refresh_job(
            job_id,
            finished=True,
            finished_at=datetime.utcnow().isoformat(),
            cancelled=False,
            message=f"Unexpected refresh error: {exc}",
            redirect_url=_dashboard_url(section, error=f"Unexpected refresh error: {exc}"),
        )


def _save_instagram_cookie_file(upload: UploadFile) -> str:
    COOKIE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    data = upload.file.read()
    if not data:
        raise ValueError("empty file")
    COOKIE_STORE_FILE.write_bytes(data)
    return str(COOKIE_STORE_FILE)


def _effective_instagram_cookie_file() -> str:
    if COOKIE_STORE_FILE.is_file():
        return str(COOKIE_STORE_FILE)
    configured = (settings.instagram_cookie_file or "").strip()
    if configured and Path(configured).is_file():
        return configured
    return ""


def _check_instagram_cookies(cookie_file: str) -> tuple[bool, str]:
    path = (cookie_file or "").strip()
    if not path or not Path(path).is_file():
        return False, "missing"

    try:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(path, ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        return False, f"cookie file parse error: {exc}"
    if len(list(jar)) == 0:
        return False, "cookie file is empty"

    req = urllib.request.Request(
        "https://www.instagram.com/accounts/edit/",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        },
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(req, timeout=20) as resp:
            final_url = (resp.geturl() or "").lower()
            html = resp.read(30000).decode("utf-8", errors="ignore").lower()
            if "/accounts/login" in final_url or "loginform" in html:
                return False, "session is not authorized"
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}"
    except Exception as exc:
        return False, str(exc)

    return True, "ok"


def _cache_avatar_locally(channel_id: int, avatar_url: str | None) -> str | None:
    if not avatar_url:
        return None
    try:
        req = urllib.request.Request(
            avatar_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            content_type = (resp.headers.get("Content-Type") or "").lower()
    except Exception:
        return avatar_url

    if not body:
        return avatar_url

    if "image/png" in content_type:
        ext = ".png"
    elif "image/webp" in content_type:
        ext = ".webp"
    elif "image/gif" in content_type:
        ext = ".gif"
    else:
        ext = ".jpg"

    AVATAR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    target = AVATAR_STORE_DIR / f"channel_{channel_id}{ext}"
    target.write_bytes(body)
    return f"/static/avatars/{target.name}"


def _detect_platform(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if "twitch.tv" in host:
        return "twitch"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    return "other"


def _display_channel_title(channel: Channel) -> str:
    raw = (channel.title or "").strip()
    if not raw:
        return "Untitled channel"

    platform = _detect_platform(channel.url or "")
    if platform != "tiktok":
        return raw

    normalized = raw[1:] if raw.startswith("@") else raw
    # TikTok often returns handle-like names; convert to a readable label.
    if re.fullmatch(r"[a-z0-9._]+", normalized):
        normalized = re.sub(r"[._]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized:
            return normalized.title()
    return raw


def _clean_channel_title_for_strip(title: str) -> str:
    if not title:
        return title
    cleaned = title.strip()
    cleaned = re.sub(r"\s*[-|•:/]\s*shorts?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(\s*shorts?\s*\)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title


def _sort_videos(videos: list[Video], sort_key: str, sort_order: str) -> list[Video]:
    reverse = sort_order == "desc"
    if sort_key == "title":
        return sorted(videos, key=lambda v: (v.title or "").lower(), reverse=reverse)
    if sort_key == "views":
        return sorted(videos, key=lambda v: (v.view_count is None, v.view_count or 0), reverse=reverse)
    if sort_key == "likes":
        return sorted(videos, key=lambda v: (v.like_count is None, v.like_count or 0), reverse=reverse)
    if sort_key == "comments":
        return sorted(videos, key=lambda v: (v.comment_count is None, v.comment_count or 0), reverse=reverse)
    return sorted(videos, key=lambda v: (v.upload_date is None, v.upload_date), reverse=reverse)


def _is_cache_valid(channel: Channel, force: bool) -> bool:
    if force:
        return False
    if not channel.last_refreshed_at:
        return False
    delta = datetime.utcnow() - channel.last_refreshed_at
    return delta < timedelta(hours=settings.refresh_interval_hours)


def _aggregate_for_channel(session: Session, channel_id: int) -> dict[str, Any]:
    totals = session.exec(
        select(
            func.coalesce(func.sum(Video.view_count), 0),
            func.coalesce(func.avg(Video.view_count), 0),
            func.coalesce(func.sum(Video.like_count), 0),
            func.coalesce(func.sum(Video.comment_count), 0),
        ).where(Video.channel_id == channel_id)
    ).one()
    total_views = int(totals[0] or 0)
    avg_views = int(float(totals[1] or 0.0))
    total_likes = int(totals[2] or 0)
    total_comments = int(totals[3] or 0)

    view_values = [
        int(value)
        for value in session.exec(select(Video.view_count).where(Video.channel_id == channel_id)).all()
        if value is not None
    ]
    view_values.sort()
    count = len(view_values)
    if count == 0:
        median_views = 0
        top_video_views = 0
    elif count % 2 == 1:
        median_views = view_values[count // 2]
        top_video_views = view_values[-1]
    else:
        median_views = int((view_values[count // 2 - 1] + view_values[count // 2]) / 2)
        top_video_views = view_values[-1]

    return {
        "total_views": total_views,
        "avg_views": avg_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "median_views": median_views,
        "top_video_views": top_video_views,
    }


def _save_channel_snapshot(
    session: Session,
    channel_id: int,
    total_views: int,
    total_likes: int,
    total_comments: int,
    subscriber_count: int | None,
) -> None:
    now = datetime.utcnow()
    latest = session.exec(
        select(ChannelSnapshot)
        .where(ChannelSnapshot.channel_id == channel_id)
        .order_by(ChannelSnapshot.captured_at.desc(), ChannelSnapshot.id.desc())
        .limit(1)
    ).first()
    if latest and (now - latest.captured_at) < timedelta(hours=24):
        return

    session.add(
        ChannelSnapshot(
            channel_id=channel_id,
            captured_at=now,
            total_views=total_views,
            total_likes=total_likes,
            total_comments=total_comments,
            subscriber_count=subscriber_count,
        )
    )


def _build_channel_24h_stats(
    session: Session,
    channel: Channel,
    aggregates: dict[str, Any],
) -> dict[str, Any]:
    platform = _detect_platform(channel.url)
    display_title = _display_channel_title(channel)
    threshold = datetime.utcnow() - timedelta(hours=24)
    baseline = session.exec(
        select(ChannelSnapshot)
        .where(ChannelSnapshot.channel_id == channel.id)
        .where(ChannelSnapshot.captured_at <= threshold)
        .order_by(ChannelSnapshot.captured_at.desc(), ChannelSnapshot.id.desc())
        .limit(1)
    ).first()

    if not baseline:
        return {
            "channel": channel,
            "platform": platform,
            "display_title": _clean_channel_title_for_strip(display_title),
            "has_delta": False,
            "views_delta": None,
            "likes_delta": None,
            "comments_delta": None,
            "subscribers_delta": None,
        }

    subscribers_delta = None
    if channel.subscriber_count is not None and baseline.subscriber_count is not None:
        subscribers_delta = channel.subscriber_count - baseline.subscriber_count

    return {
        "channel": channel,
        "platform": platform,
        "display_title": _clean_channel_title_for_strip(display_title),
        "has_delta": True,
        "views_delta": aggregates["total_views"] - baseline.total_views,
        "likes_delta": aggregates["total_likes"] - baseline.total_likes,
        "comments_delta": aggregates["total_comments"] - baseline.total_comments,
        "subscribers_delta": subscribers_delta,
    }


def _refresh_channel(session: Session, channel: Channel, lang: str, force: bool = False) -> tuple[bool, str]:
    if _is_cache_valid(channel, force=force):
        return True, _t(lang, "msg_skipped_cache")

    existing_videos = session.exec(select(Video).where(Video.channel_id == channel.id)).all()
    existing_by_url = {video.url: video for video in existing_videos if video.url}
    has_previous = len(existing_videos) > 0
    old_total_views = sum(int(video.view_count or 0) for video in existing_videos)
    old_total_likes = sum(int(video.like_count or 0) for video in existing_videos)
    old_total_comments = sum(int(video.comment_count or 0) for video in existing_videos)
    old_view_values = sorted(int(video.view_count or 0) for video in existing_videos if video.view_count is not None)

    def _view_stats(values: list[int]) -> tuple[int, int, int]:
        if not values:
            return 0, 0, 0
        top = values[-1]
        avg = int(sum(values) / len(values))
        if len(values) % 2 == 1:
            median = values[len(values) // 2]
        else:
            median = int((values[len(values) // 2 - 1] + values[len(values) // 2]) / 2)
        return avg, median, top

    old_avg_views, old_median_views, old_top_video_views = _view_stats(old_view_values)

    try:
        payload = fetch_channel_data(
            channel.url,
            settings.max_videos_per_channel,
            instagram_cookie_file=_effective_instagram_cookie_file(),
        )
    except YtDlpFetchError as exc:
        channel.last_error = str(exc)
        session.add(channel)
        session.commit()
        return False, channel.last_error
    except Exception as exc:
        channel.last_error = f"Unexpected fetch error: {exc}"
        session.add(channel)
        session.commit()
        return False, channel.last_error

    if existing_videos and not payload.videos:
        channel.last_error = _t(lang, "msg_refresh_kept_old")
        session.add(channel)
        session.commit()
        return False, channel.last_error

    try:
        cached_avatar_url = _cache_avatar_locally(channel.id, payload.avatar_url)
        channel.title = payload.title or channel.title
        channel.url = payload.url or channel.url
        channel.avatar_url = cached_avatar_url or payload.avatar_url or channel.avatar_url
        channel.subscriber_count = payload.subscriber_count if payload.subscriber_count is not None else channel.subscriber_count
        channel.last_refreshed_at = datetime.utcnow()
        channel.last_error = None

        total_views = 0
        total_likes = 0
        total_comments = 0
        new_view_values: list[int] = []
        session.exec(delete(Video).where(Video.channel_id == channel.id))
        for item in payload.videos:
            old_video = existing_by_url.get(item.url)
            upload_date = item.upload_date or (old_video.upload_date if old_video else None)
            duration_seconds = item.duration_seconds or (old_video.duration_seconds if old_video else None)
            view_count = item.view_count if item.view_count is not None else (old_video.view_count if old_video else None)
            like_count = item.like_count if item.like_count is not None else (old_video.like_count if old_video else None)
            comment_count = item.comment_count if item.comment_count is not None else (old_video.comment_count if old_video else None)
            thumbnail_url = item.thumbnail_url or (old_video.thumbnail_url if old_video else None)
            title = item.title or (old_video.title if old_video else "Untitled video")

            total_views += int(view_count or 0)
            total_likes += int(like_count or 0)
            total_comments += int(comment_count or 0)
            if view_count is not None:
                new_view_values.append(int(view_count))

            view_delta = None
            like_delta = None
            comment_delta = None
            if old_video and old_video.view_count is not None and view_count is not None:
                view_delta = int(view_count) - int(old_video.view_count)
            if old_video and old_video.like_count is not None and like_count is not None:
                like_delta = int(like_count) - int(old_video.like_count)
            if old_video and old_video.comment_count is not None and comment_count is not None:
                comment_delta = int(comment_count) - int(old_video.comment_count)

            session.add(
                Video(
                    channel_id=channel.id,
                    title=title,
                    url=item.url,
                    upload_date=upload_date,
                    duration_seconds=duration_seconds,
                    view_count=view_count,
                    like_count=like_count,
                    comment_count=comment_count,
                    view_delta=view_delta,
                    like_delta=like_delta,
                    comment_delta=comment_delta,
                    thumbnail_url=thumbnail_url,
                )
            )

        new_view_values.sort()
        new_avg_views, new_median_views, new_top_video_views = _view_stats(new_view_values)
        if has_previous:
            channel.delta_total_views = total_views - old_total_views
            channel.delta_avg_views = new_avg_views - old_avg_views
            channel.delta_median_views = new_median_views - old_median_views
            channel.delta_top_video_views = new_top_video_views - old_top_video_views
            channel.delta_total_likes = total_likes - old_total_likes
            channel.delta_total_comments = total_comments - old_total_comments
        else:
            channel.delta_total_views = None
            channel.delta_avg_views = None
            channel.delta_median_views = None
            channel.delta_top_video_views = None
            channel.delta_total_likes = None
            channel.delta_total_comments = None

        _save_channel_snapshot(
            session=session,
            channel_id=channel.id,
            total_views=total_views,
            total_likes=total_likes,
            total_comments=total_comments,
            subscriber_count=payload.subscriber_count,
        )
        session.add(channel)
        session.commit()
    except Exception as exc:
        session.rollback()
        channel.last_error = f"Unexpected refresh error: {exc}"
        session.add(channel)
        session.commit()
        return False, channel.last_error

    return True, _t(lang, "msg_refreshed_channel", title=channel.title, count=len(payload.videos))


@app.get("/")
def landing():
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/preferences/lang/{lang_code}")
def set_language(lang_code: str, next: str | None = None):
    lang = lang_code.lower()
    selected = lang if lang in SUPPORTED_LANGS else "en"
    response = RedirectResponse(url=_safe_next(next), status_code=303)
    response.set_cookie("lang", selected, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/preferences/theme/{theme_code}")
def set_theme(theme_code: str, next: str | None = None):
    theme = theme_code.lower()
    selected = theme if theme in SUPPORTED_THEMES else "light"
    response = RedirectResponse(url=_safe_next(next), status_code=303)
    response.set_cookie("theme", selected, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/dashboard")
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    msg: str | None = None,
    error: str | None = None,
    section: str = "overview",
    video_sort: str = "upload_date",
    video_order: str = "desc",
):
    lang = _get_lang(request)
    theme = _get_theme(request)
    current_section = _safe_section(section)
    current_video_sort = _safe_video_sort(video_sort)
    current_video_order = _safe_video_order(video_order)
    msg_summary = _extract_summary_counts(msg)
    channels = session.exec(select(Channel).order_by(Channel.created_at.desc())).all()
    dashboard_rows: list[dict[str, Any]] = []
    channel_24h_rows: list[dict[str, Any]] = []

    for channel in channels:
        display_title = _display_channel_title(channel)
        videos = session.exec(
            select(Video)
            .where(Video.channel_id == channel.id)
            .order_by(Video.upload_date.desc(), Video.id.desc())
            .limit(settings.max_videos_per_channel)
        ).all()
        videos = _sort_videos(videos, current_video_sort, current_video_order)
        aggregates = _aggregate_for_channel(session, channel.id)
        aggregates["delta_total_views"] = channel.delta_total_views
        aggregates["delta_avg_views"] = channel.delta_avg_views
        aggregates["delta_median_views"] = channel.delta_median_views
        aggregates["delta_top_video_views"] = channel.delta_top_video_views
        aggregates["delta_total_likes"] = channel.delta_total_likes
        aggregates["delta_total_comments"] = channel.delta_total_comments
        dashboard_rows.append(
            {
                "channel": channel,
                "display_title": display_title,
                "videos": videos,
                "aggregates": aggregates,
                "platform": _detect_platform(channel.url),
            }
        )
        channel_24h_rows.append(_build_channel_24h_stats(session, channel, aggregates))

    platform_rank = {name: idx for idx, name in enumerate(PLATFORM_ORDER)}
    channel_24h_rows.sort(
        key=lambda row: (
            platform_rank.get(row["platform"], len(PLATFORM_ORDER)),
            (row["channel"].title or "").lower(),
        )
    )

    grouped_map: dict[str, list[dict[str, Any]]] = {}
    for row in dashboard_rows:
        grouped_map.setdefault(row["platform"], []).append(row)

    grouped_rows: list[dict[str, Any]] = []
    for platform_key in PLATFORM_ORDER:
        rows = grouped_map.get(platform_key, [])
        if rows:
            group_views = sum(int(item["aggregates"]["total_views"]) for item in rows)
            group_likes = sum(int(item["aggregates"]["total_likes"]) for item in rows)
            group_comments = sum(int(item["aggregates"]["total_comments"]) for item in rows)
            group_views_deltas = [
                int(item["aggregates"]["delta_total_views"])
                for item in rows
                if item["aggregates"]["delta_total_views"] is not None
            ]
            group_likes_deltas = [
                int(item["aggregates"]["delta_total_likes"])
                for item in rows
                if item["aggregates"]["delta_total_likes"] is not None
            ]
            group_comments_deltas = [
                int(item["aggregates"]["delta_total_comments"])
                for item in rows
                if item["aggregates"]["delta_total_comments"] is not None
            ]
            grouped_rows.append(
                {
                    "key": platform_key,
                    "label": _t(lang, f"platform_{platform_key}"),
                    "rows": rows,
                    "channel_count": len(rows),
                    "summary": {
                        "views": group_views,
                        "likes": group_likes,
                        "comments": group_comments,
                        "views_delta": sum(group_views_deltas) if group_views_deltas else None,
                        "likes_delta": sum(group_likes_deltas) if group_likes_deltas else None,
                        "comments_delta": sum(group_comments_deltas) if group_comments_deltas else None,
                    },
                }
            )

    max_total_views = max((row["aggregates"]["total_views"] for row in dashboard_rows), default=0)
    max_avg_views = max((row["aggregates"]["avg_views"] for row in dashboard_rows), default=0)
    chart_rows_total = []
    for row in sorted(dashboard_rows, key=lambda item: item["aggregates"]["total_views"], reverse=True):
        total_views = row["aggregates"]["total_views"]
        chart_rows_total.append(
            {
                "channel": row["channel"],
                "display_title": row["display_title"],
                "platform": row["platform"],
                "value": total_views,
                "height_pct": int((total_views / max_total_views) * 100) if max_total_views > 0 else 0,
            }
        )

    chart_rows_avg = []
    for row in sorted(dashboard_rows, key=lambda item: item["aggregates"]["avg_views"], reverse=True):
        avg_views = row["aggregates"]["avg_views"]
        chart_rows_avg.append(
            {
                "channel": row["channel"],
                "display_title": row["display_title"],
                "platform": row["platform"],
                "value": avg_views,
                "height_pct": int((avg_views / max_avg_views) * 100) if max_avg_views > 0 else 0,
            }
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "grouped_rows": grouped_rows,
            "channel_24h_rows": channel_24h_rows,
            "chart_rows_total": chart_rows_total,
            "chart_rows_avg": chart_rows_avg,
            "settings": settings,
            "msg": msg,
            "msg_summary": msg_summary,
            "error": error,
            "lang": lang,
            "theme": theme,
            "section": current_section,
            "video_sort": current_video_sort,
            "video_order": current_video_order,
            "cookie_file_name": Path(_effective_instagram_cookie_file()).name if _effective_instagram_cookie_file() else "",
            "t": lambda key, **kwargs: _t(lang, key, **kwargs),
            "fmt_date": _fmt_date_ru,
            "fmt_datetime": _fmt_datetime_ru,
            "now": datetime.utcnow(),
        },
    )


@app.get("/analytics/export.csv")
def export_analytics_csv(session: Session = Depends(get_session)):
    channels = session.exec(select(Channel).order_by(Channel.created_at.desc())).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "channel_id",
            "channel_title",
            "channel_url",
            "platform",
            "export_video_limit",
            "video_rank_in_channel",
            "last_refreshed_at",
            "channel_last_error",
            "total_views",
            "average_views",
            "median_views",
            "top_video_views",
            "video_title",
            "video_url",
            "video_upload_date",
            "video_views",
            "video_likes",
            "video_comments",
        ]
    )

    for channel in channels:
        aggregates = _aggregate_for_channel(session, channel.id)
        platform = _detect_platform(channel.url)
        videos = session.exec(
            select(Video)
            .where(Video.channel_id == channel.id)
            .order_by(Video.upload_date.desc(), Video.id.desc())
            .limit(settings.max_videos_per_channel)
        ).all()

        if not videos:
            writer.writerow(
                [
                    channel.id,
                    channel.title,
                    channel.url,
                    platform,
                    settings.max_videos_per_channel,
                    "",
                    channel.last_refreshed_at.isoformat() if channel.last_refreshed_at else "",
                    channel.last_error or "",
                    aggregates["total_views"],
                    aggregates["avg_views"],
                    aggregates["median_views"],
                    aggregates["top_video_views"],
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue

        for idx, video in enumerate(videos, start=1):
            writer.writerow(
                [
                    channel.id,
                    channel.title,
                    channel.url,
                    platform,
                    settings.max_videos_per_channel,
                    idx,
                    channel.last_refreshed_at.isoformat() if channel.last_refreshed_at else "",
                    channel.last_error or "",
                    aggregates["total_views"],
                    aggregates["avg_views"],
                    aggregates["median_views"],
                    aggregates["top_video_views"],
                    video.title,
                    video.url,
                    video.upload_date.isoformat() if video.upload_date else "",
                    video.view_count if video.view_count is not None else "",
                    video.like_count if video.like_count is not None else "",
                    video.comment_count if video.comment_count is not None else "",
                ]
            )

    filename = f"yt_analytics_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    content = buffer.getvalue().encode("utf-8-sig")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/channels/add")
def add_channel(
    request: Request,
    channel_url: str = Form(...),
    next_section: str = Form("overview"),
    session: Session = Depends(get_session),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    normalized = channel_url.strip()
    if not normalized:
        return RedirectResponse(url=_dashboard_url(section, error=_t(lang, "msg_channel_url_required")), status_code=303)

    existing = session.exec(select(Channel).where(Channel.url == normalized)).first()
    if existing:
        return RedirectResponse(url=_dashboard_url(section, msg=_t(lang, "msg_channel_exists")), status_code=303)

    channel = Channel(title="Pending refresh", url=normalized)
    session.add(channel)
    session.commit()
    session.refresh(channel)

    ok, text = _refresh_channel(session, channel, lang=lang, force=True)
    return RedirectResponse(url=_dashboard_url(section, msg=text if ok else None, error=None if ok else text), status_code=303)


@app.post("/settings/update")
def save_settings_route(
    request: Request,
    refresh_interval_hours: str = Form(...),
    max_videos_per_channel: str = Form(...),
    instagram_cookie_upload: UploadFile | None = File(None),
    next_section: str = Form("settings"),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    try:
        interval = int(refresh_interval_hours)
        max_videos = int(max_videos_per_channel)
    except ValueError:
        return RedirectResponse(url=_dashboard_url(section, error=_t(lang, "msg_settings_invalid")), status_code=303)

    cookie_path = _effective_instagram_cookie_file()
    if instagram_cookie_upload and instagram_cookie_upload.filename:
        try:
            cookie_path = _save_instagram_cookie_file(instagram_cookie_upload)
        except Exception:
            return RedirectResponse(
                url=_dashboard_url(section, error=_t(lang, "msg_settings_cookie_upload_failed")),
                status_code=303,
            )
    elif COOKIE_STORE_FILE.is_file():
        cookie_path = str(COOKIE_STORE_FILE)

    new_settings = update_settings(interval, max_videos, cookie_path)
    settings.refresh_interval_hours = new_settings.refresh_interval_hours
    settings.max_videos_per_channel = new_settings.max_videos_per_channel
    settings.instagram_cookie_file = new_settings.instagram_cookie_file
    return RedirectResponse(url=_dashboard_url(section, msg=_t(lang, "msg_settings_saved")), status_code=303)


@app.post("/settings/instagram-cookies/check")
def check_instagram_cookies_route(
    request: Request,
    next_section: str = Form("settings"),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    cookie_path = _effective_instagram_cookie_file()
    if not cookie_path:
        return RedirectResponse(
            url=_dashboard_url(section, error=_t(lang, "msg_settings_cookie_check_missing")),
            status_code=303,
        )

    ok, reason = _check_instagram_cookies(cookie_path)
    if ok:
        return RedirectResponse(url=_dashboard_url(section, msg=_t(lang, "msg_settings_cookie_check_ok")), status_code=303)
    return RedirectResponse(
        url=_dashboard_url(section, error=_t(lang, "msg_settings_cookie_check_invalid", reason=reason)),
        status_code=303,
    )


@app.post("/settings/instagram-cookies/upload")
def upload_instagram_cookies_route(
    request: Request,
    instagram_cookie_upload: UploadFile | None = File(None),
):
    lang = _get_lang(request)
    if not instagram_cookie_upload or not instagram_cookie_upload.filename:
        return JSONResponse({"ok": False, "error": _t(lang, "msg_settings_cookie_upload_failed")}, status_code=400)
    try:
        saved = _save_instagram_cookie_file(instagram_cookie_upload)
    except Exception:
        return JSONResponse({"ok": False, "error": _t(lang, "msg_settings_cookie_upload_failed")}, status_code=400)

    new_settings = update_settings(settings.refresh_interval_hours, settings.max_videos_per_channel, saved)
    settings.instagram_cookie_file = new_settings.instagram_cookie_file
    return JSONResponse(
        {
            "ok": True,
            "message": _t(lang, "settings_cookie_upload_ok"),
            "current_file_label": _t(lang, "settings_instagram_cookie_current", name=Path(saved).name),
        }
    )


@app.get("/settings/instagram-cookies/status")
def instagram_cookies_status(request: Request):
    lang = _get_lang(request)
    cookie_path = _effective_instagram_cookie_file()
    if not cookie_path:
        return JSONResponse(
            {
                "ok": False,
                "state": "missing",
                "message": _t(lang, "settings_cookie_status_missing"),
            }
        )

    ok, reason = _check_instagram_cookies(cookie_path)
    if ok:
        return JSONResponse(
            {
                "ok": True,
                "state": "ok",
                "message": _t(lang, "settings_cookie_status_ok"),
            }
        )
    return JSONResponse(
        {
            "ok": False,
            "state": "invalid",
            "message": _t(lang, "msg_settings_cookie_check_invalid", reason=reason),
        }
    )


@app.post("/channels/{channel_id}/refresh")
def refresh_channel(
    request: Request,
    channel_id: int,
    force: int = Form(0),
    next_section: str = Form("overview"),
    session: Session = Depends(get_session),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    channel = session.get(Channel, channel_id)
    if not channel:
        return RedirectResponse(url=_dashboard_url(section, error=_t(lang, "msg_channel_not_found")), status_code=303)

    ok, text = _refresh_channel(session, channel, lang=lang, force=bool(force))
    return RedirectResponse(url=_dashboard_url(section, msg=text if ok else None, error=None if ok else text), status_code=303)


@app.post("/channels/refresh-all/start")
def refresh_all_start(
    background_tasks: BackgroundTasks,
    request: Request,
    force: int = Form(1),
    next_section: str = Form("overview"),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    _cleanup_refresh_jobs()
    job_id = uuid4().hex
    with REFRESH_JOBS_LOCK:
        REFRESH_JOBS[job_id] = {
            "job_id": job_id,
            "started_at": datetime.utcnow().isoformat(),
            "finished": False,
            "finished_at": "",
            "cancel_requested": False,
            "cancel_requested_at": "",
            "cancelled": False,
            "done": 0,
            "total": 0,
            "refreshed": 0,
            "skipped": 0,
            "failed": 0,
            "current": "",
            "message": "",
            "redirect_url": _dashboard_url(section),
        }
    background_tasks.add_task(_run_refresh_all_job, job_id, bool(force), lang, section)
    return JSONResponse({"job_id": job_id})


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    _cleanup_refresh_jobs()
    with REFRESH_JOBS_LOCK:
        job = REFRESH_JOBS.get(job_id)
        if not job:
            return JSONResponse({"error": "job_not_found"}, status_code=404)
        return JSONResponse(job)


@app.post("/jobs/{job_id}/stop")
def stop_job(request: Request, job_id: str):
    lang = _get_lang(request)
    with REFRESH_JOBS_LOCK:
        job = REFRESH_JOBS.get(job_id)
        if not job:
            return JSONResponse({"error": "job_not_found"}, status_code=404)
        if job.get("finished"):
            return JSONResponse(job)
        job["cancel_requested"] = True
        job["cancel_requested_at"] = datetime.utcnow().isoformat()
        job["message"] = _t(lang, "refresh_progress_stopping")
        return JSONResponse({"job_id": job_id, "cancel_requested": True})


@app.post("/channels/refresh-all")
def refresh_all(
    request: Request,
    force: int = Form(1),
    next_section: str = Form("overview"),
    session: Session = Depends(get_session),
):
    lang = _get_lang(request)
    section = _safe_section(next_section)
    channels = session.exec(select(Channel)).all()
    if not channels:
        return RedirectResponse(url=_dashboard_url(section, msg=_t(lang, "msg_no_channels_to_refresh")), status_code=303)

    refreshed = 0
    skipped = 0
    failed = 0
    for channel in channels:
        ok, text = _refresh_channel(session, channel, lang=lang, force=bool(force))
        if ok and text == _t(lang, "msg_skipped_cache"):
            skipped += 1
        elif ok:
            refreshed += 1
        else:
            failed += 1

    summary = _t(lang, "msg_done_summary", refreshed=refreshed, skipped=skipped, failed=failed)
    return RedirectResponse(url=_dashboard_url(section, msg=summary), status_code=303)
