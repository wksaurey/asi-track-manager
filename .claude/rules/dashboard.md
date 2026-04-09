---
globs: cal/templates/cal/dashboard.html, cal/views.py
---

# Dashboard Patterns

Tracks-only view (timeline merged into calendar day view). Events are clickable → edit view. Subtrack headers match parent track style.

Actual time stamping (Start/End) on dashboard only. Radio channel dropdowns use `data-empty` attribute for green highlight when non-default.

`_serialize_event` helper centralizes event serialization; multi-subtrack events promoted to parent track level.

Segment edit popup has "Done" button alongside "Now", Enter key saves, and inline error display (no toasts). Stamp API and segment edit API reject future times.

Impromptu event creation via "+" button (opens segment immediately, with active event blocking confirmation).
