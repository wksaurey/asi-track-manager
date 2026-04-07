# ASI Track Manager

A Django-based scheduling and asset management system for ASI Mendon Campus. Reserve and track vehicles, heavy equipment tracks, and operators across time slots with a calendar interface and admin approval workflow.

## Features

- **Multi-view calendar** -- month, week, and day views with navigation and asset filtering
- **Gantt/track view** -- day and week views display a lane-per-asset Gantt layout for at-a-glance scheduling
- **Asset management** -- track vehicles, testing tracks, and operators with color-coded display
- **Subtrack support** -- tracks can have parent/child relationships; booking a parent track conflicts with all its subtracks
- **Two-step asset picker** -- clicking a track in the event form reveals a subtrack selection panel before confirming
- **Conflict detection** -- prevents double-booking assets during overlapping time slots
- **Approval workflow** -- user-created events require admin approval; admin events are auto-approved
- **Dark/light theme** -- toggle with localStorage persistence
- **Dual login** -- simple name-based user login or Django admin credentials for staff

## Tech Stack

- Python 3 / Django 5.2
- SQLite
- Bootstrap 4, FontAwesome 5, Flatpickr (via CDN)

## Setup

1. Create and activate a virtual environment:

    ```bash
    mkdir -p .venv/asi-track-manager
    python3 -m venv .venv/asi-track-manager
    . ./.venv/asi-track-manager/bin/activate
    ```

2. Install dependencies:

    ```bash
    python3 -m pip install -r requirements.txt
    ```

3. Run migrations:

    ```bash
    python manage.py migrate
    ```

4. Create an admin user:

    ```bash
    python manage.py createsuperuser
    ```

5. Start the development server:

    ```bash
    python manage.py runserver
    ```

## Development

- Activate the venv each time you start work
- After installing a new module, update requirements:

    ```bash
    python3 -m pip freeze > requirements.txt
    ```

- After changing models, create and apply migrations:

    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

## Git Workflow

Trunk-based flow. `main` is always deployable — never commit directly to it.

### Starting Work

```bash
# 1. Make sure you're on main and up to date
git checkout main
git pull --rebase origin main

# 2. Create a branch named <type>/<short-description>
git checkout -b feat/my-new-feature    # for a new feature
git checkout -b fix/broken-calendar    # for a bug fix
git checkout -b chore/update-deps      # for maintenance
```

Branch type prefixes: `feat/`, `fix/`, `chore/`, `docs/`, `test/`, `refactor/`

### While Working

```bash
# Stage specific files and commit (never git add . or git add -A)
git add cal/views.py cal/models.py
git commit -m "feat: add email notifications for pending approvals"
```

Commit messages use `<type>: <description>` format. Keep the subject under 72 characters. Focus on *why*, not *what*.

### Before Opening a PR

```bash
# Rebase onto latest main to avoid merge conflicts
git pull --rebase origin main

# Run the full test suite
python3 manage.py test

# If deploying migrations, test against prod data first
python3 manage.py preflight_migrate --db /path/to/prod-backup.sqlite3
```

### Opening a PR

- PRs merge to `main` — no `dev` or integration branches
- Keep PRs small: under ~400 lines, reviewable in 15 minutes
- Description says WHY, not just what
- Kolter and Hollis review each other before merging
- Delete the branch after merging
