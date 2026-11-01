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

## More documentation

- [SPEC.md](SPEC.md): what the app does and how pages behave
- [DESIGN.md](DESIGN.md): design notes
- [DEPLOYMENT.md](DEPLOYMENT.md): step-by-step guide to hosting on AWS with HTTPS and nightly backups
