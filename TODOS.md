# TODOS

## Pre-Deploy (Blockers)

- [ ] Import real ASI asset data from the current spreadsheet (tracks, vehicles, operators)
  - **Why:** The tool needs real data for adoption — employees must see *their* tracks and vehicles
  - **Context:** Kolter has the spreadsheet. Seed via Django management command or admin interface
  - **Depends on:** Getting the spreadsheet from Kolter

## UI Polish

- [ ] Clarify "inactive" track behavior and visibility
  - **Why:** Inactive tracks are still selectable for event creation and visible on calendar/dashboard. Unclear if that's intended. Browser tester flagged it as confusing
  - **Context:** `is_active` is doing double duty — "track is live/hot right now" (dashboard) and "available for scheduling" (detail page). These should probably be separate fields (e.g., `is_active` for live state, `is_schedulable` for booking availability). Kolter wants high visibility — users should see what others are scheduling. Get stakeholder feedback (Josh, Lee, Andrew, Hollis) on whether inactive tracks should be hidden, grayed out, or left as-is
  - **Depends on:** Stakeholder feedback

- [ ] Lock down usernames and authentication (Hollis)
  - **Why:** Current signup allows any username — people enter jokes ("brain" instead of "brian"). Need real identity for accountability
  - **Context:** Hollis has a plan for this. Options include: requiring full names, email-based accounts, or SSO with work emails. Check in with Hollis on status and approach
  - **Depends on:** Hollis's plan

- [ ] Clean up user roles and permissions
  - **Why:** "Superuser" is a Django-level role, "Admin"/"Staff" are app-level. The navbar shows "Admin" for both, and user management mixes the terminology. Confusing for users
  - **Context:** Align app permission checks with Django's role model. Decide which roles actually matter (Superuser/Admin/Staff/User), make them consistent in UI and code
  - **Depends on:** None

- [ ] Navbar layout breaks around 908px viewport width
  - **Why:** Title wraps awkwardly and nav items get cramped before hamburger menu kicks in. Rough transition between desktop (768px) and full-width breakpoints
  - **Context:** Likely needs a `@media` tweak or adjusting when the hamburger triggers
  - **Depends on:** None

## Bugs

- [ ] Pause gap not shown while actively paused
  - **Why:** The diagonal-striped pause gap between segments only renders once a new segment starts. While an event is actively paused (segment ended, no new segment yet), there's no visual indicator of the growing pause period
  - **Context:** Pause gap is computed as space between two segments (current end → next start). With no "next segment" during active pause, nothing renders. Fix needs server-side detection of "actively paused" state in `cal/utils.py` plus client-side JS to live-grow the gap like active segments do
  - **Depends on:** None

## Testing

- [ ] Add negative/error tests to production smoke test
  - **Why:** Current smoke test only checks happy paths. Missing: form validation errors, 404 on bad event IDs, unauthenticated API access. These surface unhandled 500s
  - **Context:** Add 2-3 quick tests to `deployment/PROD_SMOKE_TEST.md`
  - **Depends on:** None

- [ ] Add Analytics page test to smoke test
  - **Why:** Test 9 checks the analytics API but not the `/cal/analytics/` page itself
  - **Context:** Quick addition to `deployment/PROD_SMOKE_TEST.md`
  - **Depends on:** None

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

- [ ] Waitress threading constraint (document prominently)
  - **Why:** SQLite + multiple processes = silent data corruption. Currently safe with `--threads 4` (single process), but this constraint is easy to forget
  - **Context:** Waitress runs with `--threads 4` (no `--workers`). Documented in DEPLOYMENT.md but should be more visible — add a warning banner or comment in settings.py. Do not increase to multiple processes until PostgreSQL migration
  - **Depends on:** PostgreSQL migration removes this constraint

## Completed

- [x] Create subtracks within track assets
- [x] Make month view fixed with scrollable day cells
- [x] Update project documentation
- [x] Remove password restrictions
- [x] Copy timeline style from dashboard project
- [x] Combine control dashboard with scheduler app
- [x] User management — admin can promote/demote users (toggle_admin + delete_user views)
