# Docker image for Smart Notes. Build and run it as shown in the plan:
#   docker build -t smart-notes .
#   docker run --rm -p 127.0.0.1:8000:8000 \
#     -v "$PWD/.env:/app/.env:ro" -v smart-notes-data:/data smart-notes
# Secrets (.env) and data (the database) are given at run time, never built in.

# Small official Python image, same version as on the Mac (3.13).
FROM python:3.13-slim

# Don't write .pyc files; print logs straight away (no buffering), so `docker logs`
# shows them. The app uses local time, like the server. The SQLite file lives in /data.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Dubai \
    DATABASE_PATH=/data/smart_notes.db

# Slim images have no time-zone data, so add it (otherwise TZ is ignored).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first: Docker caches this layer, so a code change doesn't
# reinstall every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the code. .dockerignore keeps secrets, data and junk out.
COPY . .

# Never run as root (same rule as the systemd service). /data holds the database.
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

EXPOSE 8000

# 0.0.0.0 = listen on every network interface inside the container; 127.0.0.1 would
# be unreachable from outside it. Same gunicorn settings as deploy/smart-notes.service.
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--threads", "4", "--timeout", "120"]
