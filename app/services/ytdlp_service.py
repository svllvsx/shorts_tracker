from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse
import http.cookiejar
import urllib.request
import urllib.error

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class YtDlpFetchError(Exception):
    pass


@dataclass
class VideoPayload:
    title: str
    url: str
    upload_date: Optional[date]
    duration_seconds: Optional[int]
    view_count: Optional[int]
    like_count: Optional[int]
    comment_count: Optional[int]
    thumbnail_url: Optional[str]


@dataclass
class ChannelPayload:
    title: str
    url: str
    avatar_url: Optional[str]
    subscriber_count: Optional[int]
    videos: list[VideoPayload]


def _normalize_channel_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if cleaned.startswith("@"):
        return f"https://www.youtube.com/{cleaned}"
    return cleaned


def _parse_upload_date(raw_date: str | None) -> Optional[date]:
    if not raw_date:
        return None
    try:
        return date(int(raw_date[0:4]), int(raw_date[4:6]), int(raw_date[6:8]))
    except (ValueError, TypeError):
        return None


def _pick_best_thumbnail(thumbnails: Any) -> Optional[str]:
    if not isinstance(thumbnails, list):
        return None

    candidates: list[tuple[int, str]] = []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue
        url = _normalize_media_url(item.get("url"))
        if not url:
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        area = width * height
        candidates.append((area, url))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _pick_avatar_like_thumbnail(thumbnails: Any) -> Optional[str]:
    if not isinstance(thumbnails, list):
        return None
    candidates: list[tuple[int, str]] = []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue
        url = _normalize_media_url(item.get("url"))
        if not url:
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if width <= 0 or height <= 0:
            continue
        ratio = width / height
        if ratio < 0.8 or ratio > 1.25:
            continue
        area = width * height
        candidates.append((area, url))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _normalize_media_url(raw: Any) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    value = raw.strip()
    # Some platforms return escaped JSON strings like https:\\u002F\\u002F...
    try:
        import json

        decoded = json.loads(f'"{value}"')
        if isinstance(decoded, str):
            value = decoded
    except Exception:
        pass
    value = value.replace("\\/", "/")
    value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), value)
    if not value:
        return None
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    return value


def _pick_first_url(*values: Any) -> Optional[str]:
    for value in values:
        normalized = _normalize_media_url(value)
        if normalized:
            return normalized
    return None


def _is_tiktok_channel(channel_info: dict[str, Any], source_url: str) -> bool:
    extractor = str(channel_info.get("extractor_key") or "").lower()
    webpage = str(channel_info.get("webpage_url") or channel_info.get("channel_url") or source_url).lower()
    return "tiktok" in extractor or "tiktok.com" in webpage


def _is_instagram_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return "instagram.com" in host


def _is_tiktok_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return "tiktok.com" in host


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return "youtube.com" in host or "youtu.be" in host


def _youtube_profile_url(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return url
    if parts[0].startswith("@"):
        return f"{base}/{parts[0]}"
    if parts[0] in {"channel", "c", "user"} and len(parts) > 1:
        return f"{base}/{parts[0]}/{parts[1]}"
    return url


def _extract_instagram_username(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    first = parts[0].lower()
    if first in {"reel", "p", "tv", "stories", "explore"}:
        return None
    return parts[0]


def _fetch_html(url: str, cookie_file: str) -> str:
    jar = http.cookiejar.MozillaCookieJar()
    jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        url,
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
    with opener.open(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _fetch_json(url: str, cookie_file: str) -> dict[str, Any]:
    jar = http.cookiejar.MozillaCookieJar()
    jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
            "x-ig-app-id": "936619743392459",
            "x-requested-with": "XMLHttpRequest",
        },
    )
    with opener.open(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        import json

        return json.loads(raw)


def _fetch_html_without_cookies(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _match_first(text: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _fetch_instagram_channel_data(url: str, max_videos: int, cookie_file: str) -> ChannelPayload:
    username = _extract_instagram_username(url)
    if not username:
        raise YtDlpFetchError("Instagram URL should be a profile URL like https://www.instagram.com/<username>/")
    if not cookie_file or not Path(cookie_file).is_file():
        raise YtDlpFetchError("Instagram cookies file is missing. Upload cookies in Settings first.")

    profile_url = f"https://www.instagram.com/{username}/"
    api_url = f"https://www.instagram.com/api/v1/feed/user/{username}/username/?count={max_videos * 2}"
    try:
        payload = _fetch_json(api_url, cookie_file)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise YtDlpFetchError("Instagram rate-limited the request (HTTP 429). Try again later.") from exc
        if exc.code in {401, 403}:
            raise YtDlpFetchError("Instagram rejected cookies (401/403). Export cookies again and retry.") from exc
        raise YtDlpFetchError(f"Instagram request failed: HTTP {exc.code}") from exc
    except Exception as exc:
        raise YtDlpFetchError(f"Instagram request failed: {exc}") from exc

    user_info = payload.get("user") or {}
    avatar_url = _pick_first_url(user_info.get("profile_pic_url_hd"), user_info.get("profile_pic_url"))
    title = (user_info.get("full_name") or user_info.get("username") or username).strip()
    items = payload.get("items") or []
    videos: list[VideoPayload] = []
    for item in items:
        media_type = item.get("media_type")
        product_type = str(item.get("product_type") or "")
        is_reel_like = (media_type == 2) or (product_type == "clips") or bool(item.get("clips_metadata"))
        if not is_reel_like:
            continue

        code = item.get("code")
        if not code:
            continue
        caption = ((item.get("caption") or {}).get("text") or "").strip()
        if caption:
            title_text = caption[:80]
        else:
            title_text = f"Reel {code}"

        candidates = ((item.get("image_versions2") or {}).get("candidates") or [])
        thumbnail = None
        for candidate in candidates:
            if isinstance(candidate, dict):
                thumbnail = _normalize_media_url(candidate.get("url"))
                if thumbnail:
                    break

        taken_at = item.get("taken_at")
        upload_date = None
        if isinstance(taken_at, int):
            try:
                upload_date = datetime.utcfromtimestamp(taken_at).date()
            except Exception:
                upload_date = None

        videos.append(
            VideoPayload(
                title=title_text,
                url=f"https://www.instagram.com/reel/{code}/",
                upload_date=upload_date,
                duration_seconds=item.get("video_duration"),
                view_count=item.get("play_count") or item.get("view_count") or item.get("video_view_count"),
                like_count=item.get("like_count"),
                comment_count=item.get("comment_count"),
                thumbnail_url=thumbnail,
            )
        )
        if len(videos) >= max_videos:
            break

    if not videos:
        raise YtDlpFetchError(
            "Instagram profile loaded but no reels/videos were returned by the API for this account/session."
        )

    return ChannelPayload(
        title=title,
        url=profile_url,
        avatar_url=avatar_url,
        subscriber_count=user_info.get("follower_count"),
        videos=videos,
    )


def _fetch_tiktok_avatar_from_page(url: str) -> Optional[str]:
    try:
        html = _fetch_html_without_cookies(url)
    except Exception:
        return None
    raw = _match_first(
        html,
        [
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'"avatarLarger":"([^"]+)"',
            r'"avatarMedium":"([^"]+)"',
            r'"avatarThumb":"([^"]+)"',
            r'"avatar":"([^"]+)"',
        ],
    )
    return _normalize_media_url(raw)


def _extract_avatar(channel_info: dict[str, Any], source_url: str) -> Optional[str]:
    # TikTok often puts video cover into generic thumbnail fields,
    # so for avatar use only explicit profile-avatar style keys.
    if _is_tiktok_channel(channel_info, source_url):
        explicit = _pick_first_url(
            channel_info.get("avatar_url"),
            channel_info.get("uploader_avatar"),
            channel_info.get("profile_pic_url"),
            channel_info.get("creator_thumbnail"),
            channel_info.get("channel_thumbnail"),
        )
        return explicit or _pick_avatar_like_thumbnail(channel_info.get("thumbnails"))

    from_channel = _pick_first_url(
        channel_info.get("avatar_url"),
        channel_info.get("uploader_avatar"),
        channel_info.get("channel_thumbnail"),
        channel_info.get("creator_thumbnail"),
        channel_info.get("profile_pic_url"),
    )
    if _is_youtube_url(source_url):
        # For YouTube shorts pages, generic thumbnail can be a video frame.
        return from_channel
    from_channel = from_channel or _pick_first_url(channel_info.get("thumbnail")) or _pick_best_thumbnail(channel_info.get("thumbnails"))
    return from_channel


def _fetch_youtube_avatar_from_profile(url: str) -> Optional[str]:
    profile_url = _youtube_profile_url(url)
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": 1,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(profile_url, download=False)
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    return _pick_first_url(
        info.get("avatar_url"),
        info.get("uploader_avatar"),
        info.get("channel_thumbnail"),
        info.get("profile_pic_url"),
    ) or _pick_avatar_like_thumbnail(info.get("thumbnails")) or _pick_first_url(info.get("thumbnail"))


def _extract_video_thumbnail(details: dict[str, Any], entry: dict[str, Any]) -> Optional[str]:
    return _pick_first_url(
        details.get("thumbnail"),
        details.get("cover"),
        details.get("dynamic_cover"),
        entry.get("thumbnail"),
    ) or _pick_best_thumbnail(details.get("thumbnails")) or _pick_best_thumbnail(entry.get("thumbnails"))


def _is_socket_10048_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "winerror 10048" in text or "only one usage of each socket address" in text


def _is_tiktok_user_extract_error(details: str) -> bool:
    lower = details.lower()
    return (
        "tiktok:user" in lower
        and (
            "unable to extract secondary user id" in lower
            or "private or has embedding disabled" in lower
            or "winerror 10048" in lower
        )
    )


def _extract_tiktok_username_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    first = parts[0]
    if first.startswith("@"):
        return first[1:]
    return first


def _decode_json_string(raw: str) -> str:
    try:
        import json

        decoded = json.loads(f'"{raw}"')
        if isinstance(decoded, str):
            return decoded
    except Exception:
        pass
    return raw


def _fetch_tiktok_channel_data_from_page(url: str, max_videos: int) -> ChannelPayload:
    html = _fetch_html_without_cookies(url)
    username = _extract_tiktok_username_from_url(url) or "tiktok_user"
    canonical_url = f"https://www.tiktok.com/@{username}"

    title = _match_first(
        html,
        [
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            r"<title>([^<]+)</title>",
        ],
    ) or username
    title = re.sub(r"\s+on\s+TikTok\s*$", "", title, flags=re.IGNORECASE).strip() or username

    avatar_url = _fetch_tiktok_avatar_from_page(canonical_url) or _fetch_tiktok_avatar_from_page(url)
    follower_raw = _match_first(html, [r'"followerCount"\s*:\s*(\d+)'])
    subscriber_count = int(follower_raw) if follower_raw and follower_raw.isdigit() else None

    video_id_matches = re.findall(rf"/@{re.escape(username)}/video/(\d+)", html, flags=re.IGNORECASE)
    seen_ids: set[str] = set()
    videos: list[VideoPayload] = []
    for video_id in video_id_matches:
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        video_url = f"https://www.tiktok.com/@{username}/video/{video_id}"
        desc_raw = _match_first(
            html,
            [
                rf'"id":"{re.escape(video_id)}".{{0,400}}"desc":"([^"]*)"',
                rf'"video":\{{"id":"{re.escape(video_id)}".{{0,400}}"desc":"([^"]*)"',
            ],
        )
        title_text = _decode_json_string(desc_raw).strip() if desc_raw else f"TikTok video {video_id}"
        if len(title_text) > 120:
            title_text = title_text[:117] + "..."

        videos.append(
            VideoPayload(
                title=title_text,
                url=video_url,
                upload_date=None,
                duration_seconds=None,
                view_count=None,
                like_count=None,
                comment_count=None,
                thumbnail_url=None,
            )
        )
        if len(videos) >= max_videos:
            break

    if not videos:
        raise YtDlpFetchError(
            "TikTok fallback could not parse videos from profile page. "
            "Try again later or refresh this channel individually."
        )

    return ChannelPayload(
        title=title,
        url=canonical_url,
        avatar_url=avatar_url,
        subscriber_count=subscriber_count,
        videos=videos,
    )


def _extract_info_with_backoff(ydl: YoutubeDL, url: str, retries: int = 3) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return ydl.extract_info(url, download=False)
        except DownloadError as exc:
            last_exc = exc
            if not _is_socket_10048_error(exc) or attempt >= retries:
                raise
            time.sleep(min(0.8 * (2 ** (attempt - 1)), 3.0))
    if last_exc:
        raise last_exc
    return None


def fetch_channel_data(channel_url: str, max_videos: int, instagram_cookie_file: str = "") -> ChannelPayload:
    url = _normalize_channel_url(channel_url)
    if _is_instagram_url(url):
        return _fetch_instagram_channel_data(url, max_videos=max_videos, cookie_file=instagram_cookie_file)

    cookie_file = (instagram_cookie_file or "").strip()
    use_instagram_cookies = _is_instagram_url(url) and cookie_file and Path(cookie_file).is_file()

    channel_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": max_videos,
        "socket_timeout": 20,
    }
    if use_instagram_cookies:
        channel_opts["cookiefile"] = cookie_file

    try:
        with YoutubeDL(channel_opts) as ydl:
            channel_info = _extract_info_with_backoff(ydl, url)
    except DownloadError as exc:
        details = str(exc)
        lower = details.lower()
        if _is_tiktok_url(url) and _is_tiktok_user_extract_error(details):
            try:
                return _fetch_tiktok_channel_data_from_page(url, max_videos=max_videos)
            except Exception as fallback_exc:
                raise YtDlpFetchError(f"Failed to fetch TikTok channel: {details}. Fallback failed: {fallback_exc}") from exc
        if "instagram" in lower and "unable to extract data" in lower:
            raise YtDlpFetchError(
                "Instagram extraction is currently blocked in yt-dlp. "
                "Try again later, update yt-dlp, or refresh with valid Instagram cookies."
            ) from exc
        if "429" in lower:
            raise YtDlpFetchError("Source rate-limited the request (HTTP 429). Please try again later.") from exc
        raise YtDlpFetchError(f"Failed to fetch channel: {details}") from exc

    if not channel_info:
        raise YtDlpFetchError("No data returned by yt-dlp for this channel URL.")

    entries = channel_info.get("entries") or []
    videos: list[VideoPayload] = []
    avatar_url = _extract_avatar(channel_info, source_url=url)
    if (not avatar_url) and _is_tiktok_url(url):
        avatar_url = _fetch_tiktok_avatar_from_page(url)
    if (not avatar_url) and _is_youtube_url(url):
        avatar_url = _fetch_youtube_avatar_from_profile(url)
    video_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": 20,
    }
    if use_instagram_cookies:
        video_opts["cookiefile"] = cookie_file

    with YoutubeDL(video_opts) as video_ydl:
        for entry in entries[:max_videos]:
            entry_url = entry.get("url") or entry.get("webpage_url")
            if not entry_url:
                continue
            if not str(entry_url).startswith("http"):
                entry_url = f"https://www.youtube.com/watch?v={entry_url}"

            # Prefer already available metadata from playlist entries to reduce network calls.
            title = entry.get("title") or "Untitled video"
            upload_date = _parse_upload_date(entry.get("upload_date"))
            view_count = entry.get("view_count")
            like_count = entry.get("like_count")
            comment_count = entry.get("comment_count")
            duration_seconds = entry.get("duration")
            thumbnail_url = _pick_first_url(entry.get("thumbnail")) or _pick_best_thumbnail(entry.get("thumbnails"))

            need_details = (
                upload_date is None
                or view_count is None
                or (like_count is None and comment_count is None)
                or thumbnail_url is None
            )
            details: dict[str, Any] = {}
            if need_details:
                try:
                    maybe_details = _extract_info_with_backoff(video_ydl, str(entry_url))
                    if isinstance(maybe_details, dict):
                        details = maybe_details
                except DownloadError:
                    details = {}

            videos.append(
                VideoPayload(
                    title=details.get("title") or title,
                    url=details.get("webpage_url") or str(entry_url),
                    upload_date=_parse_upload_date(details.get("upload_date")) or upload_date,
                    duration_seconds=details.get("duration") or duration_seconds,
                    view_count=details.get("view_count") if details.get("view_count") is not None else view_count,
                    like_count=details.get("like_count") if details.get("like_count") is not None else like_count,
                    comment_count=(
                        details.get("comment_count") if details.get("comment_count") is not None else comment_count
                    ),
                    thumbnail_url=_extract_video_thumbnail(details, entry) if details else thumbnail_url,
                )
            )
    channel_title = channel_info.get("title") or channel_info.get("channel") or "Unknown channel"
    canonical_url = (
        channel_info.get("webpage_url")
        or channel_info.get("channel_url")
        or channel_info.get("uploader_url")
        or url
    )
    subscriber_count = (
        channel_info.get("channel_follower_count")
        or channel_info.get("subscriber_count")
        or channel_info.get("followers")
    )
    return ChannelPayload(
        title=channel_title,
        url=canonical_url,
        avatar_url=avatar_url,
        subscriber_count=subscriber_count,
        videos=videos,
    )
