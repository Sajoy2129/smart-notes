# Smart Notes – Deploy to AWS Plan

The version 1 plan is now in `PLAN-v1.md`.

## Context
Smart Notes runs on my Mac with `flask --app app run --debug`. I want it online on
**AWS** (Amazon Web Services), on the free plan, deployed from the GitHub repo
`Sajoy2129/smart-notes`. Once it's on the internet, anyone can find the URL, so the app needs:

1. a **login**, so only I can read my notes,
2. **production settings** (gunicorn, debug off, a real secret key),
3. **environment variables** for secrets and settings,
4. a **usage limit**, so nobody (including a bug of mine) can run up my Claude API bill.

Every step below ends with passing tests and one small git commit, the same way version 1 was
built.

History: the first plan used Render with a paid disk (option A, 2026-10-19), then free Render
plus free Neon Postgres (option D, 2026-10-20). **On 2026-10-26 I switched to AWS.** Steps 0–4
(settings, login, usage limit, gunicorn) were already done and still apply.

---

## What "free" means on AWS
AWS changed its free tier on **15 July 2025**:

- **New accounts** choose a **Free plan**. It comes with about **$100 in credits**, plus up to
  $100 more for finishing a few starter tasks (one is launching an EC2 server). Everything I use,
  including the server, is paid for from these credits.
- The Free plan lasts **6 months** or until the credits run out, whichever comes first. Then the
  account is closed unless I **upgrade to a paid plan**. AWS can't charge my card while I'm on
  the Free plan.
- The old "750 free hours a month for 12 months" only applies to accounts made before
  15 July 2025. Those 12 months have now ended, even for the oldest such accounts.

So this deploy is **free for about 6 months**, not forever. After that I either pay (about
$10–15 a month for this setup) or move the app somewhere else. I'll check the official
[AWS Free Tier page](https://aws.amazon.com/free/) before signing up, because the details may
change.

---

## Decision first: where do the app and the notes live?

| Option | Cost on the Free plan | Code changes | Notes kept? |
|---|---|---|---|
| **A. One EC2 server, SQLite on its disk** (chosen) | Credits, about $10–15/month | Small: proxy settings only | Yes |
| B. EC2 server + RDS Postgres database | Credits, roughly twice as fast | Rewrite `db.py` for Postgres | Yes |
| C. Lambda + DynamoDB ("always free") | Free | Rewrite almost everything | Yes |

**Why A:** an **EC2 instance** is a virtual computer that I rent from AWS. Its disk (an **EBS
volume**) is *persistent*: files stay there through restarts and deploys, unlike Render's free
instance. So my SQLite database can stay exactly as it is. There is no Postgres rewrite and no
copy script. I copy `smart_notes.db` to the server once.

**Why not C:** Lambda runs code only for the moment a request comes in, and has no disk that
lasts. SQLite can't work there, and the app would need a new database and a new structure.

**Trade-off:** with a server of my own, I'm also its administrator. I install updates, keep
the app running, and take backups. That's good practice for an AI Engineer, and the steps below
cover each part.

Unlike Render's free instance, an EC2 server never sleeps, so there's no slow first visit.

### The pieces
```
browser ──HTTPS──▶ Caddy (port 443) ──HTTP──▶ gunicorn (127.0.0.1:8000) ──▶ Flask app ──▶ SQLite file
                   └──────────────────── one EC2 server (Ubuntu, Frankfurt) ───────────────────┘
```
- **Region:** `eu-central-1` (Frankfurt).
- **Server:** an EC2 `t3.micro` (2 virtual CPUs, 1 GB memory) running **Ubuntu 24.04**.
- **Elastic IP:** a fixed public IP address, so the address doesn't change when the server
  restarts.
- **Security group:** AWS's firewall. It decides which network ports are open:
  - port 22 (SSH, logging in to the server): **only from my home IP address**,
  - ports 80 and 443 (HTTP and HTTPS): from anywhere.
- **Caddy:** a web server in front of gunicorn. It gets a free HTTPS certificate from
  Let's Encrypt and renews it automatically.
- **systemd:** Ubuntu's service manager. It starts gunicorn when the server boots and restarts
  it if it crashes.

### A name for HTTPS
HTTPS certificates are issued for a **domain name**, not a bare IP address. I'll start with a
free name from [sslip.io](https://sslip.io). It turns an IP address into a name: the Elastic IP
`3.120.45.67` becomes `3-120-45-67.sslip.io`. Later I can buy my own domain and only change the
name in the Caddyfile and `PUBLIC_HOSTNAME`.

---

## 1. Environment variables

**What:** An *environment variable* is a named setting that the operating system gives a
program when it starts, like `ANTHROPIC_API_KEY=sk-...`. Python reads one with `os.getenv("NAME")`.

**How it fits my code:** `load_dotenv()` in `create_app()` copies `.env` into environment
variables, but only for names that aren't already set. `.env` is in `.gitignore` (correctly), so
it never reaches GitHub. On the server I create a **separate `.env`** in the app folder, by
hand, with production values. I lock it with `chmod 600 .env`, so only its owner can read it.
The same code works in both places.

**All settings the app reads:**

| Variable | Example | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API. **A separate key for the server** (see 4) |
| `SECRET_KEY` | 64 random hex characters | Signs the login cookie (see 2). A new one for the server |
| `APP_PASSWORD_HASH` | `'scrypt:32768:8:1$...'` | My login password, hashed (see 3). Single-quoted |
| `DATABASE_PATH` | `/home/ubuntu/data/smart_notes.db` | Where the SQLite file lives. Outside the git folder |
| `AI_DAILY_LIMIT` | `50` | Max AI jobs per day (see 4) |
| `BEHIND_PROXY` | `true` | **New.** Caddy sits in front, so trust its HTTPS header (see 2) |
| `PUBLIC_HOSTNAME` | `3-120-45-67.sslip.io` | **New.** The server's name, added to `TRUSTED_HOSTS` |

`BEHIND_PROXY` and `PUBLIC_HOSTNAME` replace the Render-only `RENDER` and
`RENDER_EXTERNAL_HOSTNAME`. On my Mac I leave both unset, so nothing changes locally.

**Fail fast:** if `SECRET_KEY` or `APP_PASSWORD_HASH` is missing, the app refuses to start and
prints a clear error. A loud crash at deploy time is better than a silently insecure app.

---

## 2. Production settings

### gunicorn
**What:** `flask run` starts Flask's *development server*. It's meant for one person on one
machine and isn't built to be secure or fast. **gunicorn** is a production *WSGI server*. WSGI is
the standard way Python web apps talk to web servers. gunicorn handles many requests reliably
and restarts a crashed worker.

**How:** gunicorn is already in `requirements.txt`. The systemd service runs:
```
gunicorn "app:create_app()" --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120
```
- `app:create_app()` means "in `app.py`, call `create_app()` to get the app".
- `127.0.0.1:8000`: gunicorn listens only *inside* the server. The internet can't reach it
  directly, only through Caddy.
- 1 worker with 4 threads: SQLite works best with a single process, and threads still let a few
  requests run at once.
- `--timeout 120`: a Claude call can take a while (its own timeout is 60s, and it may retry once).

### Debug off
**What:** debug mode shows full error pages with code, and its interactive debugger can **run
Python typed into the browser**. Online, that would let anyone take over the server.

**How:** gunicorn never turns on debug mode, and the service command doesn't include `--debug`.
`--debug` stays in my local `flask run` command only. A test checks `app.debug is False`.

### A real secret key
Flask *signs* the session cookie with `SECRET_KEY`, so nobody without the key can forge a
"logged in" cookie. It must stay the same across restarts and stay secret. To make one:
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### HTTPS behind Caddy
Caddy receives the HTTPS request and passes it to gunicorn as plain HTTP. This middle layer is
a *proxy*. My CSRF check compares the browser's `Origin` (`https://...`) with `request.host_url`
(`http://...`). These won't match, so **every form would get a 403**. Werkzeug's `ProxyFix`
makes the app trust Caddy's `X-Forwarded-Proto` header, so it knows the request was really
HTTPS. It's switched on only when `BEHIND_PROXY=true`. Without a proxy in front, anyone could
send that header.

### Cookie settings
- `SESSION_COOKIE_SECURE=True`: the cookie is only sent over HTTPS.
- `SESSION_COOKIE_HTTPONLY=True` (the default): JavaScript can't read the cookie.
- `SESSION_COOKIE_SAMESITE="Lax"`: other sites can't send POSTs that carry the cookie. This adds
  to the Origin check.

For local runs over `http://`, `SESSION_COOKIE_SECURE` must be off, or the browser drops the
cookie. It's turned on only when `BEHIND_PROXY=true`.

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
Logout → out again. Static CSS loads without login. The `client` fixture in `conftest.py` logs
in first, so the existing tests keep working.

---

## 4. Usage limits (protecting my API credit and my AWS credits)

The login already stops strangers. The limits are a second safety net, in case the password
leaks, a bug loops, or I paste a huge note by accident.

1. **Hard cap in the Anthropic Console (outside my code).** Set a monthly spend limit under
   *Settings → Limits*, and create a **separate API key just for the server**. If something goes
   wrong, I can revoke that one key without touching my local one. This is the only limit that
   still works if my code has a bug, so it's the most important.

2. **Daily AI limit in the app.** A table `ai_usage (day TEXT PRIMARY KEY, jobs INTEGER)`.
   Before each AI job (analysing a note or answering a question), `db.use_ai_job(limit)` adds 1 to
   today's count in a single SQL statement, but only if the count is below `AI_DAILY_LIMIT` (default
   50). It's stored in the database rather than a Python variable, so it survives restarts.
   - When the limit is reached, the note is **still saved**, just without AI fields. This works
     like an API failure today, and the page explains why. Ask shows "Daily AI limit reached, try
     again tomorrow."
   - One job can make up to 2 API calls (the retry), so the worst case is 100 calls a day.

3. **Size limits.** Notes are capped at 10,000 characters and questions at 500, checked in the
   routes with a friendly error. This limits the cost of any single call.

4. **AWS budget alert.** In *Billing → Budgets*, create a budget that emails me when credit use
   passes $5 in a month. Then a mistake, like a forgotten extra server, shows up early.

---

## 5. Running the server

### Getting the code onto the server
The GitHub repo is private, so the server needs permission to read it. I'll make a **deploy
key**: an SSH key created on the server and added to the repo under *Settings → Deploy keys*,
**read-only**. It can clone this one repo and nothing else, and can't push.

### Updating the app later
```
ssh ubuntu@3-120-45-67.sslip.io
cd smart-notes && git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart smart-notes
```
This is what Render did for me automatically. Doing it by hand first shows what "deploying"
really means. Automating it (e.g. GitHub Actions) can come later.

### Backups
The notes live on one disk on one server, so backups are now my job.
- `deploy/backup.sh` runs every night from **cron** (Linux's task scheduler). It runs
  `sqlite3 smart_notes.db ".backup '...'"` into `/home/ubuntu/data/backups/` and keeps the last
  14 days.
- Every week or so I copy the newest backup to my Mac with `scp`, so a broken server can't take
  every copy with it.

### Keeping the server safe
- Log in with an **SSH key only** (Ubuntu on EC2 already turns password login off).
- Turn on **automatic security updates** (`unattended-upgrades`, on by default in Ubuntu).
- Never run the app as `root`. It runs as the `ubuntu` user.
- Turn on **MFA** (a second login step, e.g. a phone code) for the AWS root account, and don't
  use the root account day to day.

### Files kept in git
A new folder, `deploy/`, so the server setup is written down and reviewable:
- `deploy/smart-notes.service`: the systemd service (runs the gunicorn command from section 2).
- `deploy/Caddyfile`: the hostname, plus `reverse_proxy 127.0.0.1:8000`.
- `deploy/backup.sh`: the nightly backup.
- `deploy/README.md`: the setup commands from step 9, in order.

None of these contain secrets. Secrets stay in the server's `.env`.

---

## Steps (one commit each)
0. **Plan.** `PLAN-v1.md` (renamed) plus this `PLAN.md`. Add `.DS_Store` to `.gitignore`. ✅
1. **Settings from the environment.** `load_dotenv()` in `create_app()`, `SECRET_KEY`,
   `DATABASE_PATH`, `TRUSTED_HOSTS`, `ProxyFix`, cookie settings, and fail fast on missing
   secrets. ✅
2. **Login.** `/login`, `/logout`, the `before_request` check, `login.html`, Log out button,
   tests, `SPEC.md`. ✅
3. **Usage limit.** `ai_usage` table, `db.use_ai_job()`, size limits, messages and tests. ✅
4. **gunicorn.** Added to `requirements.txt`. ✅
5. **Plan for AWS.** Rewrite this file for option A on AWS (this change).
6. **AWS account (in the AWS console, no commit).** Sign up on the **Free plan**. Turn on MFA for
   the root account. Create the $5 budget alert. Choose region Frankfurt (`eu-central-1`).
7. **Settings not tied to Render.** Replace `RENDER` / `RENDER_EXTERNAL_HOSTNAME` with
   `BEHIND_PROXY` / `PUBLIC_HOSTNAME` in `app.py`, and update the error message and tests.
8. **Deploy files.** The `deploy/` folder from section 5.
9. **Launch the server (in the AWS console and over SSH, no commit).**
   - Anthropic Console: create a new key for the server and set a monthly spend limit.
   - EC2: launch a `t3.micro` with Ubuntu 24.04, a new SSH key pair (the `.pem` file stays on
     my Mac, `chmod 400`) and the security group from "The pieces". Attach an Elastic IP.
   - On the server: install `python3-venv`, `sqlite3` and Caddy. Add the deploy key, clone the
     repo, create `.venv`, `pip install -r requirements.txt`, and run `pytest` there.
   - Write the server's `.env` (section 1) and `chmod 600` it.
   - Back up `smart_notes.db` on my Mac, then `scp` it to `/home/ubuntu/data/`.
   - Install the systemd service, the Caddyfile and the cron backup. Start everything.
   - Follow the checks below.
10. **Review.** Run `/security-review` (or the `code-reviewer` agent) on the changes and fix
    anything serious.

## Verification
- `pytest -v` passes on my Mac and on the server, still with no real API calls.
- Local: `flask --app app run --debug` still works with `.env`.
- On `https://<elastic-ip-with-dashes>.sslip.io`:
  - The browser shows a valid HTTPS padlock, and `http://` redirects to `https://`.
  - A private browser window redirects to `/login`, and a wrong password is refused.
  - Log in, add a note, and the summary appears (the Origin check and HTTPS work).
  - My 10 old notes are there.
  - `sudo reboot` the server. Afterwards the app comes back by itself, I'm still logged in, and
    the notes are still there (systemd, the secret key and the disk work).
  - Temporarily set `AI_DAILY_LIMIT=0`. The note saves with the "limit reached" message.
  - Visit a URL that doesn't exist. It shows the normal 404 page, not a debug page.
  - Port 8000 is **not** reachable from my Mac (only Caddy is public).
  - The next morning, a backup file exists in `/home/ubuntu/data/backups/`.
- `git log -p` contains no secrets.
