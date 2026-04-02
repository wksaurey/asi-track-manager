# TODOS

## Pre-Deploy (Blockers)

- [ ] Import real ASI asset data from the current spreadsheet (tracks, vehicles, operators)
  - **Why:** The tool needs real data for adoption — employees must see *their* tracks and vehicles
  - **Context:** Kolter has the spreadsheet. Seed via Django management command or admin interface
  - **Depends on:** Getting the spreadsheet from Kolter

## V2 Priorities

- [ ] Admin setting: block impromptu event creation when an active/approved event exists on the same track
  - **Why:** Safety procedure — prevents accidental overlap on active tracks. Currently uses a confirmation popup instead of a hard block
  - **Context:** Add a site-wide or per-track admin toggle. When enabled, the dashboard "mark active" flow should refuse to create an impromptu event if a conflicting active/approved event exists, instead of just warning
  - **Depends on:** v1.1 impromptu event + active track features

- [ ] PostgreSQL migration
  - **Why:** SQLite doesn't support concurrent writes from multiple processes. Currently pinned to 1 Gunicorn worker as a workaround. Also enables proper ORM aggregation for analytics
  - **Trigger:** If >1 Gunicorn worker needed, or "database is locked" errors appear, or when adding dashboard auto-refresh polling
  - **Context:** Add PostgreSQL to docker-compose.yml, update settings.py DATABASE config, migrate data
  - **Depends on:** Initial deployment to VM

- [ ] Gunicorn worker constraint (document)
  - **Why:** SQLite + multiple workers = silent data corruption
  - **Context:** Currently pinned to `--workers 1 --threads 4` in Dockerfile. This constraint must be documented and visible until PostgreSQL migration
  - **Depends on:** PostgreSQL migration removes this constraint

## Completed

- [x] Create subtracks within track assets
- [x] Make month view fixed with scrollable day cells
- [x] Update project documentation
- [x] Remove password restrictions
- [x] Copy timeline style from dashboard project
- [x] Combine control dashboard with scheduler app
- [x] User management — admin can promote/demote users (toggle_admin + delete_user views)
