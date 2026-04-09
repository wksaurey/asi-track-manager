# CLAUDE.md

## Project Overview

**ASI Track Manager** — Django web app for ASI employees to reserve testing tracks, vehicles, and operators on the ASI Mendon Campus. Calendar-based scheduling with conflict detection, approval workflow, and a control center dashboard.

## Commands

Development runs on WSL2 (Linux) — use `python3`. Windows deployment uses `python` (see `deployment/DEPLOYMENT.md`).

```bash
# Development
python3 manage.py runserver
python3 manage.py migrate
python3 manage.py createsuperuser

# Test data (resets DB with seed assets/users + generated events)
python3 manage.py setup_testdb              # fresh DB, 7 days of events
python3 manage.py setup_testdb --days 30    # wider date range
python3 manage.py setup_testdb --keep-db    # add events without reset

# Testing
python3 manage.py test              # all tests
python3 manage.py test cal          # cal app only
python3 manage.py test users        # users app only
```

## Architecture

Django MTV with two apps (`cal`, `users`). SQLite DB, Bootstrap 4, native Windows + Waitress deployment.

**Models:** `Asset` (track/vehicle/operator, self-referential parent FK for subtracks), `Event` (M2M to Asset, approval workflow, nullable start/end times for impromptu events, optional radio channel override), `ActualTimeSegment` (play/pause/stop segments per event), and `Feedback` (user-submitted bug reports/feature requests).

**Shared modules:** `cal/decorators.py` (`@staff_required`, `@staff_required_api`) and `cal/helpers.py` (`parse_api_datetime`, `validate_radio_channel`, `serialize_segments`, `stamp_response`). Module-level `RADIO_CHANNEL_CHOICES` in `cal/models.py`.

**Key rules:**
- One track group per reservation (multiple subtracks of same parent OK)
- Multi-subtrack events (booked on 2+ subtracks of same parent) are promoted to full-track events in day view and dashboard API
- Booking a parent track conflicts with all subtracks and vice versa
- All events default to pending (unapproved) regardless of creator — must go through approval workflow
- Case-insensitive login (custom auth backend in `users/backends.py`)
- Per-event radio channel override (defaults to track's channel, channels 1-16); admin-only in event form
- Impromptu events have null start_time/end_time — created from dashboard, open a segment immediately
- Single-day events only (no midnight spanning)
- Event form uses separate date/time fields (event_date, start_time_only, end_time_only); server-side combine in form.clean()
- Stale open segments from previous days are auto-closed at 23:59:59 of their start day

**Routes:** See `cal/urls.py` and `users/urls.py` for the full URL structure and API endpoints.

**Deployment:** Waitress with `--threads 4` (single process, SQLite constraint). See `deployment/DEPLOYMENT.md`.

## Key Patterns

Detailed UI patterns are in path-scoped `.claude/rules/` files (loaded automatically when working on relevant files):

- **`gantt-day-view.md`** — six event states, segment rendering, connectors, tooltips, color palette
- **`dashboard.md`** — stamping, radio channels, serialization, impromptu events
- **`ui-patterns.md`** — modals, asset picker, pending filter, mobile responsive, duration shortcuts

## Seed Data

Fixture at `cal/fixtures/seed.json` contains 31 assets (7 parent tracks + 11 subtracks + 13 vehicles) and 2 users (admin, kolter). `setup_testdb` command loads this fixture and generates realistic events.

## Git Workflow

See `README.md` for the full git workflow. Key points for Claude:
- **NEVER commit directly to `main`** — always create a feature branch first
- Before starting any work, verify you are NOT on `main`: `git branch --show-current`
- Use `/commit` skill — enforces atomic commits, conventional prefixes, test-before-commit, and split detection
- PRs: small (under ~400 lines), description says WHY. Before `/ship`, check diff size and warn if over ~400 lines

## Server Update Procedure

See `deployment/DEPLOYMENT.md` ("Updating After a Code Change" section) for the full procedure. The server is at `test-scl-mobius00.asi.asirobots.com` (10.10.105.198), running native Windows + Waitress via Task Scheduler.

## Web Browsing

Use `/browse` for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

## Out of Scope

Vehicle maintenance, notification/calendar syncing, Jira integration, recurring reservations. See `TODOS.md` for v2 priorities.
