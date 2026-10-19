# Smart Notes – Deploy to Render Plan

The version 1 plan is now in `PLAN-v1.md`.

## Context
Smart Notes runs on my Mac with `flask --app app run --debug`. I want it online through
[Render](https://render.com), deployed from the GitHub repo `Sajoy2129/smart-notes`. Once it's on
the internet, anyone can find the URL, so the app needs:

1. a **login**, so only I can read my notes,
2. **production settings** (gunicorn, debug off, a real secret key),
3. **environment variables** for secrets and settings instead of the `.env` file,
4. a **usage limit**, so nobody (including a bug of mine) can run up my Claude API bill.

Every step below ends with passing tests and one small git commit, the same way version 1 was
built.

---

## Decision first: where do the notes live?
The notes are kept in a SQLite file. **On Render, a web service's disk is temporary.** It's wiped
on every deploy and restart, so a SQLite file there would lose all notes each time I push code.

| Option | Cost | Code changes | Notes kept? |
|---|---|---|---|
| **A. Paid instance + persistent disk** (recommended) | Starter instance + small disk (check Render's pricing page) | Only the database path | Yes |
| B. Render Postgres database | Free tier expires; paid after | Rewrite `db.py` for Postgres | Yes |
| C. Free instance, no disk | Free | None | **No**, wiped on each deploy |

**Chosen: A** (decided 2026-10-19). A *persistent disk* is storage that survives deploys. Render mounts it at a
folder such as `/var/data`, and I set `DATABASE_PATH=/var/data/smart_notes.db`. `db.py` stays as it
is. Option B is a good thing to learn later, but it's a big change made just for hosting.

Also good to know: free instances go to sleep after about 15 minutes without visitors, and the
next visit waits about a minute while the app wakes up.

The Render database starts **empty**. My local notes stay on my Mac.

---

## 1. Environment variables instead of `.env`

**What:** An *environment variable* is a named setting that the operating system gives a
program when it starts, like `ANTHROPIC_API_KEY=sk-...`. Python reads one with `os.getenv("NAME")`.

**Why:** `.env` is in `.gitignore` (correctly), so it never reaches GitHub, and Render never sees
it. On Render I type each secret into the service's **Environment** tab. Render keeps it encrypted
and passes it to the app on start. Secrets stay out of the code and out of git.

**How it fits my code:** `load_dotenv()` copies `.env` into environment variables, but only for
names that aren't already set. So:
- On my Mac, `.env` exists, `load_dotenv()` fills in the values, and everything works as before.
- On Render, there's no `.env`, `load_dotenv()` does nothing, and the real environment variables
  are used.

The same code works in both places. I'll move the `load_dotenv()` call from `ai.py` into
`create_app()` so it loads every setting, not only the API key.

**All settings the app will read:**

| Variable | Example | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API (already used) |
| `SECRET_KEY` | 64 random hex characters | Signs the login cookie (see 2) |
| `APP_PASSWORD_HASH` | `scrypt:32768:8:1$...` | My login password, hashed (see 3) |
| `DATABASE_PATH` | `/var/data/smart_notes.db` | Where SQLite lives (default: `smart_notes.db`) |
| `AI_DAILY_LIMIT` | `50` | Max AI jobs per day (see 4) |
| `PYTHON_VERSION` | `3.13.7` | Tells Render which Python to use (matches my `.venv`) |

Render also sets `RENDER_EXTERNAL_HOSTNAME` (e.g. `smart-notes.onrender.com`) automatically. I'll
add it to `TRUSTED_HOSTS` so the app accepts requests sent to its own URL. Right now it only
accepts `localhost`.

**Fail fast:** if `SECRET_KEY` or `APP_PASSWORD_HASH` is missing, the app refuses to start and
prints a clear error. A loud crash at deploy time is better than a silently insecure app.

---

## 2. Production settings

### gunicorn
**What:** `flask run` starts Flask's *development server*. It's meant for one person on one
machine and isn't built to be secure or fast. **gunicorn** is a production *WSGI server*. WSGI is
the standard way Python web apps talk to web servers. gunicorn handles many requests reliably
and restarts a crashed worker.

**How:** add `gunicorn` to `requirements.txt`. Render's start command is:
```
gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```
- `app:create_app()` means "in `app.py`, call `create_app()` to get the app".
- `$PORT` is the port Render tells the app to listen on.
- 1 worker with 4 threads: SQLite works best with a single process, and threads still let a few
  requests run at once.
- `--timeout 120`: a Claude call can take a while (its own timeout is 60s, and it may retry once).

### Debug off
**What:** debug mode shows full error pages with code, and its interactive debugger can **run
Python typed into the browser**. Online, that would let anyone take over the server.

**How:** gunicorn never turns on debug mode, and the start command doesn't include `--debug`.
`--debug` stays in my local `flask run` command only. I'll add a test that checks
`app.debug is False`.

### A real secret key
**What:** Flask *signs* the session cookie with `SECRET_KEY`. Signing adds a code that only the
holder of the key can produce. After I log in, the cookie says "logged in". Without the key, nobody
can forge that cookie.

**Why the current code must change:** `app.secret_key = os.urandom(32)` makes a new random key
each time the app starts. That was fine for flash messages, but with a login, every restart or
deploy would log me out. The key must stay the same and stay secret, so it comes from
`SECRET_KEY`. To make one:
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### HTTPS behind Render's proxy
Render receives the HTTPS request and passes it to my app as plain HTTP. This middle layer is a
*proxy*. My CSRF check compares the browser's `Origin` (`https://...`) with `request.host_url`
(`http://...`). These won't match, so **every form would get a 403**. Werkzeug's `ProxyFix`
makes the app trust Render's `X-Forwarded-Proto` header, so it knows the request was really HTTPS.

### Cookie settings
- `SESSION_COOKIE_SECURE=True`: the cookie is only sent over HTTPS.
- `SESSION_COOKIE_HTTPONLY=True` (the default): JavaScript can't read the cookie.
- `SESSION_COOKIE_SAMESITE="Lax"`: other sites can't send POSTs that carry the cookie. This adds
  to the Origin check.

For local runs over `http://`, `SESSION_COOKIE_SECURE` must be off, or the browser drops the
cookie. I'll turn it on only when running on Render (Render sets `RENDER=true`).

---

## 3. A simple login

**What:** this is a single-user login with no usernames, no sign-up page and no database table. I
have one password, and the app keeps only its *hash*.

**Why a hash:** a *hash* is a one-way scramble. Werkzeug's `generate_password_hash()` turns my
password into `scrypt:...`. `check_password_hash()` can tell whether a typed password matches, but
nobody can turn the hash back into the password. Even if the environment variables leaked, the
password wouldn't. To make the hash without the password ending up in my shell history:
```
python3 -c "import getpass; from werkzeug.security import generate_password_hash as h; print(h(getpass.getpass()))"
```

**How it works:**
- `GET /login` shows a password box. `POST /login` checks the password. If it's right, the app
  sets `session["logged_in"] = True` and sends me to the page I asked for. If it's wrong, it waits
  1 second and shows "Wrong password". The delay makes guessing slow.
- `POST /logout` clears the session. It's POST for the same reason as Delete: a link must never
  change anything.
- One `@app.before_request` check sends every request to `/login` unless I'm logged in. The only
  exceptions are `/login` itself and `/static/...` (the CSS). Because it's one central check, a
  new page can't forget to be protected.
- The login lasts 30 days (`session.permanent` plus `PERMANENT_SESSION_LIFETIME`), so I don't
  type the password every visit.
- The top bar gets a "Log out" button. `SPEC.md` "Who uses it" is updated.

**Password advice:** use a long random password (16+ characters, from a password manager). With
the 1-second delay, guessing it would take forever.

**Tests:** logged out → redirect to `/login`. Wrong password → stays out. Right password → in.
Logout → out again. Static CSS loads without login. The `client` fixture in `conftest.py` will log
in first, so the existing tests keep working.

---

## 4. Usage limit (protecting my API credit)

The login already stops strangers. The limit is a second safety net, in case the password leaks,
a bug loops, or I paste a huge note by accident. Three layers, from strongest to finest:

1. **Hard cap in the Anthropic Console (outside my code).** Set a monthly spend limit under
   *Settings → Limits*, and create a **separate API key just for Render**. If something goes
   wrong, I can revoke that one key without touching my local one. This is the only limit that
   still works if my code has a bug, so it's the most important.

2. **Daily AI limit in the app.** A new table `ai_usage (day TEXT PRIMARY KEY, jobs INTEGER)`.
   Before each AI job (analysing a note or answering a question), `db.use_ai_job(limit)` adds 1 to
   today's count in a single SQL statement, but only if the count is below `AI_DAILY_LIMIT` (default
   50). It's stored in the database rather than a Python variable, so it survives restarts.
   - When the limit is reached, the note is **still saved**, just without AI fields. This works
     like an API failure today, and the page explains why. Ask shows "Daily AI limit reached, try
     again tomorrow."
   - One job can make up to 2 API calls (the retry), so the worst case is 100 calls a day.

3. **Size limits.** Notes are capped at 10,000 characters and questions at 500, checked in the
   routes with a friendly error. This limits the cost of any single call.

**Tests:** the limit is reached → the note is saved with no AI call (the fake client shows zero
calls). The count resets on a new day. A note that's too long → error, nothing saved.

---

## Steps (one commit each)
0. **Plan.** `PLAN-v1.md` (renamed) plus this `PLAN.md`. Add `.DS_Store` to `.gitignore`.
1. **Settings from the environment.** `load_dotenv()` in `create_app()`, `SECRET_KEY`,
   `DATABASE_PATH`, `RENDER_EXTERNAL_HOSTNAME` in `TRUSTED_HOSTS`, `ProxyFix`, cookie settings,
   and fail fast on missing secrets. `create_app()` takes a test config so tests don't need real
   secrets. Add `SECRET_KEY` and `APP_PASSWORD_HASH` to my local `.env`.
2. **Login.** `/login`, `/logout`, the `before_request` check, `login.html`, a Log out button, a
   logged-in test fixture and new tests. Update `SPEC.md`.
3. **Usage limit.** `ai_usage` table, `db.use_ai_job()`, size limits, messages and tests.
4. **gunicorn.** Add it to `requirements.txt`. Run it locally to check:
   `gunicorn "app:create_app()" --bind 127.0.0.1:8000`.
5. **Deploy (done in the Render dashboard, no commit).**
   - Anthropic Console: create a new key for Render and set a monthly spend limit.
   - Render: *New → Web Service → connect GitHub repo*. Build command
     `pip install -r requirements.txt`. Start command as in section 2. Pick the instance type.
     Add a disk mounted at `/var/data` (option A).
   - Add the environment variables from section 1.
   - Deploy, then follow the checks below.
6. **Review.** Run the `code-reviewer` agent (or `/security-review`) on the changes and fix
   anything serious.

## Verification
- `pytest -v` passes, still with no real API calls.
- Local: `flask --app app run --debug` still works with `.env`.
- On the Render URL:
  - A private browser window redirects to `/login`, and a wrong password is refused.
  - Log in, add a note, and the summary appears (the Origin check and HTTPS work).
  - Deploy again (e.g. an empty commit). I'm still logged in and the note is still there (the
    secret key and disk work).
  - Temporarily set `AI_DAILY_LIMIT=0`. The note saves with the "limit reached" message.
  - Visit a URL that doesn't exist. It shows the normal 404 page, not a debug page.
- `git log -p` contains no secrets.
