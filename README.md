# ASI Track Manager

A Django-based scheduling and asset management system for ASI Mendon Campus. Reserve and track vehicles, testing tracks, and operators across time slots with a calendar interface, approval workflow, and a control center dashboard.

## Features

- **Multi-view calendar** -- month, week, and day views with navigation and asset filtering
- **Gantt day view** -- lane-per-asset Gantt layout with six event states (scheduled, active, paused, completed, no-show, pending), connector lines, hover tooltips, and a live "Now" line
- **Asset management** -- tracks, vehicles, and operators with color-coded display and WCAG AA compliant palette
- **Subtrack support** -- parent/child track relationships; booking a parent conflicts with all subtracks and vice versa
- **Conflict detection** -- prevents double-booking assets during overlapping time slots
- **Approval workflow** -- all events default to pending and require admin approval; mass-approve with conflict detection
- **Control center dashboard** -- admin-only live view with play/pause/stop time tracking, radio channel controls, and impromptu event creation
- **Analytics** -- track utilization and event statistics
- **Feedback** -- in-app bug reports and feature requests with admin resolution tracking
- **Mobile responsive** -- 768px/480px breakpoints, hamburger nav, collapsible Gantt labels
- **Dark/light theme** -- toggle with localStorage persistence

## Tech Stack

- Python 3.12 / Django 5.2
- SQLite (single-process Waitress constraint)
- Bootstrap 4, FontAwesome 5, Flatpickr (via CDN)
- Waitress (production WSGI server on Windows)

## Setup

> Development is done on WSL2 (Linux). Commands below use `python3`. For Windows deployment commands, see [`deployment/DEPLOYMENT.md`](deployment/DEPLOYMENT.md) (which uses `python`).

1. Create and activate a virtual environment:

    ```bash
    python3 -m venv .venv/asi-track-manager
    . ./.venv/asi-track-manager/bin/activate
    ```

2. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Run migrations:

    ```bash
    python3 manage.py migrate
    ```

4. Create an admin user:

    ```bash
    python3 manage.py createsuperuser
    ```

5. Start the development server:

    ```bash
    python3 manage.py runserver
    ```

## Test Data

Load seed assets and generate realistic events:

```bash
python3 manage.py setup_testdb              # fresh DB, 7 days of events
python3 manage.py setup_testdb --days 30    # wider date range
python3 manage.py setup_testdb --keep-db    # add events without reset
```

Default test accounts: `admin`/`admin` (staff) and `kolter`/`testpass123`.

## Testing

Comprehensive test suite covering access control, event CRUD, approval workflow, conflict detection, calendar rendering, dashboard APIs, analytics, user management, and more.

```bash
python3 manage.py test              # all tests
python3 manage.py test cal          # cal app only
python3 manage.py test users        # users app only
```

## Environment Variables

For production, create a `.env` file in the project root (see `deployment/env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | insecure dev default |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | CSRF trusted origins | none |
| `DB_PATH` | SQLite database path | `db.sqlite3` in project root |

## Development

- Activate the venv each time you start work
- After installing a new package: `pip freeze > requirements.txt`
- After changing models: `python3 manage.py makemigrations && python3 manage.py migrate`

## Deployment

Production runs on a Windows VM with Waitress. See [`deployment/DEPLOYMENT.md`](deployment/DEPLOYMENT.md) for the full guide, [`deployment/PRE_DEPLOY.md`](deployment/PRE_DEPLOY.md) for pre-deploy checks, and [`deployment/POST_DEPLOY.md`](deployment/POST_DEPLOY.md) for post-deploy verification.

## Git Workflow

Trunk-based flow. `main` is always deployable -- never commit directly to it.

### Starting Work

```bash
# 1. Make sure you're on main and up to date
git checkout main
git pull --rebase origin main

# 2. Create a branch named <type>/<short-description>
git checkout -b feat/my-new-feature
git checkout -b fix/broken-calendar
git checkout -b chore/update-deps
```

Branch type prefixes: `feat/`, `fix/`, `chore/`, `docs/`, `test/`, `refactor/`

### Commits

```bash
# Stage specific files (never git add . or git add -A)
git add cal/views.py cal/models.py
git commit -m "feat: add email notifications for pending approvals"
```

Commit messages use `<type>: <description>` format. Keep the subject under 72 characters. Focus on *why*, not *what*.

### Before Opening a PR

```bash
git pull --rebase origin main
python3 manage.py test
python3 manage.py preflight_migrate   # test migrations against prod data
```

### PRs

- Merge to `main` -- no `dev` or integration branches
- Keep PRs small: under ~400 lines, reviewable in 15 minutes
- Description says WHY, not just what
- If features changed, update README/CLAUDE.md/TODOS.md in the same PR
- Delete the branch after merging
