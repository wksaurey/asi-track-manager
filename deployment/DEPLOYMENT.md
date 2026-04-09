# ASI Track Manager — Deployment Guide

This guide walks you through deploying the ASI Track Manager on a Windows VM using **Waitress** as the production WSGI server. Commands use `python` (Windows). For development setup on WSL2/Linux, see the project `README.md` (which uses `python3`).

**Stack:**
- **Django 5.2** (Python 3.12) served by **Waitress**
- **SQLite** database (stored in the project directory)
- **WhiteNoise** for static file serving
- **Windows Task Scheduler** for auto-start on boot
- **PowerShell** for backup automation

---

## Prerequisites

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| OS | Windows 10 22H2 | Windows 11 22H2+ |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB free | 40 GB free |
| CPU | 2 cores | 4 cores |

The app is lightweight — 1–15 concurrent users will barely stress these specs.

**Software:**
- **Python 3.12+** — install from [python.org](https://www.python.org/downloads/). Check **"Add to PATH"** during install.
- **Git for Windows** (optional) — can copy code via file share instead.

---

## Setup

Clone or copy the project to the VM:

```powershell
cd C:\apps
git clone https://github.com/wksaurey/asi-track-manager.git
cd asi-track-manager
```

Create a virtual environment and install dependencies:

```powershell
mkdir .venv
python -m venv .venv\asi_track_manager
.venv\asi_track_manager\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Why Waitress?** Django's built-in `runserver` is single-threaded and not safe for production. Waitress is a production-grade Windows-compatible WSGI server — maintained by the Pylons Project and used in production by many Django/Flask apps. It's included in `requirements.txt`.

---

## Configuration

Create a `.env` file in the project root. Django loads this automatically on startup. This file must **never** be committed to git (it's already in `.gitignore`).

Generate a secret key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the example file and fill in the values (replace `<VM-IP>` with the VM's actual IP):

```powershell
copy deployment\env.example .env
```

See `deployment/env.example` for the template with all available variables. Key notes:

> - `SECRET_KEY` signs cookies and tokens — must be secret and unique per deployment. Generate one with the command above.
> - `DEBUG=False` disables the interactive error page (which leaks code internals).
> - `ALLOWED_HOSTS` prevents HTTP Host header attacks. Include every hostname/IP users will access.
> - `CSRF_TRUSTED_ORIGINS` is required by Django 4+ — include the full origin with scheme (`http://...`).

> **Note:** No `https://` origins are listed because there are no TLS certificates configured. If you later add HTTPS via IIS reverse proxy, add the `https://` origins at that time.

---

## Database Setup

With the virtual environment activated:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

- **migrate** creates all the database tables (SQLite file appears as `db.sqlite3` in the project root).
- **createsuperuser** creates your admin login. Use a strong password — this account has full access.
- **collectstatic** copies static files (CSS, JS, images) into `staticfiles/` for WhiteNoise to serve.

---

## Running Manually

To start the server interactively (useful for testing):

```powershell
waitress-serve --host=0.0.0.0 --port=80 --threads=4 asi_track_manager.wsgi:application
```

The app will be available at `http://localhost`. Press `Ctrl+C` to stop.

> **Why `--threads=4` and not multiple workers?** SQLite doesn't support concurrent writes from multiple processes. A single process with multiple threads keeps things safe. Upgrade to `--workers N` only after migrating to PostgreSQL.

---

## Running as a Windows Task Scheduler Task

Task Scheduler keeps the app running in the background and auto-starts it on boot. No extra software required.

1. Open **Task Scheduler** (search in Start Menu).

2. Click **Create Task** (not "Create Basic Task" — we need more control).

3. **General tab:**
   - Name: `ASI Track Manager`
   - Description: `ASI Track Scheduler Web Application`
   - Check **"Run whether user is logged on or not"**
   - Check **"Run with highest privileges"**

4. **Triggers tab:**
   - Click **New...** → Begin the task: **At startup** → OK

5. **Actions tab:**
   - Click **New...**
   - Action: **Start a program**
   - Program/script: `C:\apps\asi-track-manager\.venv\asi_track_manager\Scripts\waitress-serve.exe`
   - Add arguments: `--host=0.0.0.0 --port=80 --threads=4 asi_track_manager.wsgi:application`
   - Start in: `C:\apps\asi-track-manager`
   - Click OK

6. **Settings tab:**
   - Uncheck **"Stop the task if it runs longer than"**
   - Check **"If the task fails, restart every"** → **1 minute**, up to **3 times**
   - Check **"Allow task to be run on demand"**
   - Click OK

7. Enter the Windows account password when prompted.

8. Right-click the task → **Run** to start it immediately.

---

## Managing the Task

- **Stop:** Right-click the task → End
- **Start:** Right-click the task → Run
- **View status:** Check the "Last Run Result" column in Task Scheduler

---

## Windows Firewall

Open the app's port (run PowerShell as Administrator):

```powershell
New-NetFirewallRule -DisplayName "ASI Track Manager HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
```

---

## DNS Setup

Ask IT to create an internal DNS A record:

```
schedule.asi.com → <VM-IP>
```

To find the VM's IP:

```powershell
ipconfig
# Look for the IPv4 Address of your primary network adapter
```

**Temporary workaround** until IT creates the record — on each client machine, add the following line to `C:\Windows\System32\drivers\etc\hosts` (requires admin):

```
<VM-IP>  schedule.asi.com
```

---

## HTTPS

The app runs on HTTP by default. For an internal-only tool, this is acceptable.

If you want HTTPS, two options:

1. **IIS as a reverse proxy:** If IIS is available on the VM, configure it to reverse-proxy to `http://localhost:80` with an SSL binding. IT may already have internal CA certificates for this.
2. **Accept HTTP:** For an internal tool behind a corporate firewall, plain HTTP is fine. Users access `http://schedule.asi.com`.

If you add HTTPS later, update `CSRF_TRUSTED_ORIGINS` in `.env` to include the `https://` origins.

---

## Backups

SQLite backups are simple: copy the database file. Create `C:\apps\asi-track-manager\backup-db.ps1`:

```powershell
# backup-db.ps1 — Daily SQLite backup for ASI Track Manager
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupDir = "C:\backups\asi-track-manager"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item "C:\apps\asi-track-manager\db.sqlite3" "$backupDir\db_$timestamp.sqlite3"
# Keep last 30 backups
Get-ChildItem $backupDir -Filter "db_*.sqlite3" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item
```

Schedule via Task Scheduler:

1. Create a new task named `ASI Track Manager — Backup`.
2. **Triggers tab:** Daily at 2:00 AM.
3. **Actions tab:**
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File C:\apps\asi-track-manager\backup-db.ps1`
4. Enter Windows account password when prompted.

**Test it manually first:**

```powershell
powershell -ExecutionPolicy Bypass -File C:\apps\asi-track-manager\backup-db.ps1
```

Confirm a file appears in `C:\backups\asi-track-manager\`.

### Restoring from Backup

```powershell
# 1. Stop the Task Scheduler task (right-click → End)
# 2. Replace the database:
Copy-Item "C:\backups\asi-track-manager\db_2026-04-01_020000.sqlite3" "C:\apps\asi-track-manager\db.sqlite3"
# 3. Start the task again (right-click → Run)
```

---

## Updating After a Code Change

```powershell
# 1. Stop the scheduled task (right-click → End in Task Scheduler)

# 2. Pull and rebuild:
cd C:\apps\asi-track-manager
.venv\asi_track_manager\Scripts\Activate.ps1
git pull origin main
pip install -r requirements.txt

# 3. Test migrations against prod data BEFORE applying:
python manage.py preflight_migrate
# If this fails, DO NOT run migrate — fix the issue first.

# 4. Apply migrations and rebuild static files:
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 5. Start the scheduled task (right-click → Run in Task Scheduler)
```

---

## Troubleshooting

### Port 80 in Use

```powershell
netstat -ano | findstr ":80 "
# Note the PID, then:
tasklist | findstr <PID>
```

If IIS is using port 80, stop it: `Stop-Service W3SVC`

### DNS Not Resolving

```powershell
nslookup schedule.asi.com
```

If it fails, DNS hasn't propagated yet. Use the hosts file workaround described in the DNS Setup section above.

### Static Files Not Loading

Run `collectstatic` again with the virtual environment activated:

```powershell
python manage.py collectstatic --noinput
```

### 500 Errors

Temporarily set `DEBUG=True` in `.env`, restart the task, and reproduce the error. Django will show a detailed error page. **Set it back to `False` immediately after debugging.**

### Host Header / 400 Errors

If you see "Bad Request (400)", the hostname or IP the user typed isn't in `ALLOWED_HOSTS`. Add it to the comma-separated list in `.env` and restart the task.

---

## Security Checklist

Before going live, confirm each item:

- [ ] `SECRET_KEY` is a newly generated key, not the default from the repo
- [ ] `SECRET_KEY` is only in `.env`, not in `settings.py` or anywhere in the git history
- [ ] `DEBUG=False` in the `.env` file
- [ ] `ALLOWED_HOSTS` lists only the expected hostnames/IPs (not `*`)
- [ ] `CSRF_TRUSTED_ORIGINS` includes all origins users will access
- [ ] `.env` is listed in `.gitignore` (verify with `git status`)
- [ ] `db.sqlite3` is **not** tracked by git (verify: `git ls-files db.sqlite3` returns nothing)
- [ ] The superuser account has a strong, unique password
- [ ] Automated backups are running and you've verified a backup file was created
- [ ] The backup directory (`C:\backups\asi-track-manager\`) has appropriate permissions
- [ ] Task Scheduler task is configured and tested (reboot the VM and verify the app comes back)
- [ ] Windows Firewall rule for port 80 is in place
- [ ] The VM has a static IP (so DNS doesn't break after a reboot)

---

## File Summary

After setup, the deployment-relevant files in `C:\apps\asi-track-manager\` are:

```
C:\apps\asi-track-manager\
├── .env                  # Secrets — never commit this
├── db.sqlite3            # SQLite database (created by migrate)
├── staticfiles\          # Collected static files (created by collectstatic)
├── backup-db.ps1         # Daily backup script (run via Task Scheduler)
└── ... (application files: manage.py, cal/, users/, templates/, etc.)
```
