# yt-analytics

Minimal FastAPI web app for public YouTube channel analytics using `yt-dlp` (no OAuth).

## Features
- FastAPI + Jinja2 templates
- Landing page + dashboard
- Add channels by URL (`https://www.youtube.com/@handle` also works)
- Fetch and store latest N videos per channel in SQLite via SQLModel
- Per channel aggregates:
  - total views (sum of stored videos)
  - average views
  - uploads per week over last 30 days
- Per-channel refresh + global refresh
- Cache guard: skips refresh when last refresh is less than configured interval (unless forced)
- Friendly error messages for yt-dlp failures
- Config via `settings.toml`

## Project structure
```text
yt-analytics/
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
- Data source is `yt-dlp` only.
- Some channels/videos may not expose `like_count`; UI shows `-` in that case.
- Database file is `yt_analytics.db` in project root.
