# ASI Track Manager — Deployment Guide

This guide walks you through deploying the ASI Track Manager Django application on an internal Windows VM running **Ubuntu via WSL2**. The stack is:

- **Django 5.2.11** (Python 3.12) served by **Gunicorn**
- **Caddy** as a reverse proxy with automatic self-signed HTTPS (no cert management required)
- **SQLite** database stored in a persistent Docker volume
- **Docker Compose** to orchestrate everything
- **cron** for automated backups and optional auto-updates
- All services run inside **Ubuntu (WSL2)** on the Windows VM

Target audience: a developer comfortable with the command line but not necessarily experienced with Docker or production deployments.

---

## Prerequisites

### VM Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| OS | Windows 10 22H2 | Windows 11 22H2+ |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB free | 40 GB free |
| CPU | 2 cores | 4 cores |

The app is lightweight — 1–15 concurrent users will barely stress these specs.

### 1. Enable WSL2 and Install Ubuntu

Open PowerShell **as Administrator** on the VM:

```powershell
wsl --install
```

This installs WSL2 and Ubuntu in one step. Reboot when prompted. After rebooting, Ubuntu will finish setup and ask you to create a Linux username and password.

> If WSL is already installed but you need Ubuntu specifically:
> ```powershell
> wsl --install -d Ubuntu
> ```

Verify the install:
```powershell
wsl --list --verbose
```
You should see `Ubuntu` with `VERSION 2`.

### 2. Enable systemd in Ubuntu

Systemd lets Docker and other services start automatically when WSL launches. Open an Ubuntu terminal and run:

```bash
sudo tee /etc/wsl.conf > /dev/null <<'EOF'
[boot]
systemd=true
EOF
```

Then restart WSL from PowerShell:
```powershell
wsl --shutdown
wsl -d Ubuntu
```

### 3. Install Docker Engine in Ubuntu

Run these commands inside the Ubuntu terminal (copy the whole block):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Add your user to the `docker` group so you don't need `sudo` for every docker command:
```bash
sudo usermod -aG docker $USER
```

Then close and reopen your Ubuntu terminal (the group change takes effect on new login).

Enable Docker to start automatically:
```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Verify:
```bash
docker --version
docker compose version
```
You should see Docker 24+ and Compose v2+.

### 4. Install Git

```bash
sudo apt-get install -y git
git --version
```

### Internal DNS Setup

Ask your IT team to create an A record:
```
schedule.asi.com → <VM's static IP address>
```

To find the VM's IP address from the Ubuntu terminal:
```bash
ip addr show eth0
# Look for the inet line (e.g., 192.168.1.50)
```

Or from Windows PowerShell:
```powershell
ipconfig
# Look for the IPv4 Address of your primary network adapter
```

---

## WSL2 Auto-Start and Network Access

This section handles two WSL-specific concerns that don't apply to a plain Linux server.

### Auto-Start WSL on Windows Boot

WSL2 doesn't start automatically when Windows boots. You need a Windows Task Scheduler task to launch it.

Open **Task Scheduler** on the VM (search "Task Scheduler" in Start Menu):

1. Click **Create Task** (not Basic Task — we need more control)
2. **General tab:**
   - Name: `WSL2 — Auto Start`
   - Check **"Run whether user is logged on or not"**
   - Check **"Run with highest privileges"**
3. **Triggers tab:** Click New → Begin the task: **At startup**
4. **Actions tab:** Click New
   - Program: `wsl.exe`
   - Arguments: `-d Ubuntu`
5. **Settings tab:** Check **"Allow task to be run on demand"**
6. Click OK and enter the Windows account password when prompted

This starts the Ubuntu WSL2 instance on boot, which triggers systemd, which starts Docker, which restarts your containers (since they're configured with `restart: unless-stopped`).

**Test it:** Reboot the VM, wait 60 seconds, then open a browser and check `https://localhost`.

### Make the App Reachable from Other Machines on the Network

Enable mirrored networking so WSL2 shares the Windows host's network interfaces. Docker ports (80, 443) will appear directly on the VM's LAN IP with no extra configuration.

From PowerShell (or open `%USERPROFILE%\.wslconfig` in Notepad):
```powershell
Add-Content "$env:USERPROFILE\.wslconfig" "[wsl2]`nnetworkingMode=mirrored"
```

Then restart WSL:
```powershell
wsl --shutdown
```

Open Windows Firewall for the app's ports (run PowerShell as Administrator):
```powershell
New-NetFirewallRule -DisplayName "ASI Track Manager HTTP"  -Direction Inbound -Protocol TCP -LocalPort 80  -Action Allow
New-NetFirewallRule -DisplayName "ASI Track Manager HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

---

## 1. Project Setup on the VM

Open an Ubuntu (WSL2) terminal and create the app directory:

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/wksaurey/asi-track-manager.git
cd asi-track-manager
```

### Create the Production `.env` File

The `.env` file holds secrets and environment-specific config. It must **never** be committed to git (it's already in `.gitignore`).

Generate a new secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Now create the file (replace the placeholder with your generated key):
```bash
cat > .env <<'EOF'
SECRET_KEY=<paste-your-generated-key-here>
DEBUG=False
ALLOWED_HOSTS=schedule.asi.com,localhost
CSRF_TRUSTED_ORIGINS=https://schedule.asi.com,https://localhost
DB_PATH=/app/db/db.sqlite3
EOF
```

Double-check it looks right:
```bash
cat .env
```

> **Why these variables?**
> - `SECRET_KEY` signs cookies and tokens — must be secret and unique per deployment.
> - `DEBUG=False` disables the interactive error page (which leaks code internals).
> - `ALLOWED_HOSTS` prevents HTTP Host header attacks.
> - `CSRF_TRUSTED_ORIGINS` is required by Django 4+ when behind a reverse proxy with HTTPS.
> - `DB_PATH` places the database inside the Docker volume so it survives container rebuilds.

---

## 2. Dockerfile

The `Dockerfile` is included in the `deployment/` folder. Copy it to the project root before building:

```bash
cp deployment/Dockerfile .
```

> **Why Gunicorn?** Django's built-in `runserver` is single-threaded and not safe for production. Gunicorn runs multiple worker processes so concurrent requests don't queue behind each other.

> **Why WhiteNoise?** It lets Django serve its own static files efficiently without needing a separate file server config. This keeps the setup simple — Caddy will handle the routing.

---

## 3. Docker Compose with Caddy for HTTPS

Copy the deployment files to the project root:

```bash
cp deployment/docker-compose.yml .
cp deployment/Caddyfile .
```

> **Why Caddy instead of nginx?** For an internal deployment with a self-signed cert, Caddy's `tls internal` directive handles certificate generation and renewal automatically — no openssl commands, no certbot, no manual cert rotation. It's significantly simpler.

> **Why volumes?** The `db-data` volume keeps your SQLite database alive across container rebuilds. `static-files` is shared between the `web` container (which writes files during `collectstatic`) and `caddy` (which serves them directly, bypassing Django entirely).

> **What `tls internal` does:** Caddy generates a local CA and issues a certificate signed by it. Users will see a browser warning the first time they visit — they click "Advanced → Proceed" once and the warning goes away for that browser. For an internal tool this is perfectly acceptable.

---

## 4. Django Production Settings

Open `asi_track_manager/settings.py` and make the following changes:

**Add `import os` at the top** (after the existing `from pathlib import Path`):

```python
from pathlib import Path
import os
```

**Replace the hardcoded SECRET_KEY, DEBUG, and ALLOWED_HOSTS block:**

```python
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-local-dev-key-replace-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
```

**Add WhiteNoise middleware** — it must come directly after `SecurityMiddleware`:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # <-- add this line
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

**Update the database path** so it points to the Docker volume instead of the project root:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DB_PATH', BASE_DIR / 'db.sqlite3'),
    }
}
```

**Replace the existing `STATIC_URL` line and add the full static file and HTTPS block** (the existing file has `STATIC_URL = 'static/'` — replace that line and everything after it in the static files comment block):

```python
# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Whitenoise — serve compressed static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# HTTPS / proxy settings — required when running behind Caddy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF trusted origins — required when Django is behind a reverse proxy
CSRF_TRUSTED_ORIGINS = os.environ.get(
    'CSRF_TRUSTED_ORIGINS', 'http://localhost'
).split(',')
```

---

## 5. Database Setup

After the containers are running (see Section 8), initialize the database and create your admin account.

**Run migrations** — creates all the database tables:
```bash
docker compose exec web python3 manage.py migrate
```

**Create the superuser** (your admin login for `/admin/`):
```bash
docker compose exec web python3 manage.py createsuperuser
```

Follow the prompts. Use a strong password — this account has full access to all data.

**Optionally seed demo data:**
```bash
docker compose exec web python3 manage.py seed_events
```

This populates the calendar with sample track events so you can verify everything looks right before entering real data.

**Verify the database file exists on the volume:**
```bash
docker compose exec web ls -la /app/db/
```

You should see `db.sqlite3` listed.

---

## 6. Automated Backups

SQLite backups are simple: copy the database file. The script below uses Docker to pull the file out of the volume and saves it to a local directory, then prunes old backups.

### Create the Backup Script

The backup script is included at `deployment/backup-db.sh`. Copy it to the project root and make it executable:

```bash
cp deployment/backup-db.sh ~/apps/asi-track-manager/backup-db.sh
chmod +x ~/apps/asi-track-manager/backup-db.sh
```

> **Why `sqlite3 .backup` instead of a plain file copy?** The `.backup` command is SQLite's built-in hot backup mechanism — it safely snapshots the database even if a write is happening simultaneously. A plain file copy during an active write can produce a corrupt backup.

### Schedule the Backup with cron

```bash
crontab -e
```

Add this line at the bottom (runs daily at 2:00 AM):
```
0 2 * * * /home/ubuntu/apps/asi-track-manager/backup-db.sh >> /home/ubuntu/logs/asi-backup.log 2>&1
```

> Adjust the path if your WSL username isn't `ubuntu` — use `echo $HOME` in the terminal to confirm.

Create the log directory:
```bash
mkdir -p ~/logs
```

**Test the backup manually first:**
```bash
~/apps/asi-track-manager/backup-db.sh
```

Confirm a file appears in `~/backups/asi-track-manager/`.

### Restoring from Backup

```bash
# Stop the app so nothing is writing to the DB
docker compose -f ~/apps/asi-track-manager/docker-compose.yml stop web

# Copy the backup into the container's volume
CONTAINER=$(docker compose -f ~/apps/asi-track-manager/docker-compose.yml ps -q web)
docker cp ~/backups/asi-track-manager/db_2026-03-15_020000.sqlite3 "${CONTAINER}:/app/db/db.sqlite3"

# Restart
docker compose -f ~/apps/asi-track-manager/docker-compose.yml start web
```

---

## 7. Auto-Update from GitHub

When code is pushed to the `main` branch on GitHub, you want the server to pull the changes and rebuild. Two options are provided below — choose one.

### The Update Script (used by both options)

The update script is included at `deployment/update-app.sh`. Copy it to the project root and make it executable:

```bash
cp deployment/update-app.sh ~/apps/asi-track-manager/update-app.sh
chmod +x ~/apps/asi-track-manager/update-app.sh
```

---

### Option A: GitHub Webhook (Recommended)

A webhook listener container runs alongside the app and triggers `update-app.sh` whenever GitHub pushes to `main`. This means updates happen within seconds of a push, with no polling.

**Step 1:** The webhook listener code is in `deployment/webhook/`. It gets built by Docker Compose automatically.

**Step 2:** Add the webhook service to your `docker-compose.yml` (already included in the deployment version).

**Step 3:** Add `WEBHOOK_SECRET` to your `.env` file:
```bash
echo "WEBHOOK_SECRET=choose-a-long-random-string-here" >> ~/apps/asi-track-manager/.env
```

**Step 4: Open the webhook port in Windows Firewall** (from PowerShell as Administrator):
```powershell
New-NetFirewallRule -DisplayName "ASI Webhook" -Direction Inbound -Protocol TCP -LocalPort 9000 -Action Allow
```

**Step 5: Configure the GitHub webhook**

1. Go to `https://github.com/wksaurey/asi-track-manager/settings/hooks`
2. Click **Add webhook**
3. Payload URL: `http://<VM-IP>:9000/webhook`
4. Content type: `application/json`
5. Secret: the same value you put in `WEBHOOK_SECRET`
6. Which events: **Just the push event**
7. Check **Active** and save

> Note: GitHub webhooks require the VM to be reachable from the internet on port 9000. If the VM is fully internal (no public IP), use Option B instead.

---

### Option B: Scheduled Polling (Simpler, No Public IP Required)

The polling script is included at `deployment/check-for-updates.sh`. Copy it to the project root and make it executable:

```bash
cp deployment/check-for-updates.sh ~/apps/asi-track-manager/check-for-updates.sh
chmod +x ~/apps/asi-track-manager/check-for-updates.sh
```

**Schedule it with cron:**

```bash
crontab -e
```

Add this line (polls every 5 minutes):
```
*/5 * * * * /home/ubuntu/apps/asi-track-manager/check-for-updates.sh >> /home/ubuntu/logs/asi-updates.log 2>&1
```

---

## 8. First-Time Deploy (Step-by-Step Checklist)

Complete these steps in order. All commands run in the **Ubuntu (WSL2) terminal** unless noted.

1. **Install WSL2 + Ubuntu on the VM** — run from PowerShell as Administrator:
   ```powershell
   wsl --install
   ```
   Reboot when prompted.

2. **Enable systemd** — from Ubuntu terminal:
   ```bash
   sudo tee /etc/wsl.conf > /dev/null <<'EOF'
   [boot]
   systemd=true
   EOF
   ```
   Then from PowerShell: `wsl --shutdown && wsl -d Ubuntu`

3. **Install Docker Engine** — follow the steps in Prerequisites section 3

4. **Install Git:** `sudo apt-get install -y git`

5. **Configure WSL2 auto-start and network access** — follow the "WSL2 Auto-Start and Network Access" section

6. **Clone the repository:**
   ```bash
   mkdir -p ~/apps && cd ~/apps
   git clone https://github.com/wksaurey/asi-track-manager.git
   cd asi-track-manager
   ```

7. **Copy deployment files to project root:**
   ```bash
   cp deployment/Dockerfile .
   cp deployment/docker-compose.yml .
   cp deployment/Caddyfile .
   cp deployment/backup-db.sh .
   cp deployment/update-app.sh .
   cp deployment/check-for-updates.sh .
   chmod +x backup-db.sh update-app.sh check-for-updates.sh
   ```

8. **Update `settings.py`** — apply all changes from Section 4

9. **Create the `.env` file** — follow Section 1, generate a fresh SECRET_KEY

10. **Build and start the containers:**
    ```bash
    cd ~/apps/asi-track-manager
    docker compose up -d --build
    ```
    First build takes 2–5 minutes (downloading Python image, installing packages).

11. **Check that containers are running:**
    ```bash
    docker compose ps
    ```
    Both `web` and `caddy` should show `Up`.

12. **Run database migrations:**
    ```bash
    docker compose exec web python3 manage.py migrate
    ```

13. **Create the superuser:**
    ```bash
    docker compose exec web python3 manage.py createsuperuser
    ```

14. **Test locally on the VM:**
    Open a browser on the VM and go to `https://localhost`
    - Accept the self-signed cert warning (click Advanced → Proceed)
    - You should see the login page — log in with your superuser credentials
    - Navigate to `/admin/` to verify admin access

15. **Have IT point `schedule.asi.com` to the VM's IP address**

16. **Test via the domain name:**
    From another machine on the network, open `https://schedule.asi.com`
    - Accept the cert warning once
    - Verify the app loads

17. **Set up automated backups** — follow Section 6, test the backup script manually

18. **Set up auto-update** — follow Section 7, choose Option A (webhook) or Option B (polling)

19. **Review the security checklist** — Section 10

---

## 9. Maintenance and Troubleshooting

### Day-to-Day Operations

**View live logs** (run inside Ubuntu terminal):
```bash
cd ~/apps/asi-track-manager
docker compose logs -f web
```
Press `Ctrl+C` to stop following. To see Caddy logs: `docker compose logs -f caddy`

**Restart the app** (without rebuilding — fast):
```bash
docker compose restart web
```

**Full rebuild** (after code changes if not using auto-update):
```bash
docker compose down
docker compose up -d --build
```

**Open a Django shell** (for debugging or data inspection):
```bash
docker compose exec web python3 manage.py shell
```

**Open the SQLite database directly:**
```bash
docker compose exec web python3 manage.py dbshell
```

**Check disk usage of Docker volumes:**
```bash
docker system df
```

### Updating After a Code Change (Manual)

```bash
cd ~/apps/asi-track-manager
git pull origin main
docker compose build --no-cache
docker compose up -d
docker compose exec web python3 manage.py migrate --noinput
```

### Common Issues

**Port 80 or 443 already in use inside WSL**

```bash
sudo ss -tlnp | grep -E ':80|:443'
```

If something else is using those ports, stop it or change Caddy's ports in `docker-compose.yml` (e.g., `8443:443`).

**Port 80 or 443 in use on the Windows host (IIS, etc.)**

From PowerShell:
```powershell
netstat -ano | findstr ":443 "
# Note the PID, then:
tasklist | findstr <PID>
```

Either stop IIS (`Stop-Service W3SVC`) or use alternate ports.

**`schedule.asi.com` doesn't resolve**

DNS propagation can take a few minutes. Test with:
```bash
nslookup schedule.asi.com
```

As a temporary workaround, add a line to `C:\Windows\System32\drivers\etc\hosts` on the **client** machine (not the server):
```
<VM-IP>  schedule.asi.com
```

**Containers stop when WSL restarts**

If Docker is configured with `restart: unless-stopped` and systemd is enabled, containers come back automatically when WSL starts. If they don't:
```bash
sudo systemctl status docker
docker compose -f ~/apps/asi-track-manager/docker-compose.yml up -d
```

**Browser shows cert warning every time**

This is expected with `tls internal` (Caddy's self-signed CA). Users need to accept it once per browser. To eliminate warnings permanently, export Caddy's local CA certificate and distribute it to users:

```bash
docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt
```

Users install `caddy-root.crt` as a trusted root certificate in their browser or OS.

**Static files (CSS/JS) not loading**

Make sure `collectstatic` ran during the build (it's in the Dockerfile `CMD`). Run manually if needed:
```bash
docker compose exec web python3 manage.py collectstatic --noinput
```

**502 Bad Gateway from Caddy**

The `web` container isn't responding. Check:
```bash
docker compose logs web
docker compose ps
```

If `web` crashed, check for Python errors in the logs. Often caused by a missing environment variable or a `settings.py` syntax error.

**Migrations fail with "table already exists"**

Rarely happens if a partial migration ran. Check the current state:
```bash
docker compose exec web python3 manage.py showmigrations
```

If needed, you can fake a specific migration:
```bash
docker compose exec web python3 manage.py migrate --fake <app_name> <migration_name>
```

---

## 10. Security Checklist

Before going live, confirm each item:

- [ ] `SECRET_KEY` is a newly generated key, not the default from the repo
- [ ] `SECRET_KEY` is only in `.env`, not in `settings.py` or anywhere in the git history
- [ ] `DEBUG=False` in the `.env` file
- [ ] `ALLOWED_HOSTS` is set to `schedule.asi.com,localhost` (not `*`)
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https://schedule.asi.com`
- [ ] `.env` is listed in `.gitignore` (it already is — verify with `git status`)
- [ ] `db.sqlite3` is **not** tracked by git (verify: `git ls-files db.sqlite3` should return nothing)
- [ ] The superuser account has a strong, unique password
- [ ] Automated backups are running and you have manually verified a backup file was created
- [ ] The backup directory (`~/backups/asi-track-manager/`) has appropriate permissions (`chmod 700 ~/backups`)
- [ ] WSL auto-start Task Scheduler task is configured and tested (reboot the VM and verify the app comes back)
- [ ] Windows Firewall rules for ports 80 and 443 are in place
- [ ] The VM has a static IP (so DNS doesn't break after a reboot)

---

## Appendix: File Summary

After completing setup, your `~/apps/asi-track-manager/` directory should contain these deployment-specific files:

```
~/apps/asi-track-manager/
├── .env                        # Secrets — never commit this
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # Orchestrates web + caddy services
├── Caddyfile                   # Caddy reverse proxy + HTTPS config
├── backup-db.sh                # Daily backup script (run via cron)
├── update-app.sh               # Rebuild + redeploy script
├── check-for-updates.sh        # Polling auto-update (Option B)
└── webhook/                    # Webhook listener (Option A only)
    ├── app.py
    ├── requirements.txt
    └── Dockerfile
```

The existing application files (`manage.py`, `asi_track_manager/`, `cal/`, `users/`, `templates/`, `requirements.txt`) are unchanged except for the `settings.py` modifications in Section 4.
