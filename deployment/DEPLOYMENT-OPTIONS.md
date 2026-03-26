# ASI Track Manager — Deployment Options

This document compares four deployment strategies for the ASI Track Manager on the ASI Mendon VM. The VM is a Windows machine running inside Hyper-V. The options are listed from simplest to most complex.

---

## Quick Comparison

| Option | Requires WSL2? | Requires Docker? | Complexity | Production-Ready? |
|--------|---------------|-------------------|------------|-------------------|
| **1. Native Windows + Waitress** | No | No | Low | Yes |
| **2. Packaged EXE (PyInstaller)** | No | No | Medium | Yes (with caveats) |
| **3. Docker + WSL2** | Yes | Yes | Medium-High | Yes |
| **4. Docker Desktop (Hyper-V backend)** | No | Yes | High | Yes |

---

## Option 1: Native Windows + Waitress (Recommended)

**Overview:** Install Python directly on Windows, run Django with Waitress (a production-quality WSGI server that works natively on Windows). No containers, no Linux layer.

**Why Waitress?** Gunicorn (used in the Docker deployment) is Linux-only. Waitress is the standard Windows-compatible alternative — it's maintained by the Pylons Project, battle-tested, and used in production by many Django/Flask apps.

### Prerequisites

- Python 3.12+ installed from [python.org](https://www.python.org/downloads/) (check "Add to PATH" during install)
- Git for Windows (optional — can copy code via file share instead)

### Setup

```powershell
# Clone or copy the project
cd C:\apps
git clone https://github.com/wksaurey/asi-track-manager.git
cd asi-track-manager

# Create virtual environment and install dependencies
mkdir .venv
python -m venv .venv\asi_track_manager
.venv\asi_track_manager\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root (or set environment variables via Windows):

```
SECRET_KEY=<generate-a-random-key>
DEBUG=False
ALLOWED_HOSTS=schedule.asi.com,localhost
CSRF_TRUSTED_ORIGINS=https://schedule.asi.com,https://localhost
```

Generate a secret key:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Database Setup

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

### Running the Server

```powershell
# Basic startup
waitress-serve --host=0.0.0.0 --port=8080 --threads=4 asi_track_manager.wsgi:application
```

Or create a startup script (`start-server.ps1`):

```powershell
# start-server.ps1
$env:DJANGO_SETTINGS_MODULE = "asi_track_manager.settings"
Set-Location C:\apps\asi-track-manager
& C:\apps\asi-track-manager\.venv\Scripts\Activate.ps1
waitress-serve --host=0.0.0.0 --port=8080 --threads=4 asi_track_manager.wsgi:application
```

### Running as a Windows Service

To keep the app running in the background and auto-start on boot, use **NSSM** (Non-Sucking Service Manager):

1. Download NSSM from [nssm.cc](https://nssm.cc/download)
2. Install the service:

```powershell
nssm install ASITrackManager C:\apps\asi-track-manager\.venv\Scripts\waitress-serve.exe
nssm set ASITrackManager AppParameters "--host=0.0.0.0 --port=8080 --threads=4 asi_track_manager.wsgi:application"
nssm set ASITrackManager AppDirectory C:\apps\asi-track-manager
nssm set ASITrackManager AppEnvironmentExtra "SECRET_KEY=<your-key>" "DEBUG=False" "ALLOWED_HOSTS=schedule.asi.com,localhost"
nssm set ASITrackManager DisplayName "ASI Track Manager"
nssm set ASITrackManager Description "ASI Track Scheduler Web Application"
nssm set ASITrackManager Start SERVICE_AUTO_START
nssm start ASITrackManager
```

The service will now auto-start on boot, restart on crash, and can be managed from Windows Services (`services.msc`).

### HTTPS

Without Caddy handling HTTPS, you have two options:

1. **IIS as a reverse proxy:** If IIS is available on the VM, configure it as a reverse proxy to `localhost:8080` with an SSL binding. IT may already have internal CA certificates for this.
2. **Direct HTTP:** For an internal-only tool, running on HTTP (port 80 or 8080) may be acceptable. Users access `http://schedule.asi.com:8080`.

### Backups

Set up a Windows Scheduled Task to copy the SQLite database file:

```powershell
# backup-db.ps1
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupDir = "C:\backups\asi-track-manager"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item "C:\apps\asi-track-manager\db.sqlite3" "$backupDir\db_$timestamp.sqlite3"
# Keep last 30 backups
Get-ChildItem $backupDir -Filter "db_*.sqlite3" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item
```

### Pros

- Simplest deployment — no Docker, no WSL, no Linux knowledge needed
- Minimal IT involvement (just Python and a firewall rule)
- Easy to debug — everything is in one place on the Windows filesystem
- Fast startup, low resource overhead

### Cons

- No container isolation (app runs directly on the OS)
- Updates require manually pulling code and restarting the service
- No built-in HTTPS (need IIS or accept HTTP for internal use)

---

## Option 2: Packaged EXE (PyInstaller)

**Overview:** Bundle the entire application — Python runtime, all dependencies, Django, templates, static files — into a standalone Windows executable. IT receives a single folder they can drop on the VM and run.

### How It Works

PyInstaller analyzes the Python application and packages everything needed to run it into a `dist/` folder. The entry point is a small script that starts Waitress serving the Django app.

### Entry Point Script

```python
# run_server.py
import os
import sys

# When running as a PyInstaller bundle, adjust paths
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.environ['DJANGO_STATIC_ROOT'] = os.path.join(BASE_DIR, 'staticfiles')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asi_track_manager.settings')
os.environ.setdefault('DB_PATH', os.path.join(BASE_DIR, 'db.sqlite3'))

import django
django.setup()

from django.core.management import call_command
call_command('migrate', '--run-syncdb', verbosity=0)
call_command('collectstatic', '--noinput', verbosity=0)

from waitress import serve
from asi_track_manager.wsgi import application

print("=" * 50)
print("ASI Track Manager is running!")
print("Open http://localhost:8080 in your browser")
print("Press Ctrl+C to stop")
print("=" * 50)

serve(application, host='0.0.0.0', port=8080, threads=4)
```

### Build Command

```powershell
pip install pyinstaller
pyinstaller --name ASITrackManager `
    --add-data "cal;cal" `
    --add-data "users;users" `
    --add-data "static;static" `
    --add-data "templates;templates" `
    --add-data "asi_track_manager;asi_track_manager" `
    --hidden-import "django.contrib.admin" `
    --hidden-import "django.contrib.auth" `
    --hidden-import "django.contrib.contenttypes" `
    --hidden-import "django.contrib.sessions" `
    --hidden-import "django.contrib.messages" `
    --hidden-import "django.contrib.staticfiles" `
    run_server.py
```

### Distribution

The `dist/ASITrackManager/` folder contains everything needed. Copy the folder to the VM, double-click `ASITrackManager.exe`, and the web server starts. The SQLite database is created next to the executable.

### Pros

- Zero dependencies on the target machine (no Python install, no Docker, no WSL)
- Simple to distribute — copy a folder, run an exe
- Good for environments where installing software requires lengthy approval

### Cons

- Larger package size (~50-100 MB)
- Slower startup (PyInstaller extracts bundled files at launch)
- Build process requires some trial and error to get all Django dependencies included
- Updates require rebuilding and redistributing the entire package
- Django + PyInstaller can have edge cases with template discovery and static files that need testing
- Harder to debug issues on the target machine

---

## Option 3: Docker + WSL2 (Original Plan)

**Overview:** Run the app in Docker containers inside Ubuntu on WSL2. This is the original deployment plan documented in `DEPLOYMENT.md`.

### Requirements

- WSL2 enabled on the Hyper-V VM (requires IT to allow the `wsl --install` feature)
- Docker Engine installed inside the WSL2 Ubuntu instance

### Why This Was the Original Choice

- Industry-standard containerized deployment
- Caddy provides automatic HTTPS with zero configuration
- Docker Compose orchestrates the web server and reverse proxy
- Automated backups and updates via cron
- Identical environment between development and production

### Current Blocker

IT has not yet enabled the WSL2 feature on the Hyper-V VM. WSL2 requires the "Virtual Machine Platform" Windows feature, which IT needs to allow within the Hyper-V VM settings.

### Full Documentation

See `DEPLOYMENT.md` for the complete step-by-step guide for this option.

### Pros

- Most robust and well-documented option
- Container isolation
- Built-in HTTPS via Caddy
- Automated backup and update infrastructure already built
- Reproducible environment

### Cons

- Requires IT to enable WSL2 on the Hyper-V VM
- More moving parts (Docker, WSL2, Caddy, systemd)
- Slightly higher resource usage than native Windows

---

## Option 4: Docker Desktop (Hyper-V Backend)

**Overview:** Install Docker Desktop for Windows, which can use the Hyper-V backend instead of WSL2. Run the same Docker Compose setup but on the Windows side.

### How It Differs from Option 3

Docker Desktop for Windows has two backend modes:
1. **WSL2 backend** (default, requires WSL2) — this is what Option 3 uses via Docker Engine inside WSL
2. **Hyper-V backend** — runs a lightweight Linux VM using Hyper-V directly

### Requirements

- Hyper-V enabled on the VM (it likely already is since this is a Hyper-V VM)
- **Nested virtualization** must be enabled on the Hyper-V host for the guest VM
- Docker Desktop for Windows installed with "Use Hyper-V instead of WSL2" selected during setup

### The Catch

Running Docker Desktop's Hyper-V backend inside a Hyper-V VM requires **nested virtualization**, which must be enabled on the *host* Hyper-V server by IT:

```powershell
# Run on the Hyper-V HOST (not the VM) — requires IT
Set-VMProcessor -VMName "ASI-VM" -ExposeVirtualizationExtensions $true
```

This may face the same IT approval delays as enabling WSL2, since both require changes to the VM's virtualization settings.

### Pros

- Uses the same Dockerfile and docker-compose.yml as Option 3
- Doesn't require WSL2 specifically
- Docker Desktop provides a GUI for managing containers

### Cons

- Likely requires the same IT involvement as Option 3 (nested virtualization)
- Docker Desktop licensing (free for small companies, paid for larger orgs — verify ASI's status)
- Higher resource overhead than native Windows deployment
- Docker Desktop can be finicky with Hyper-V nested virtualization

---

## Recommendation

**For immediate deployment:** Go with **Option 1 (Native Windows + Waitress)**. It requires the least IT involvement — just Python installed and a firewall rule. The app will be production-ready with Waitress serving it as a Windows service.

**When IT enables WSL2:** Migrate to **Option 3 (Docker + WSL2)** for the full containerized setup with Caddy HTTPS, automated backups, and the infrastructure already documented in `DEPLOYMENT.md`.

**Option 2 (EXE)** is a good fallback if even installing Python is a problem, but it adds build complexity for minimal benefit over Option 1.

**Option 4 (Docker Desktop)** is unlikely to bypass the IT blocker since it also requires virtualization changes.
