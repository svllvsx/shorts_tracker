# Deploy In Docker On Ubuntu VPS

This guide is for deploying this project as a Docker container on Ubuntu (22.04/24.04).

## 1. What Is Already Portable

- App stack: FastAPI + SQLite + yt-dlp.
- No Windows-only runtime dependencies in Python code.
- Cookies are stored inside project data (`data/cookies/instagram_cookies.txt`) after upload.

Important:
- SQLite file (`yt_analytics.db`) and `settings.toml` should be persisted via Docker volumes/bind mounts.
- Avatar cache is written to `app/static/avatars`, so persist it too.
- Telegram auth secrets should be stored in `.env` (do not commit `.env` to git).

## 2. Prepare VPS

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg

# Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker
```

## 3. Copy Project To VPS

Example target folder:

```bash
sudo mkdir -p /opt/yt-analytics
sudo chown -R $USER:$USER /opt/yt-analytics
```

Copy full project folder there (scp/rsync/git clone), then:

```bash
cd /opt/yt-analytics
```

## 4. Create `.dockerignore`

Create file `.dockerignore`:

```dockerignore
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.git
.gitignore
SESSION_LOG.md
run_service.ps1
1.png
```

## 5. Create `Dockerfile`

Create file `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY settings.toml ./settings.toml

# Runtime writable dirs/files will be mounted from host:
# /app/yt_analytics.db
# /app/data/cookies
# /app/app/static/avatars

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 6. Prepare Persistent Host Paths

```bash
mkdir -p data/cookies
mkdir -p app/static/avatars
touch yt_analytics.db
cp .env.example .env
```

Optional: if you already have DB/cookies from Windows, copy:
- `yt_analytics.db`
- `data/cookies/instagram_cookies.txt`

## 7. Create `docker-compose.yml`

Create file `docker-compose.yml`:

```yaml
services:
  yt-analytics:
    build: .
    container_name: yt-analytics
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./yt_analytics.db:/app/yt_analytics.db
      - ./settings.toml:/app/settings.toml
      - ./data/cookies:/app/data/cookies
      - ./app/static/avatars:/app/app/static/avatars
    env_file:
      - .env
    environment:
      - TZ=${TZ:-Europe/Moscow}
```

Create `.env` in project root (example):

```env
TELEGRAM_BOT_USERNAME=your_bot_username
TELEGRAM_BOT_TOKEN=123456789:replace_with_real_token
TELEGRAM_ALLOWED_USER_ID=123456789
TZ=Europe/Moscow
```

## 8. Build + Run

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

Check:
- `http://SERVER_IP:18080/dashboard`

## 9. Optional Nginx Reverse Proxy + Domain

If you need HTTPS/domain, put Nginx in front of app:
- Nginx listens on `80/443`.
- Proxies to `http://127.0.0.1:8000`.
- TLS via Certbot.

Minimal Nginx site example:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 10. Update Process

When code changes:

```bash
cd /opt/yt-analytics
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose logs -f
```

## 11. Backup

Backup these files/folders:
- `yt_analytics.db`
- `settings.toml`
- `.env`
- `data/cookies/`
- `app/static/avatars/`

Quick backup command:

```bash
tar -czf yt-analytics-backup-$(date +%F_%H-%M).tar.gz \
  yt_analytics.db settings.toml .env data/cookies app/static/avatars
```

## 12. Common Issues

- `Permission denied` on mounted files:
  - fix ownership on host folder (`chown -R $USER:$USER /opt/yt-analytics`).
- `Instagram cookies invalid`:
  - upload fresh cookies in Settings and use built-in cookie check.
- Empty refresh data:
  - this is usually source/platform-side (rate limit, blocked extraction, invalid cookies), not Docker.

## 13. Quick Readiness Verdict For Current Project

Yes, project is ready for Docker deploy on Ubuntu with the setup above.
Main production concern is persistence (DB/settings/cookies/avatars), already covered by compose mounts in this guide.
