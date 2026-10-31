# Setting up the Smart Notes server (step 9)

Do these in order. Lines that start with `mac$` run on my Mac. Lines with `server$` run on the
EC2 server, over SSH. Copy only the part after the `$`.

In the commands below, replace:
- `ELASTIC-IP`: the server's fixed address, e.g. `3.120.45.67`
- `HOSTNAME`: the same address with dashes plus `.sslip.io`, e.g. `3-120-45-67.sslip.io`

---

## 1. Anthropic Console
1. Create a **new API key** just for the server, named `smart-notes-server`.
2. Under *Settings → Limits*, check the monthly spend limit.

## 2. Launch the server (AWS console, region Stockholm `eu-north-1`)
1. **EC2 → Launch instance**
   - Name: `smart-notes`
   - Image: **Ubuntu Server 24.04 LTS**
   - Instance type: **t3.micro**
   - Key pair: **Create new key pair**, named `smart-notes`, type ED25519, format `.pem`. The
     browser downloads `smart-notes.pem`. This is the only key that can log in, so keep it safe.
   - Network settings → **Create security group**:
     - Allow SSH traffic from **My IP** (not "Anywhere")
     - Allow HTTPS traffic from the internet
     - Allow HTTP traffic from the internet (Caddy needs it to get the certificate)
   - Storage: the default 8 GiB gp3 is enough.
2. **EC2 → Elastic IPs → Allocate Elastic IP address**, then **Actions → Associate** it with
   the `smart-notes` instance.

## 3. Log in
```
mac$ mv ~/Downloads/smart-notes.pem ~/.ssh/
mac$ chmod 400 ~/.ssh/smart-notes.pem
mac$ ssh -i ~/.ssh/smart-notes.pem ubuntu@ELASTIC-IP
```
`chmod 400` makes the key readable only by me. SSH refuses keys that others can read.
The first time, SSH asks whether to trust the server. Type `yes`.

If SSH stops working later, my home IP address has probably changed. Update the security
group's SSH rule to **My IP** again.

## 4. Prepare the server
```
server$ sudo apt update && sudo apt upgrade -y
server$ sudo apt install -y python3-venv sqlite3 git
server$ sudo timedatectl set-timezone Asia/Dubai
```
The timezone matters: the app stamps notes and resets the daily AI limit using the server's
clock, which starts on UTC.

Install Caddy, following [Caddy's install guide](https://caddyserver.com/docs/install#debian-ubuntu-raspbian):
```
server$ sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
server$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
server$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
server$ sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
server$ sudo apt update && sudo apt install -y caddy
```

## 5. Get the code (read-only deploy key)
```
server$ ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "smart-notes server"
server$ cat ~/.ssh/github_deploy.pub
```
On GitHub: repo **Settings → Deploy keys → Add deploy key**. Title `smart-notes server`, paste
the line that `cat` printed, and leave **Allow write access** off.

```
server$ printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
server$ git clone git@github.com:Sajoy2129/smart-notes.git ~/smart-notes
```
When asked to trust github.com, check that the fingerprint matches one on
[GitHub's SSH fingerprints page](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints),
then type `yes`.

## 6. Install the app and run the tests
```
server$ cd ~/smart-notes
server$ python3 -m venv .venv
server$ .venv/bin/pip install -r requirements.txt
server$ .venv/bin/pytest -q
```
All tests must pass before going further.

## 7. Copy my notes to the server
Back up first, then copy. Run these on the Mac, in the project folder:
```
mac$ sqlite3 smart_notes.db ".backup 'backups/smart_notes-$(date +%F).db'"
server$ mkdir -p ~/data/backups
mac$ scp -i ~/.ssh/smart-notes.pem smart_notes.db ubuntu@ELASTIC-IP:/home/ubuntu/data/smart_notes.db
```
`scp` copies a file over SSH. From now on, the server's copy is the real one.

## 8. The server's `.env`
Make a new secret key:
```
server$ python3 -c "import secrets; print(secrets.token_hex(32))"
```
Then create the file:
```
server$ nano ~/smart-notes/.env
```
```
# The new key from part 1
ANTHROPIC_API_KEY=sk-ant-...
# The value printed above
SECRET_KEY=...
# Same as on my Mac, in single quotes
APP_PASSWORD_HASH='scrypt:...'
DATABASE_PATH=/home/ubuntu/data/smart_notes.db
AI_DAILY_LIMIT=50
BEHIND_PROXY=true
PUBLIC_HOSTNAME=HOSTNAME
```
Save with Ctrl+O then Enter, and leave with Ctrl+X. Then make it readable only by me:
```
server$ chmod 600 ~/smart-notes/.env
```

## 9. Start the app (systemd)
```
server$ sudo cp ~/smart-notes/deploy/smart-notes.service /etc/systemd/system/
server$ sudo systemctl daemon-reload
server$ sudo systemctl enable --now smart-notes
server$ systemctl status smart-notes
server$ curl -I http://127.0.0.1:8000/login
```
`status` should say **active (running)**, and `curl` should print `HTTP/1.1 200 OK`. If not,
read the error with `journalctl -u smart-notes -n 50`.

## 10. Turn on HTTPS (Caddy)
```
server$ sed 's/YOUR-HOSTNAME/HOSTNAME/' ~/smart-notes/deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile
server$ sudo systemctl reload caddy
```
Open `https://HOSTNAME` in the browser. Getting the first certificate can take up to a
minute. If it fails, read `journalctl -u caddy -n 50`.

## 11. Nightly backups (cron)
```
server$ crontab -e
```
Choose `nano` if asked, and add this line at the end:
```
30 3 * * * /home/ubuntu/smart-notes/deploy/backup.sh
```
This runs the backup every day at 03:30, Dubai time. The five fields are minute, hour,
day of month, month and day of week, and `*` means "every".

## 12. Check everything
Follow the **Verification** list at the end of `PLAN.md`.

---

## Later: updating the app
After pushing new code to GitHub:
```
mac$ ssh -i ~/.ssh/smart-notes.pem ubuntu@ELASTIC-IP
server$ cd ~/smart-notes && git pull
server$ .venv/bin/pip install -r requirements.txt
server$ .venv/bin/pytest -q
server$ sudo systemctl restart smart-notes
```
If `deploy/smart-notes.service` or `deploy/Caddyfile` changed, copy them again (parts 9 and 10).

## Later: copy a backup to my Mac
```
mac$ scp -i ~/.ssh/smart-notes.pem 'ubuntu@ELASTIC-IP:/home/ubuntu/data/backups/*' backups/
```

## Useful commands
| Command | What it does |
|---|---|
| `systemctl status smart-notes` | Is the app running? |
| `journalctl -u smart-notes -f` | Follow the app's log live (Ctrl+C to stop) |
| `sudo systemctl restart smart-notes` | Restart the app |
| `journalctl -u caddy -n 50` | Caddy's last 50 log lines (HTTPS problems) |
| `df -h /` | How full is the disk? |
