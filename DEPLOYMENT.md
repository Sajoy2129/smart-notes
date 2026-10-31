# Deploying Smart Notes to AWS: a step-by-step guide

This guide walks through putting Smart Notes (a small Flask web app) on the internet, from an
empty AWS account to a working `https://` website. It is written for someone doing this for
the first time. Every command is explained, and each step ends with a check so you know it
worked before moving on.

`deploy/README.md` has the same steps in a shorter form, for someone who has done it before.

---

## Contents

0. [What you will end up with](#0-what-you-will-end-up-with)
1. [Before you start](#1-before-you-start)
2. [Get an API key for the server](#2-get-an-api-key-for-the-server)
3. [Launch the server on AWS](#3-launch-the-server-on-aws)
4. [Log in to the server](#4-log-in-to-the-server)
5. [Prepare the server](#5-prepare-the-server)
6. [Install Caddy](#6-install-caddy)
7. [Get the code (deploy key)](#7-get-the-code-deploy-key)
8. [Install the app and run the tests](#8-install-the-app-and-run-the-tests)
9. [Copy the database to the server](#9-copy-the-database-to-the-server)
10. [Create the server's `.env` file](#10-create-the-servers-env-file)
11. [Start the app with systemd](#11-start-the-app-with-systemd)
12. [Turn on HTTPS](#12-turn-on-https)
13. [Nightly backups with cron](#13-nightly-backups-with-cron)
14. [Final checks](#14-final-checks)
15. [After launch: updates, backups, troubleshooting](#15-after-launch)
16. [Optional: use PostgreSQL instead of SQLite](#16-optional-use-postgresql-instead-of-sqlite)

---

## 0. What you will end up with

```
Your browser ──HTTPS──▶ Caddy (ports 80 and 443, public)
                          └─▶ gunicorn (127.0.0.1:8000, private, kept running by systemd)
                                └─▶ Flask app ──▶ SQLite database file (~/data/smart_notes.db)
                                                    └─ cron makes a backup every night
```

| Part | What it is | Why it is needed |
|---|---|---|
| **EC2 instance** | A small Linux computer rented from AWS | Somewhere for the app to run 24/7 |
| **Elastic IP** | A fixed public address for that computer | So the address never changes |
| **Caddy** | A web server that sits in front of the app | Handles HTTPS (the padlock) by itself |
| **gunicorn** | A production server for Python web apps | Flask's own server is only for development |
| **systemd** | Linux's service manager | Starts the app at boot and restarts it if it crashes |
| **SQLite** | The database, a single file on disk | Stores the notes |
| **cron** | Linux's task scheduler | Runs the backup every night |
| **sslip.io** | A free name service: `3-120-45-67.sslip.io` points to `3.120.45.67` | HTTPS certificates need a name, not a bare IP |

**Cost:** a `t3.micro` server is covered by AWS's new-account credits for the first months,
then costs roughly $10–15 a month. Set a budget alert (step 3).

---

## 1. Before you start

**You need:**
- A Mac (or Linux) terminal. Windows works with PowerShell, but the commands below are for Mac.
- The Smart Notes code in a GitHub repository, with all tests passing locally (`pytest`).
- An AWS account, with **MFA** turned on (multi-factor authentication: a second login check
  through an app on your phone) and a **budget alert** (Billing → Budgets, e.g. $5).
- An Anthropic account (for the AI features).

**How to read the commands in this guide:**

| Prefix | Where to type it |
|---|---|
| `mac$` | In Terminal on your own computer |
| `server$` | On the server, after logging in with SSH (step 4) |

Copy only the part **after** the `$`.

**You can always tell where you are by looking at the prompt:**
- `yourname@Your-MacBook smart-notes %` means you are on your **Mac** (Mac prompts end in `%`).
- `ubuntu@ip-172-31-xx-xx:~$` means you are on the **server** (Linux prompts end in `$`).

**Placeholders:** replace these everywhere you see them:
- `ELASTIC-IP`: your server's fixed address, e.g. `3.120.45.67` (you get it in step 3)
- `HOSTNAME`: the same address with dashes instead of dots, plus `.sslip.io`, e.g.
  `3-120-45-67.sslip.io`
- `GITHUB-USER/REPO`: your GitHub repository, e.g. `alice/smart-notes`

**Tip:** keep two Terminal tabs open (Cmd+T opens a new one): one on your Mac and one logged
in to the server.

---

## 2. Get an API key for the server

1. Go to the Anthropic Console → **API Keys** → **Create key**. Name it `smart-notes-server`.
2. Copy it straight into a password manager. The Console shows it only once.
3. Under **Settings → Limits**, check the monthly spend limit.

**Why a separate key?** If the server is ever compromised, you can delete just this key
without breaking the copy of the app on your Mac.

---

## 3. Launch the server on AWS

All of this happens in the AWS web console.

1. Pick a **region** (top right), e.g. Stockholm (`eu-north-1`) or Frankfurt
   (`eu-central-1`). Choose one close to you, then keep using that same region.
2. Go to **EC2 → Launch instance** and fill in:
   - **Name:** `smart-notes`
   - **Image (AMI):** Ubuntu Server 24.04 LTS
   - **Instance type:** `t3.micro`
   - **Key pair:** *Create new key pair*. Name it `smart-notes`, type **ED25519**, format
     **.pem**. Your browser downloads `smart-notes.pem`. This file is the *only* way to log in,
     so keep it safe and never commit it to git.
   - **Network settings → Create security group** (a security group is AWS's firewall):
     - Allow **SSH** from **My IP** (not "Anywhere")
     - Allow **HTTPS** from the internet
     - Allow **HTTP** from the internet (Caddy needs it to get the certificate)
   - **Storage:** the default 8 GiB is enough.
3. Click **Launch instance**.
4. Go to **EC2 → Elastic IPs → Allocate Elastic IP address**. Then choose
   **Actions → Associate Elastic IP address** and pick the `smart-notes` instance.

**Why an Elastic IP?** Without it, the server gets a new public address every time it
stops and starts.

✅ **Check:** the instance shows **Running**, and the Elastic IP is shown on its details page.
Write the IP down; this is your `ELASTIC-IP`.

---

## 4. Log in to the server

```
mac$ mv ~/Downloads/smart-notes.pem ~/.ssh/
mac$ chmod 400 ~/.ssh/smart-notes.pem
mac$ ssh -i ~/.ssh/smart-notes.pem ubuntu@ELASTIC-IP
```

| Command | What it does |
|---|---|
| `mv ... ~/.ssh/` | Moves the key to the standard folder for SSH keys |
| `chmod 400` | Makes the key readable only by you. SSH refuses keys that other users can read. |
| `ssh -i KEY ubuntu@IP` | Opens a remote command line on the server. `-i` = "identity" (your key); `ubuntu` is the default user on Ubuntu servers. |

The first time, SSH asks `Are you sure you want to continue connecting?`. Type `yes`.

✅ **Check:** the prompt changes to `ubuntu@ip-...:~$`.

**Good to know:**
- SSH sessions close if they sit idle, or if your Mac sleeps. Just run the `ssh` command
  again. The app keeps running either way.
- If SSH says `Connection timed out`, your home IP address has probably changed. In AWS, edit
  the security group's SSH rule and set it to **My IP** again.

---

## 5. Prepare the server

```
server$ sudo apt update && sudo apt upgrade -y
server$ sudo apt install -y python3-venv sqlite3 git
server$ sudo timedatectl set-timezone Asia/Dubai
server$ sudo reboot
```

| Command | What it does |
|---|---|
| `sudo` | Runs a command as the administrator ("superuser do") |
| `apt update` / `apt upgrade -y` | Refreshes the list of available software, then installs all updates (`-y` = answer yes) |
| `apt install -y python3-venv sqlite3 git` | Installs virtual-environment support for Python, the SQLite tool and git |
| `timedatectl set-timezone ...` | Sets the server's clock to **your** timezone. Change `Asia/Dubai` to yours (list them with `timedatectl list-timezones`). |
| `sudo reboot` | Restarts the server so updates to the core system take effect. SSH disconnects; wait a minute and log in again. |

**Why the timezone matters:** the app stamps notes with the server's local time and resets the
daily AI limit at local midnight. A new server runs on UTC.

✅ **Check:** after logging back in, `date` shows your local time.

---

## 6. Install Caddy

Ubuntu's own software list does not have a current Caddy, so first tell `apt` about Caddy's
official source, then install from it. Run these one at a time:

```
server$ sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
server$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
server$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
server$ sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
server$ sudo apt update && sudo apt install -y caddy
```

| Line | What it does |
|---|---|
| 1 | Installs tools that let `apt` download from outside sources over HTTPS |
| 2 | Downloads Caddy's **signing key**, which `apt` uses to check that packages really come from Caddy |
| 3 | Adds Caddy's package source to `apt`'s list |
| 4 | Makes both files readable (`o+r` = "others may read") so `apt` can use them |
| 5 | Installs Caddy. `&&` means "run the second command only if the first one worked". |

(These commands come from [Caddy's install guide](https://caddyserver.com/docs/install#debian-ubuntu-raspbian).)

✅ **Check:**
```
server$ caddy version
server$ systemctl status caddy --no-pager
```
You should see a version like `v2.x.x` and **`active (running)`**.

**Tip:** without `--no-pager`, `systemctl status` opens a scrolling viewer. Press `q` to leave it.

---

## 7. Get the code (deploy key)

The repository is private, so the server needs permission to download it. A **deploy key**
is an SSH key that gives access to **one** repository only, and we make it **read-only**. Then,
even if someone broke into the server, they could not change your code on GitHub.

An SSH key comes in two halves: the **private key** stays secret on the server, and the
**public key** (`.pub`) is safe to share. You give the public half to GitHub.

**7a. Make the key (server):**
```
server$ ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "smart-notes server"
server$ cat ~/.ssh/github_deploy.pub
```
- `-t ed25519`: a modern key type. `-f`: where to save it. `-N ""`: no passphrase, so the
  server can use it unattended. `-C`: a label.
- `cat` prints the public key: one line starting `ssh-ed25519`. Copy the whole line.

**7b. Add it to GitHub (browser):** open the repository → **Settings → Deploy keys → Add deploy
key**. Title: `smart-notes server`. Paste the line. Leave **Allow write access unticked**.
Click **Add key**.

**7c. Clone the repository (server):**
```
server$ printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
server$ git clone git@github.com:GITHUB-USER/REPO.git ~/smart-notes
```
- The `printf` line tells SSH to use the deploy key for github.com. `>>` adds to the end of the
  file (and creates it if it doesn't exist).
- The first time, SSH shows GitHub's **fingerprint** and asks whether to trust it. Compare it
  with the `ED25519` value on
  [GitHub's SSH fingerprints page](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints).
  If it matches, type `yes`. This proves you are talking to the real GitHub.

✅ **Check:**
```
server$ cd ~/smart-notes && git log --oneline -1
```
It shows the same latest commit as on your Mac. If it shows an older one, you forgot to push
from your Mac: run `git push` there, then `git pull` here.

❌ `Permission denied (publickey)` means the deploy key is missing on GitHub, or was saved
wrongly. Repeat step 7b.

---

## 8. Install the app and run the tests

```
server$ cd ~/smart-notes
server$ python3 -m venv .venv
server$ .venv/bin/pip install -r requirements.txt
server$ .venv/bin/pytest -q
```

| Command | What it does |
|---|---|
| `python3 -m venv .venv` | Creates a **virtual environment**: a private folder of Python packages just for this app, separate from the system's |
| `.venv/bin/pip install -r requirements.txt` | Installs the packages the app needs (Flask, gunicorn, the Anthropic SDK...) into it |
| `.venv/bin/pytest -q` | Runs all the tests on the server |

**Why run the tests here too?** The server is a different computer, with a different Python
version and different system libraries. Passing tests prove the app works *on this machine*.
(The tests use a fake AI client, so they cost nothing.)

✅ **Check:** the last line says `N passed` with **no failures**. Don't continue until it does.

---

## 9. Copy the database to the server

The notes live in `smart_notes.db`. Database files are deliberately not in git, so the clone
did not bring them.

**9a. Make a safe snapshot (Mac, in the project folder):**
```
mac$ sqlite3 smart_notes.db ".backup 'backups/smart_notes-$(date +%F).db'"
mac$ sqlite3 backups/smart_notes-$(date +%F).db "PRAGMA integrity_check; SELECT count(*) FROM notes;"
```
`.backup` makes a consistent copy even if the app is running. `$(date +%F)` inserts today's
date, e.g. `2026-10-31`. The second line should print `ok` and the number of notes.

**9b. Make a folder for the data (server):**
```
server$ mkdir -p ~/data/backups
```
The database goes in `~/data`, **outside** the code folder, so a `git pull` can never touch it.

**9c. Copy the snapshot up (Mac):**
```
mac$ scp -i ~/.ssh/smart-notes.pem backups/smart_notes-YYYY-MM-DD.db ubuntu@ELASTIC-IP:/home/ubuntu/data/smart_notes.db
```
**`scp`** ("secure copy") copies a file over SSH: `scp FROM TO`. We copy the **snapshot**, not
the live database, so the copy can't be caught half-written.

✅ **Check (server):**
```
server$ sqlite3 ~/data/smart_notes.db "SELECT count(*) FROM notes;"
```
It prints the same number as on the Mac.

⚠️ **From now on, the server's database is the real one.** Notes added to the Mac's copy will
not appear on the website.

---

## 10. Create the server's `.env` file

`.env` holds the app's secret settings. It is **never** committed to git, so you create it by
hand. 🔒 Never paste its contents into a chat, an email or a screenshot.

**10a. Make a new secret key (server)**, and copy the output *before* opening the editor:
```
server$ python3 -c "import secrets; print(secrets.token_hex(32))"
```
Flask uses this to sign login cookies. The server gets its **own** key, different from your
Mac's.

**10b. Get the password hash.** If you already have one in your Mac's `.env`, show it in a
plain Terminal tab: `grep APP_PASSWORD_HASH .env`. If not, make one (it asks for the password
without showing it):
```
mac$ .venv/bin/python -c "import getpass; from werkzeug.security import generate_password_hash as h; print(h(getpass.getpass()))"
```
A **hash** is a scrambled, one-way version of the password. The app can check a password
against it, but nobody can turn the hash back into the password.

**10c. Write the file (server):**
```
server$ nano ~/smart-notes/.env
```
**nano** is a simple text editor that runs in the terminal. Paste in the lines below, then
replace each `...` with your real value:
```
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=...
APP_PASSWORD_HASH='scrypt:...'
DATABASE_PATH=/home/ubuntu/data/smart_notes.db
AI_DAILY_LIMIT=50
BEHIND_PROXY=true
PUBLIC_HOSTNAME=HOSTNAME
```

| Setting | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | The server's key from step 2 |
| `SECRET_KEY` | The value from 10a |
| `APP_PASSWORD_HASH` | From 10b. **Keep the single quotes**: the hash contains `$` signs. |
| `DATABASE_PATH` | Where the database file is (step 9) |
| `AI_DAILY_LIMIT` | The most AI calls per day, to cap costs |
| `BEHIND_PROXY` | Tells the app that Caddy is in front, so it trusts Caddy's "this was HTTPS" header |
| `PUBLIC_HOSTNAME` | The site's name; the app refuses requests for other names |

**nano keys:** arrow keys to move (the mouse doesn't work), Cmd+V to paste,
**Ctrl+O then Enter** to save, **Ctrl+X** to exit. `^O` on nano's menu means Ctrl+O.

**10d. Lock it down:**
```
server$ chmod 600 ~/smart-notes/.env
```
`600` = only your user can read and write it.

✅ **Check** (this is safe to share, because it shows only the names, not the values):
```
server$ ls -l ~/smart-notes/.env && cut -d= -f1 ~/smart-notes/.env
```
- The line starts with `-rw-------` (that's a lowercase **L** in `ls -l`, not the number 1).
- It lists the 7 names, **spelled exactly right**. Pasting into nano sometimes drops the first
  letter, e.g. `NTHROPIC_API_KEY`.

---

## 11. Start the app with systemd

The file `deploy/smart-notes.service` is a short recipe that tells systemd how to run the app:
as the `ubuntu` user (never as root), with gunicorn listening on `127.0.0.1:8000` (reachable
only from inside the server), restarting it if it crashes, and starting it at boot.

```
server$ sudo cp ~/smart-notes/deploy/smart-notes.service /etc/systemd/system/
server$ sudo systemctl daemon-reload
server$ sudo systemctl enable --now smart-notes
```

| Command | What it does |
|---|---|
| `cp ... /etc/systemd/system/` | Puts the recipe where systemd looks for services |
| `daemon-reload` | Makes systemd re-read its files ("daemon" = a background program) |
| `enable --now` | `enable`: start at every boot. `--now`: also start it right away. |

✅ **Check:**
```
server$ systemctl status smart-notes --no-pager
server$ curl -I http://127.0.0.1:8000/login
```
- `status` shows **`active (running)`**.
- `curl -I` asks for just the page's headers and should print **`HTTP/1.1 200 OK`**.

❌ If not, read the app's log. The real error is usually a Python traceback near the bottom:
```
server$ journalctl -u smart-notes -n 50 --no-pager
```

---

## 12. Turn on HTTPS

Give Caddy the app's config, with your hostname filled in:
```
server$ sed 's/YOUR-HOSTNAME/HOSTNAME/' ~/smart-notes/deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile
server$ sudo systemctl reload caddy
```
- `sed 's/old/new/'` replaces the placeholder in `deploy/Caddyfile` with your hostname.
  `sudo tee` writes the result to Caddy's config file and also prints it, so check that the
  first real line is `HOSTNAME {`.
- `reload` makes Caddy read the new config without stopping. Caddy then gets a free HTTPS
  certificate from **Let's Encrypt** and renews it automatically from then on.

✅ **Check:** open `https://HOSTNAME` in your browser. The first visit can take up to a minute.
You should see the login page, and a **padlock** to the left of the address (Chrome shows a
"tune" icon with two sliders instead; it means the same thing). Click it, and it should say
**"Connection is secure"**.

❌ If it doesn't load, check that the security group allows HTTP and HTTPS (step 3), then read
`journalctl -u caddy -n 50 --no-pager`.

---

## 13. Nightly backups with cron

`deploy/backup.sh` copies the database to `~/data/backups/smart_notes-YYYY-MM-DD.db` and
deletes backups older than 14 days.

**13a. Test it by hand first.** cron fails silently, so make sure the script works:
```
server$ ~/smart-notes/deploy/backup.sh && ls -l ~/data/backups/
```
You should see a file with today's date.

**13b. Schedule it:**
```
server$ crontab -e
```
If asked to pick an editor, choose **nano** (usually `1`). Go to the **very bottom** of the
file and add this line on a new line of its own:
```
30 3 * * * /home/ubuntu/smart-notes/deploy/backup.sh
```
Save and exit (Ctrl+O, Enter, Ctrl+X).

**How to read it:** the five fields are `minute hour day-of-month month day-of-week`, and `*`
means "every". So this runs at **03:30 every night**, server time (which is why step 5 set the
timezone).

⚠️ The file is full of example lines that start with `#`. A `#` turns a line into a **comment**,
which cron ignores. Make sure **your** line does not start with `#`.

✅ **Check:**
```
server$ crontab -l | grep -v '^#'
```
This shows only the lines that are **not** comments (`grep -v` = "lines that don't match";
`^#` = "starts with #"). You should see exactly your backup line. If nothing prints, the line
is still commented out.

The next morning, `ls -l ~/data/backups/` shows a new file.

---

## 14. Final checks

**From the Mac:**
```
mac$ curl -sI http://HOSTNAME/ | grep -iE "^HTTP|^location"
mac$ curl -sI https://HOSTNAME/ | grep -iE "^HTTP|^location"
mac$ curl -sI https://HOSTNAME/no-such-page | head -1
mac$ curl -s -m 5 http://ELASTIC-IP:8000/login || echo "blocked (good)"
mac$ git log -p | grep -cE "sk-ant-[A-Za-z0-9_-]{10,}|SECRET_KEY=[0-9a-f]{32,}"
```

| Check | Expected result | What it proves |
|---|---|---|
| `http://` | `308` redirect to `https://` | Visitors are always switched to the secure site |
| `https://` while logged out | `302` to `/login` | Pages are locked without the password |
| A page that doesn't exist | `404` | A plain error page, no debug information leaked |
| Port 8000 | `blocked (good)` | Only Caddy is public; the app itself is hidden |
| Secrets in git history | `0` | No keys were ever committed |

**In the browser:**
- [ ] A private (Incognito) window lands on the login page, and a wrong password is refused.
- [ ] After logging in, all the old notes are there.
- [ ] Adding a note produces an AI summary.

**Reboot test (the most important):**
```
server$ sudo reboot
```
Wait a minute, then refresh the site. It should come back by itself, you should still be logged
in, and the notes should still be there. This proves systemd, the secret key and the disk
all work.

**Next morning:** `ls -l ~/data/backups/` shows the first automatic backup.

🎉 **The app is live.**

---

## 15. After launch

### Updating the app
1. On your Mac: change the code, run `pytest`, commit, then `git push`.
2. On the server:
   ```
   server$ cd ~/smart-notes && git pull
   server$ .venv/bin/pip install -r requirements.txt   # only needed if requirements.txt changed
   server$ .venv/bin/pytest -q
   server$ sudo systemctl restart smart-notes
   ```
   The restart is needed because the running app loaded the old code when it started.
3. If `deploy/smart-notes.service` or `deploy/Caddyfile` changed, repeat step 11 or 12.

### Copying the backups to your Mac
```
mac$ scp -i ~/.ssh/smart-notes.pem 'ubuntu@ELASTIC-IP:/home/ubuntu/data/backups/*' backups/
```
Backups that exist only on the server are lost if the server is. Copy them down now and then.

### Useful commands (on the server)
| Command | What it does |
|---|---|
| `systemctl status smart-notes --no-pager` | Is the app running? |
| `journalctl -u smart-notes -f` | Follow the app's log live (Ctrl+C to stop) |
| `sudo systemctl restart smart-notes` | Restart the app |
| `journalctl -u caddy -n 50 --no-pager` | Caddy's last 50 log lines (HTTPS problems) |
| `df -h /` | How full is the disk? |
| `crontab -l` | Show the scheduled jobs |

### Troubleshooting
| Symptom | Likely cause | Fix |
|---|---|---|
| `ssh: Connection timed out` | Your home IP address changed | Set the security group's SSH rule to **My IP** again |
| `Permission denied (publickey)` when cloning | Deploy key not on GitHub | Repeat step 7b |
| A screen ending in `(END)` or `:` that won't respond | You are in a pager | Press `q` (or add `--no-pager`) |
| Can't see output that was on screen before opening nano | nano covers the whole screen | Exit with Ctrl+X, copy what you need, reopen |
| App not `active (running)` | Usually a `.env` problem | `journalctl -u smart-notes -n 50 --no-pager` |
| AI features fail | API key name misspelled or wrong | Check the names with `cut -d= -f1 .env` |
| `curl -I` returns 401 on `/login` | An old version of the app that didn't handle HEAD requests | `git pull` and restart |
| No backups appear | The cron line starts with `#` | `crontab -l \| grep -v '^#'` |
| Site down after editing the Caddyfile | A typo in the config | `journalctl -u caddy -n 50 --no-pager` |

### Costs
- The AWS credits on a new account run out after some months. After that, the server costs
  roughly $10–15 a month. The budget alert emails you before any real charges.
- AI usage is capped by `AI_DAILY_LIMIT`, plus the spend limit in the Anthropic Console.

---

## 16. Optional: use PostgreSQL instead of SQLite

Everything above uses **SQLite**: the notes live in one file, `~/data/smart_notes.db`. The app
can also use **PostgreSQL**, a database server (for example AWS RDS, or Neon). Which one it uses
depends on a single setting in `.env`:

| `.env` has | The app uses |
|---|---|
| no `DATABASE_URL` line (or `DATABASE_URL=` with nothing after it) | SQLite, at `DATABASE_PATH` |
| `DATABASE_URL=postgresql://...` | PostgreSQL. `DATABASE_PATH` is then ignored |

The live server has no `DATABASE_URL`, so it uses SQLite. **Nothing changes until you add one.**

### 16a. What a `DATABASE_URL` looks like
```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```
| Part | Meaning | Example |
|---|---|---|
| `USER`, `PASSWORD` | The database login (not your app password) | `notes`, `4f9c2a7e1b...` |
| `HOST` | The database server's address | `localhost`, or the address RDS/Neon shows you |
| `5432` | The port. 5432 is PostgreSQL's usual one | `5432` |
| `DATABASE` | The database's name on that server | `smart_notes` |
| `?sslmode=require` | Encrypt the connection, or refuse to connect | Always add it when the database is on another machine |

- **Why `sslmode=require`:** without it, the connection *tries* encryption but quietly continues
  unencrypted if the server doesn't offer it. Then your password and notes cross the internet as
  plain text that anyone along the way could read. `require` refuses to connect unencrypted.
  Neon's ready-made URLs already end with it. For RDS, add it yourself. (`verify-full` is
  stricter still: it also checks the server's certificate, but needs the RDS certificate file
  downloaded to the server.) For `localhost`, as in the tests, leave it out.

- The URL contains a password, so it belongs in `.env` (never in git), and `.env` stays
  `chmod 600` (step 10). To check the names in `.env` without showing the values, use
  `cut -d= -f1 .env`.
- **Use a password made only of letters and digits.** Some characters have a special meaning
  inside a URL, and an unencoded one breaks it. PostgreSQL's error can then show part of the
  password. Make a safe one with `python3 -c "import secrets; print(secrets.token_hex(24))"`.
  If you must keep a password with special characters, encode each one:

  | Character | `%` | `@` | `:` | `/` | `#` | `?` | space |
  |---|---|---|---|---|---|---|---|
  | Write it as | `%25` | `%40` | `%3A` | `%2F` | `%23` | `%3F` | `%20` |

### 16b. Switch the server to PostgreSQL
1. Make sure the PostgreSQL database exists and is empty. The app creates its tables itself when
   it starts.
2. Add the `DATABASE_URL` line to `~/smart-notes/.env` (`nano ~/smart-notes/.env`).
3. Install the PostgreSQL driver (it's in `requirements.txt`) and restart:
   ```
   server$ cd ~/smart-notes && .venv/bin/pip install -r requirements.txt
   server$ sudo systemctl restart smart-notes
   server$ systemctl status smart-notes --no-pager
   ```
**Check:** the status says `active (running)`. Log in to the site. The project list is **empty**:

> **Switching does not copy your notes.** The new PostgreSQL database starts empty. The SQLite
> file stays exactly where it was. Copying the notes across needs a migration script, which
> doesn't exist yet.

**Switching back:** delete the `DATABASE_URL` line (or put `#` in front of it) and restart. The
app uses the SQLite file again, as it was before the switch. Notes written while on PostgreSQL
stay in PostgreSQL.

### 16c. Backups on PostgreSQL
`deploy/backup.sh` (step 13) only backs up the **SQLite file**. On PostgreSQL it keeps
copying the old file, which no longer changes. Before relying on PostgreSQL:
- Managed services (RDS, Neon) have their own automatic backups. Check that they are on.
- Or make your own copy with `pg_dump`, PostgreSQL's backup command. It writes the whole database as
  SQL you can load again later. A `pg_dump` version of `backup.sh` is still to be written.

### 16d. Testing on PostgreSQL (on your Mac)
The normal `pytest` always uses SQLite. To run the same tests on PostgreSQL:
```
mac$ brew install postgresql@17                                   # once
mac$ brew services run postgresql@17                              # after each restart of the Mac
mac$ /opt/homebrew/opt/postgresql@17/bin/createdb smart_notes_test  # once
mac$ TEST_DATABASE_URL=postgresql://localhost/smart_notes_test pytest
```
**Check:** the first line of the output says `database: PostgreSQL (smart_notes_test)`, and all
tests pass. The tests delete every table before each test, so they refuse any database whose name
doesn't contain `test`. Your real data can't be wiped by mistake.

### 16e. Troubleshooting PostgreSQL
If the app can't reach PostgreSQL, the log (`journalctl -u smart-notes -n 50 --no-pager`)
says `Could not connect to PostgreSQL` and **hides the details**, because PostgreSQL's own
message can contain the password. To see the details on your screen only (not in the log),
connect by hand with the same URL:
```
server$ sudo apt install -y postgresql-client                # once: the psql command
server$ psql "$(grep '^DATABASE_URL=' ~/smart-notes/.env | cut -d= -f2-)" -c "SELECT 1"
```
| `psql` says | Likely cause | Fix |
|---|---|---|
| `connection refused` or `timeout` | PostgreSQL isn't running, or wrong `HOST`/port | Check the URL's host. For RDS, the security group must let the server in on port 5432 |
| `password authentication failed` | Wrong `USER` or `PASSWORD` in the URL | Check them. Encode special characters (16a) |
| `invalid percent-encoded token` or `failed to resolve host` | A special character in the password isn't encoded | Encode it (16a), or use a letters-and-digits password |
| `database "..." does not exist` | The database wasn't created yet | Create it (`createdb NAME`, or in the RDS/Neon console) |

If the log says `No module named 'psycopg'` instead, the driver isn't installed:
`.venv/bin/pip install -r requirements.txt`.
