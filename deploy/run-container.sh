#!/usr/bin/env bash
# Build the Smart Notes image on the server and (re)start it as a container.
# Replaces the systemd service (deploy/smart-notes.service); see deploy/README.md.
# Run it from anywhere, after `git pull`:   sudo ~/smart-notes/deploy/run-container.sh
#
# Nothing else changes: Caddy still proxies to 127.0.0.1:8000, the database stays in
# /home/ubuntu/data (so backup.sh and its cron line keep working), and .env stays put.

# Stop at the first error, and treat unset variables as errors.
set -euo pipefail

# The ${VAR:-default} form allows other paths, only for testing it on a laptop.
APP_DIR="${APP_DIR:-/home/ubuntu/smart-notes}"
DATA_DIR="${DATA_DIR:-/home/ubuntu/data}"
NAME=smart-notes   # used for both the image and the container

cd "$APP_DIR"

echo "== Building the image"
docker build -t "$NAME" .

# Stop the old container first: two copies can't share port 8000 (or the database).
# `docker stop` asks gunicorn to finish its requests and exit (unlike `rm -f`).
if docker container inspect "$NAME" >/dev/null 2>&1; then
    echo "== Stopping the old container"
    docker stop "$NAME"
    docker rm "$NAME"
fi

echo "== Starting the new container"
# --restart unless-stopped: start again after a crash or a reboot, like systemd did.
# -p 127.0.0.1:...: only Caddy, on this server, can reach the app.
# .env is lent read-only; /data is the folder that holds smart_notes.db.
# DATABASE_PATH is set here on purpose: it wins over the server path in .env,
#   which doesn't exist inside the container.
# --log-opt: keep at most 3 x 10 MB of logs, so they can't fill the 8 GB disk.
docker run -d \
    --name "$NAME" \
    --restart unless-stopped \
    -p 127.0.0.1:8000:8000 \
    -v "$APP_DIR/.env:/app/.env:ro" \
    -v "$DATA_DIR:/data" \
    -e DATABASE_PATH=/data/smart_notes.db \
    --log-opt max-size=10m --log-opt max-file=3 \
    "$NAME"

# Wait up to 20 seconds for the login page, so a broken start is noticed now.
echo "== Checking the app"
for _ in $(seq 20); do
    if curl -fs -o /dev/null http://127.0.0.1:8000/login; then
        echo "OK: the app answers on 127.0.0.1:8000"
        exit 0
    fi
    sleep 1
done
echo "ERROR: no answer after 20 seconds. Last log lines:" >&2
docker logs --tail 30 "$NAME" >&2
exit 1
