# Todo

Shared task list for Kolter and Hollis. New ideas go in **Unapproved** with an author tag. Discuss in person, then move approved items to **Approved** with an assignee. Tags: `[kolter]`, `[hollis]`, `[unassigned]`. Every item gets **Why** and **Context** fields.

## Approved

_(None yet — triage Unapproved items together to populate this section.)_

## Unapproved

- [kolter] Sort dashboard track event lists by newest first
  - **Why:** Events under each track on the dashboard aren't sorted by recency -- harder to find the most relevant event at a glance
  - **Context:** Dashboard API serializes events per track. Need to handle impromptu events (null start_time) when sorting

- [unassigned] Import real ASI asset data from the current spreadsheet (tracks, vehicles, operators)
  - **Why:** The tool needs real data for adoption — employees must see *their* tracks and vehicles
  - **Context:** Kolter has the spreadsheet. Seed via Django management command or admin interface. Blocked until spreadsheet is obtained

- [unassigned] Dashboard scroll jumps to top when stamping events lower on the page
  - **Why:** Starting/stopping/pausing an event resets scroll position to page top. User has to scroll back down to continue working
  - **Context:** Likely the stamp API response triggers a re-render or page reload that loses scroll position. Fix should preserve scroll position across state changes

- [unassigned] Clarify "inactive" track behavior and visibility
  - **Why:** Inactive tracks are still selectable for event creation and visible on calendar/dashboard. Browser tester flagged it as confusing
  - **Context:** `is_active` is doing double duty — "track is live/hot right now" (dashboard) and "available for scheduling" (detail page). These should probably be separate fields (e.g., `is_active` for live state, `is_schedulable` for booking availability). Kolter wants high visibility — users should see what others are scheduling. Get stakeholder feedback (Josh, Lee, Andrew, Hollis) on whether inactive tracks should be hidden, grayed out, or left as-is

- [unassigned] Lock down usernames and authentication
  - **Why:** Current signup allows any username — people enter jokes ("brain" instead of "brian"). Need real identity for accountability
  - **Context:** Hollis has a plan for this. Options include: requiring full names, email-based accounts, or SSO with work emails. Check in with Hollis on status and approach

- [unassigned] Clean up user roles and permissions
  - **Why:** "Superuser" is a Django-level role, "Admin"/"Staff" are app-level. The navbar shows "Admin" for both, and user management mixes the terminology. Confusing for users
  - **Context:** Align app permission checks with Django's role model. Decide which roles actually matter (Superuser/Admin/Staff/User), make them consistent in UI and code

- [unassigned] Navbar layout breaks around 908px viewport width
  - **Why:** Title wraps awkwardly and nav items get cramped before hamburger menu kicks in. Rough transition between desktop (768px) and full-width breakpoints
  - **Context:** Likely needs a `@media` tweak or adjusting when the hamburger triggers

- [unassigned] Add negative/error tests to production smoke test
  - **Why:** Current smoke test only checks happy paths. Missing: form validation errors, 404 on bad event IDs, unauthenticated API access. These surface unhandled 500s
  - **Context:** Add 2-3 quick tests to `deployment/POST_DEPLOY.md`

- [unassigned] Add Analytics page test to smoke test
  - **Why:** Test 9 checks the analytics API but not the `/cal/analytics/` page itself
  - **Context:** Quick addition to `deployment/POST_DEPLOY.md`

- [unassigned] Consolidate `set_radio_channel` and `set_event_radio_channel` views
  - **Why:** Nearly identical views (`set_radio_channel` and `set_event_radio_channel`). DRY violation
  - **Context:** Straightforward merge — pick one view, parameterize the difference

- [unassigned] Audit legacy stamp actions (`clear_start`/`clear_end`)
  - **Why:** `clear_start`/`clear_end` views still exist with tests, but may be dead code in the UI (replaced by segment-based stamping)
  - **Context:** Check if any template or JS references these endpoints. If dead, remove views and tests

- [unassigned] Clean up `analytics_api` redundant querysets
  - **Why:** Multiple querysets that could be consolidated
  - **Context:** Review `analytics_api` view for duplicate or overlapping queries

- [unassigned] How should CLAUDE.md work in a multi-developer repo?
  - **Why:** CLAUDE.md is checked into the repo, which means it enforces one person's AI workflow preferences on all contributors. Could create friction as team grows
  - **Context:** Should CLAUDE.md contain only project facts (architecture, models, APIs) and leave workflow/style preferences to each dev's `~/.claude/` config? Discuss with Hollis

- [unassigned] Rename project from "ASI Track Manager" to "Verification and Validation Schedule (V&V Scheduler)"
  - **Why:** Repo already renamed at the org level. Local rename still needed
  - **Context:** See below for full breakdown. Blocked on deciding the Python module name and display name
  - **Functional changes (will break things if skipped):**
    - Rename `asi_track_manager/` directory to new module name (e.g. `vv_scheduler`)
    - Update `manage.py`, `settings.py` (ROOT_URLCONF, WSGI_APPLICATION), `wsgi.py`, `asgi.py`, `urls.py` to reference new module
    - Update nav brand in `templates/base.html:26` and title in `users/templates/users/management.html:4`
    - Update `cal/tests.py` assertContains checks (lines ~416, ~424) that assert "ASI Track Manager"
    - Fix `templates/base.html:17` default `<title>` (currently says "ASI Asset Scheduler" — already inconsistent)
  - **Cosmetic changes (comments, docs):**
    - Docstrings in `cal/decorators.py`, `models.py`, `helpers.py`, `views.py`, `tests_v11.py`, `styles.css`
    - Docs: `README.md`, `CLAUDE.md`, `deployment/DEPLOYMENT.md`, `deployment/env.example`, `deployment/POST_DEPLOY.md`
    - `.claude/retro.md` heading
  - **No change needed:**
    - App names (`cal`, `users`) — generic, no branding
    - Database tables — named after app labels, not the project
    - Migrations — no project name embedded
  - **Post-rename:**
    - Rename local folder (`asi-track-manager` → TBD)
    - Update git remote URL to new org repo
    - Copy `.claude/projects/-home-kolter-asi-blitz-asi-track-manager/` memory to new path-scoped project folder
    - Update deployment paths on server (`C:\apps\asi-track-manager\`, Task Scheduler, firewall rule, backup script)

- [unassigned] Require status checks to pass before merge
  - **Why:** PRs can merge without CI passing — no automated safety net
  - **Context:** Add to repo ruleset once CI is set up

- [unassigned] Restrict commit metadata — enforce conventional commit regex on subject line
  - **Why:** Keeps commit history consistent and parseable as team grows
  - **Context:** Enable when team grows past 2-3 devs. Draft regex: `^(feat|fix|docs|chore|refactor|test|ci|style|perf|build|revert)(\(.+\))?!?:` — validate subject line only, not full message body

- [unassigned] Restrict branch names — enforce `<name>/<description>` pattern
  - **Why:** Keeps branch naming consistent as team grows
  - **Context:** Enable when team grows past 2-3 devs. Draft regex needs tuning for dots, numbers, caps in real branch names

- [unassigned] Admin setting: block impromptu event creation when an active/approved event exists on the same track
  - **Why:** Safety procedure — prevents accidental overlap on active tracks. Currently uses a confirmation popup instead of a hard block
  - **Context:** Add a site-wide or per-track admin toggle. When enabled, the dashboard "mark active" flow should refuse to create an impromptu event if a conflicting active/approved event exists, instead of just warning. Builds on v1.1 impromptu event + active track features

- [unassigned] PostgreSQL migration
  - **Why:** SQLite doesn't support concurrent writes from multiple processes. Currently pinned to 1 Waitress process as a workaround. Also enables proper ORM aggregation for analytics
  - **Context:** Update settings.py DATABASE config, migrate data. Trigger: if more Waitress workers needed, "database is locked" errors appear, or when adding dashboard auto-refresh polling. Blocked until deployed to VM

- [unassigned] Waitress threading constraint (document prominently)
  - **Why:** SQLite + multiple processes = silent data corruption. Currently safe with `--threads 4` (single process), but this constraint is easy to forget
  - **Context:** Waitress runs with `--threads 4` (no `--workers`). Documented in DEPLOYMENT.md but should be more visible — add a warning banner or comment in settings.py. Blocked until PostgreSQL migration removes this constraint
