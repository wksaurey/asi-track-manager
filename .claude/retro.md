# Retro — ASI Track Manager

## 2026-04-03 — Trunk-based flow over GitFlow [decision]
**Context:** Git audit revealed diverged branches, duplicate commits, mega-PRs from dev-to-main batching.
**Decision:** Drop `dev` branch, merge features directly to `main`.
**Rationale:** Simpler, forces small PRs, keeps `main` current. Two-person team doesn't need a staging branch.
**Caveats:** Requires discipline to keep feature branches short-lived. Both contributors need to rebase from `main` frequently.

## 2026-04-03 — Skills at user level, not project level [decision]
**Context:** `/commit` and `/git-check` skills were initially project-scoped. Realized they're generic.
**Decision:** Moved to `~/.claude/skills/`, made test command discovery dynamic (reads from project CLAUDE.md).
**Rationale:** Reusable across all projects without duplication.
**Caveats:** Project-specific test commands must be documented in each project's CLAUDE.md or the skill won't find them.

## 2026-04-03 — Cherry-pick over merge for Hollis integration [decision]
**Context:** `git merge origin/dev` produced 50+ conflicts across every core file. Branches diverged at the data model (segments vs flat fields).
**Decision:** Cherry-pick individual features from origin/dev into v1.1, adapting each to the segment model.
**Rationale:** Mechanical merge would produce a Frankenstein codebase. Cherry-pick lets us keep v1.1's architecture and selectively integrate Hollis's UI/features.
**Caveats:** Some Hollis features needed rewriting (impromptu events, dashboard API). More work upfront, but cleaner result.

## 2026-04-03 — Segment model over flat actual_start/actual_end [decision]
**Context:** Hollis used flat fields; v1.1 uses ActualTimeSegment model.
**Decision:** Keep v1.1's segment model for all merged code. Rewrite Hollis's impromptu events to create segments.
**Rationale:** Play/pause/stop requires multiple time ranges per event. Flat fields can't represent paused state.
**Caveats:** All Hollis code touching actual times needed adaptation.

## 2026-04-03 — Separate date/time form fields over combined datetime [decision]
**Context:** Three visible Flatpickr inputs synced into two hidden Django fields via JS — fragile sync bugs.
**Decision:** Use three real Django form fields (event_date, start_time_only, end_time_only) combined server-side in clean().
**Rationale:** Single source of truth per field. No JS sync function needed. Testable and deterministic.
**Caveats:** Existing tests needed updating to use new field names.

## 2026-04-03 — Single-day events only [decision]
**Context:** Stale segments from previous days blocked new impromptu events. Multi-day events cause complexity.
**Decision:** Events cannot span midnight. Added form validation. Stale segments auto-close at 23:59:59.
**Rationale:** Simplifies the time model. Multi-day use case can be solved with event series in the future.
**Caveats:** If someone needs a true overnight test, they'd need two events.

## 2026-04-03 — Mass approve skips ALL conflicting events [decision]
**Context:** First implementation approved in DB order (first one wins). User wanted fairness.
**Decision:** Two-pass approach: identify all conflicts (including within the batch), then only approve clean events.
**Rationale:** Prevents arbitrary ordering from deciding which event wins. Forces manual resolution of conflicts.
**Caveats:** If two pending events conflict with each other, neither is approved even if one has no other conflicts.

## 2026-04-03 — Radio channels expanded to 1-16 [decision]
**Context:** v1.1 used 11-16; Hollis used 1-16. Business decision needed.
**Decision:** Expand to 1-16 per user request ("we will fix our radios eventually").
**Rationale:** Future-proofing. Existing values (11-16) remain valid.
**Caveats:** Migration 0022 changes field choices only (no data migration needed).

## 2026-04-03 — Impromptu events have null start_time/end_time [decision]
**Context:** Could give impromptu events fake times (now + 1hr) or null times.
**Decision:** Null times — impromptu events have no scheduled window.
**Rationale:** Distinguishes scheduled from impromptu in analytics. Fake times would pollute scheduling data.
**Caveats:** Every code path accessing start_time/end_time needs null guards.

## 2026-04-03 — Dev branch caused more problems than it solved [lesson]
GitFlow-style `dev` staging branch led to mega-PRs, stale `main`, and parallel long-lived branches with duplicated commits. Switching to trunk-based flow: feature branches off `main`, merge directly back.

## 2026-04-03 — CRLF normalization nukes git blame [lesson]
A single line-ending normalization commit touched 71 files and 16K+ lines, making `git blame` useless for those files. Always add `.gitattributes` at project start, not after the damage.

## 2026-04-03 — Kitchen-sink commits can't be reverted [lesson]
Commits bundling multiple features are un-revertable and un-bisectable. If the commit message needs commas, it should be multiple commits.

## 2026-04-03 — Worktree agents that don't commit lose everything [lesson]
Agents running in `isolation: "worktree"` that finish without committing have their worktree cleaned up automatically. All file changes are lost. Need to either have agents commit, or extract diffs before cleanup.

## 2026-04-03 — timezone.now().strftime() produces UTC, form expects local time [lesson]
Tests using `timezone.now().strftime('%H:%M')` submit UTC times to forms that interpret them in the app timezone. When UTC and local times cross midnight, "end before start" errors appear. Fix: use `localtime()` with fixed hours in tests.

## 2026-04-03 — Django templates don't support Python methods like .split [lesson]
`{% for ch in "1 2 3".split %}` crashes — Django template language doesn't support Python string methods. Use explicit HTML or pass lists from the view context.

## 2026-04-03 — CSS class names in inline style blocks match assertNotContains [lesson]
Tests like `assertNotContains(resp, 'conflict-badge')` fail when the class name exists in an inline `<style>` block even though no badge element renders. Test for the actual rendered element instead.

## 2026-04-03 — Stale open segments from previous days block new events [lesson]
Segments left open (end=None) from days ago appear "active" and block impromptu event creation. Added auto-close at 23:59:59 of the segment's start day when creating new impromptu events on the same track.

## 2026-04-08 — Nullable fields need null guards in every code path [lesson]
Migration 0021 made `start_time`/`end_time` nullable for impromptu events, but `formatdayview` sorts by `ev.start_time` in 6 places. Two impromptu events on the same track crashed with `TypeError: '<' not supported between NoneType`. The retro entry from 2026-04-03 already warned: "Every code path accessing start_time/end_time needs null guards." Test suite didn't catch it because no test put 2+ impromptu events on the same track. Added regression tests.

## 2026-04-14 — Rebase-only merge method over squash [decision]
**Context:** Branch protections discussion. Claude extension recommended squash-only to keep main clean.
**Decision:** Rebase-only. Squash and merge commits both disabled.
**Rationale:** /commit skill produces atomic, well-messaged commits. Squash throws all that away into one commit per PR. Rebase preserves individual commits AND keeps linear history (required by branch protection).
**Caveats:** If someone makes messy commits on a feature branch, they'll all land on main. Mitigated by PR review and the team's commit discipline.

## 2026-04-14 — GitHub is source of truth for branch protections [decision]
**Context:** Debated whether to document branch protection rules in README or project docs.
**Decision:** Let GitHub Settings > Rules be the documentation for what rules are active. Project docs (README) document the workflow — how devs should work. TODOS.md tracks what to enable next.
**Rationale:** Duplicating rules in project docs creates maintenance drift. Anyone with repo access can see the rules in GitHub. The README already covers the workflow implications.
**Caveats:** If a new dev can't access repo settings, they'll hit the protections naturally (push to main rejected → told to use a PR).

## 2026-04-14 — Defer regex-based branch protections for small teams [decision]
**Context:** Considered commit metadata regex (conventional prefixes) and branch name regex restrictions.
**Decision:** Skip both until team grows past 2-3 devs.
**Rationale:** Two people already follow the conventions. Bad regex blocks legitimate merges and is painful to debug. /commit skill enforces format on Claude's end. Enable when onboarding devs who haven't internalized conventions.
**Caveats:** Draft regexes saved in TODOS.md for when the time comes.
