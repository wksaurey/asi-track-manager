# CLAUDE.md

## Project Overview

**ASI Track Manager** — Django web app for ASI employees to reserve testing tracks, vehicles, and operators on the ASI Mendon Campus. Calendar-based scheduling with conflict detection, approval workflow, and a control center dashboard.

## Commands

```bash
# Setup
python3 -m venv .venv/asi-track-manager
. ./.venv/asi-track-manager/bin/activate
pip install -r requirements.txt

# Development
python3 manage.py runserver
python3 manage.py migrate
python3 manage.py createsuperuser

# Testing (175 tests)
python3 manage.py test              # all tests
python3 manage.py test cal          # cal app only
python3 manage.py test users        # users app only
```

## Architecture

Django MTV with two apps (`cal`, `users`). SQLite DB, Bootstrap 4, Docker/Caddy/Gunicorn deployment.

**Models:** `Asset` (track/vehicle/operator, self-referential parent FK for subtracks) and `Event` (M2M to Asset, approval workflow, actual start/end timestamps).

**Key rules:**
- One track group per reservation (multiple subtracks of same parent OK)
- Booking a parent track conflicts with all subtracks and vice versa
- Admin events auto-approved; user events default to pending
- Case-insensitive login (custom auth backend in `users/backends.py`)

**URL structure:** `/cal/calendar/`, `/cal/event/new/`, `/cal/event/edit/<id>/`, `/cal/event/approve/<id>/`, `/cal/event/unapprove/<id>/`, `/cal/event/delete/<id>/`, `/cal/events/pending/`, `/cal/assets/`, `/cal/assets/new/`, `/cal/assets/<id>/`, `/cal/dashboard/`, `/cal/analytics/`, `/users/login/`, `/users/register/`, `/users/management/`

**Dashboard APIs:** `/cal/api/dashboard-events/`, `/cal/api/event/<id>/stamp/`, `/cal/api/analytics/`

**Deployment:** `--workers 1 --threads 4` (SQLite constraint). See `deployment/` and `TODOS.md`.

## Testing

175 tests covering: access control, event CRUD, approval workflow, conflict detection (including subtrack rules), calendar rendering (month/week/day/Gantt), dashboard APIs, stamp validation, analytics computation, user management (toggle admin, delete user), asset CRUD, color auto-assignment.

## Key Patterns

- **Confirmation modals:** All destructive actions use `confirmDelete(form, msg)` or `showConfirmModal(msg, callback)` — no browser `confirm()`. Defined in `base.html`.
- **Pending filter:** Client-side CSS toggle (`.cal-hide-pending` class), no page reload. State synced to URL via `history.replaceState`.
- **Asset picker:** Custom JS pill-based picker in event form. Single track group, multi-select subtracks, multi-select vehicles/operators.
- **`json_script`:** Asset data passed to templates via Django's `json_script` tag (not `mark_safe`).

## gstack

Use `/browse` for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

## Out of Scope

Vehicle maintenance, notification/calendar syncing, Jira integration, recurring reservations. See `TODOS.md` for v2 priorities.
