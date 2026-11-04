# Smart Notes

A small Flask web app for saving rough notes (meeting notes, site visit notes, phone calls). When you save a note, Claude writes a short summary, pulls out action items, and adds tags. You can also ask questions across all your notes and see which notes each answer came from.

## Features

- Notes grouped into projects, with a sidebar showing open-note counts
- AI summary, action items (task, owner, due date) and tags for every note
- Ask page: keyword search finds the relevant notes, and Claude answers only from them
- Single-password login (no usernames, no sign-up), 30-day session
- Daily limit on AI calls to keep API costs under control
- SQLite by default, with optional PostgreSQL via `DATABASE_URL`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (it is git-ignored):

```
ANTHROPIC_API_KEY=your-key
SECRET_KEY=<output of: python3 -c "import secrets; print(secrets.token_hex(32))">
APP_PASSWORD_HASH=<hash of your login password>
```

Make the password hash with:

```bash
python -c "import getpass; from werkzeug.security import generate_password_hash as h; print(h(getpass.getpass()))"
```

Optional settings: `DATABASE_URL` or `DATABASE_PATH`, `AI_DAILY_LIMIT` (default 50), `BEHIND_PROXY`, `PUBLIC_HOSTNAME`.

## Run

```bash
flask --app app run --debug
```

Then open http://127.0.0.1:5000 and log in.

## Run with Docker

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and the `.env` file from Setup. Secrets and data are given to the container when it runs; they are never built into the image.

**App + PostgreSQL (Docker Compose).** First create `db.env`, the database password file (git-ignored):

```bash
cp db.env.example db.env
python3 -c "import secrets; print(secrets.token_hex(24))"   # put this in BOTH lines of db.env
```

Then:

```bash
docker compose up -d --build   # start the database, then the app
docker compose logs -f app     # follow the app's logs (Ctrl+C stops following)
docker compose down            # stop; notes are kept in the pg-data volume
```

Open http://localhost:8000 and log in. The database has no port open on your machine; only the app can reach it. Use `docker compose exec db psql -U smart_notes` to look inside. `docker compose down -v` also **deletes the database**.

**App only, with SQLite:**

```bash
docker build -t smart-notes .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v "$PWD/.env:/app/.env:ro" -v smart-notes-data:/data smart-notes
```

The `.env` file is mounted read-only instead of passed with `--env-file`, because `--env-file` would keep the quote marks around `APP_PASSWORD_HASH` and the login would fail.

## Tests

```bash
pytest
```

## Project layout

| Path | What it is |
| --- | --- |
| `app.py` | Flask routes, settings and login |
| `ai.py` | Claude API calls (note analysis and Ask) |
| `db.py` | Database access |
| `search.py` | Keyword search for the Ask page |
| `templates/`, `static/` | HTML pages and CSS |
| `tests/` | pytest suite |
| `deploy/` | Caddy, systemd and backup files for the AWS server |
| `Dockerfile`, `.dockerignore` | Docker image for the app |
| `compose.yaml`, `db.env.example` | Docker Compose: app + PostgreSQL |

## More documentation

- [SPEC.md](SPEC.md): what the app does and how pages behave
- [DESIGN.md](DESIGN.md): design notes
- [DEPLOYMENT.md](DEPLOYMENT.md): step-by-step guide to hosting on AWS with HTTPS and nightly backups
