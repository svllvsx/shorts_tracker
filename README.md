# Shorts Tracker

FastAPI web app for public short-video channel analytics (YouTube, TikTok, Instagram) using `yt-dlp` and platform fallbacks.

## Features
- FastAPI + Jinja2 templates
- Landing page + dashboard
- Add channels by URL (`youtube.com`, `tiktok.com`, `instagram.com`)
- Fetch and store latest N videos per channel in SQLite via SQLModel
- Per channel aggregates:
  - total views (sum of stored videos)
  - average views
  - uploads per week over last 30 days
- Per-channel refresh + global refresh
- Cache guard: skips refresh when last refresh is less than configured interval (unless forced)
- Instagram cookies upload + validation from Settings
- Platform grouping and charts (total/average views by channel)
- Friendly error messages for yt-dlp failures
- Config via `settings.toml`

## Screenshots

![Dashboard](shots/1.png)
![Charts](shots/2.png)
![Settings](shots/3.png)
![Mobile](shots/4.png)
![Theme](shots/5.png)

## Quick Start (Docker)

```bash
git clone https://github.com/svllvsx/shorts_tracker.git
cd shorts_tracker
mkdir -p data/cookies app/static/avatars && touch yt_analytics.db
docker compose up -d --build
docker compose logs -f
```

Open:
- http://127.0.0.1:8000/dashboard

## Project structure
```text
shorts-tracker/
  app/
    services/
      ytdlp_service.py
    static/
      style.css
    templates/
      base.html
      index.html
      dashboard.html
    db.py
    main.py
    models.py
    settings.py
  settings.toml
  requirements.txt
  README.md
```

## Setup (Windows PowerShell)
```powershell
cd C:\Data\Soft\yt-analytics
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```powershell
uvicorn app.main:app --reload
```

Open in browser:
- http://127.0.0.1:8000/
- Dashboard: http://127.0.0.1:8000/dashboard

## Settings
Edit `settings.toml`:
```toml
[app]
refresh_interval_hours = 6
max_videos_per_channel = 12
```

## Notes
- Main data source is `yt-dlp` with platform-specific fallbacks for unstable endpoints.
- Some channels/videos may not expose `like_count`; UI shows `-` in that case.
- Database file is `yt_analytics.db` in project root.
