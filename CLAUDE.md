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

# Test data (resets DB with seed assets/users + generated events)
python3 manage.py setup_testdb              # fresh DB, 7 days of events
python3 manage.py setup_testdb --days 30    # wider date range
python3 manage.py setup_testdb --keep-db    # add events without reset

# Testing (339+ tests)
python3 manage.py test              # all tests
python3 manage.py test cal          # cal app only
python3 manage.py test users        # users app only
```

## Architecture

Django MTV with two apps (`cal`, `users`). SQLite DB, Bootstrap 4, Docker/Caddy/Gunicorn deployment.

**Models:** `Asset` (track/vehicle/operator, self-referential parent FK for subtracks) and `Event` (M2M to Asset, approval workflow, actual start/end timestamps, optional radio channel override).

**Key rules:**
- One track group per reservation (multiple subtracks of same parent OK)
- Multi-subtrack events (booked on 2+ subtracks of same parent) are promoted to full-track events in day view and dashboard API
- Booking a parent track conflicts with all subtracks and vice versa
- Admin events auto-approved; user events default to pending
- Case-insensitive login (custom auth backend in `users/backends.py`)
- Per-event radio channel override (defaults to track's channel); admin-only in event form

**URL structure:** `/cal/calendar/`, `/cal/event/new/`, `/cal/event/edit/<id>/`, `/cal/event/approve/<id>/`, `/cal/event/unapprove/<id>/`, `/cal/event/delete/<id>/`, `/cal/events/pending/`, `/cal/assets/`, `/cal/assets/new/`, `/cal/assets/<id>/`, `/cal/dashboard/`, `/cal/analytics/`, `/users/login/`, `/users/register/`, `/users/management/`

**Dashboard APIs:** `/cal/api/dashboard-events/`, `/cal/api/event/<id>/stamp/`, `/cal/api/event/<id>/channel/`, `/cal/api/track/<id>/channel/`, `/cal/api/analytics/`

**Deployment:** `--workers 1 --threads 4` (SQLite constraint). See `deployment/` and `TODOS.md`.

## Testing

339+ tests covering: access control, event CRUD, approval workflow, conflict detection (including subtrack rules), calendar rendering (month/week/day/Gantt), dashboard APIs, stamp validation, analytics computation, user management (toggle admin, delete user), asset CRUD, color auto-assignment, dark-mode CSS integrity, Gantt event state classification, Gantt block rendering, Gantt legend context, Gantt CSS integrity.

## Key Patterns

- **Confirmation modals:** All destructive actions use `confirmDelete(form, msg)` or `showConfirmModal(msg, callback)` — no browser `confirm()`. Defined in `base.html`.
- **Pending filter:** Client-side CSS toggle (`.cal-hide-pending` class), no page reload. State synced to URL via `history.replaceState`.
- **Asset picker:** Custom JS pill-based picker in event form. Single track group, multi-select subtracks, multi-select vehicles/operators. Supports `?track=<id>` pre-selection from URL.
- **`json_script`:** Asset data passed to templates via Django's `json_script` tag (not `mark_safe`).
- **`?next=` redirects:** All event actions (create, edit, approve, unapprove, delete) respect `?next=` parameter for return-to-previous-view. Validated with `url_has_allowed_host_and_scheme`.
- **Dashboard:** Tracks-only view (timeline merged into calendar day view). Events are clickable → edit view. Subtrack headers match parent track style. Actual time stamping (Start/End) on dashboard only. Radio channel dropdowns use `data-empty` attribute for green highlight when non-default. `_serialize_event` helper centralizes event serialization; multi-subtrack events promoted to parent track level. Segment edit popup has "Done" button alongside "Now", Enter key saves, and inline error display (no toasts). Stamp API and segment edit API reject future times.
- **Calendar day view:** Default view. Six event states with distinct visual treatments:
  - **Scheduled** — solid bar in track color (upcoming approved, no segments)
  - **Active** — ghost bar (opacity 0.4) + solid segment with pulsing right-edge glow
  - **Paused** — ghost bar + solid segments with diagonal-striped gaps between them; trailing pause gap pulses and grows live via JS from last segment end to current time (opacity 0.45)
  - **Completed** — faded (opacity 0.55, desaturated) ghost bar + solid segment
  - **No-show** — dashed amber border, subtle amber tint fill, dark amber text (past, never stamped)
  - **Pending** — 12% track-color tinted fill with solid track-color border, bold colored text
  Events with segments use a separate `.gantt-block-text` overlay (z-index 5) so text stays readable above segments regardless of opacity stacking contexts. Text shadow on all Gantt blocks and overlays for readability on faded/semi-transparent backgrounds. "Now" red line. Sticky collapsible "Key" legend at bottom-left (state persisted to localStorage). Rich hover tooltips on all event blocks (scheduled bar, segments, pause gaps) showing title, status badge, creator, scheduled time, tracks/vehicles, actual segments with durations, pause time, and description. Connector lines link disconnected scheduled bars and segments (solid for early starts, dashed for late starts). Scheduled boundary markers (white edge lines) appear when segments visually cover those edges; segment start markers (white left-edge line) on actual/active segments. Full-track events render in a dedicated "All" parent lane above subtracks (not as an overlay spanning subtracks). `_assign_rows` uses visual extent (scheduled + actual segments) to prevent overlapping events; subtrack rows expand height when events need stacking.
- **Track color palette:** 16 Tailwind colors, all WCAG AA compliant (≥4.5:1 contrast ratio with white text at 12px). Warm/green/cyan hues use -700 shades; cool hues use -600. Auto-assigned on track creation; manually overridable via asset form.
- **Duration shortcuts:** Event form has quick-select buttons (30m, 1h, 1.5h, 2h, 3h, 4h) + custom duration display.

## Seed Data

Fixture at `cal/fixtures/seed.json` contains 31 assets (7 parent tracks + 11 subtracks + 13 vehicles) and 2 users (admin, kolter). `setup_testdb` command loads this fixture and generates realistic events.

## gstack

Use `/browse` for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

## Out of Scope

Vehicle maintenance, notification/calendar syncing, Jira integration, recurring reservations. See `TODOS.md` for v2 priorities.
