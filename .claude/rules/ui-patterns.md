---
globs: cal/templates/**
---

# UI Patterns

- **Confirmation modals:** All destructive actions use `confirmDelete(form, msg)` or `showConfirmModal(msg, callback)` — no browser `confirm()`. Defined in `base.html`.
- **Pending filter:** Client-side CSS toggle (`.cal-hide-pending` class), no page reload. State synced to URL via `history.replaceState`.
- **Asset picker:** Custom JS pill-based picker in event form. Single track group, multi-select subtracks, multi-select vehicles/operators. Supports `?track=<id>` pre-selection from URL.
- **`json_script`:** Asset data passed to templates via Django's `json_script` tag (not `mark_safe`).
- **`?next=` redirects:** All event actions (create, edit, approve, unapprove, delete) respect `?next=` parameter for return-to-previous-view. Validated with `url_has_allowed_host_and_scheme`.
- **Mass approve:** Bulk approve pending events with conflict detection. Events with conflicts are skipped (not approved-then-skipped). Conflict annotations with links to conflicting events.
- **Mobile responsive:** 768px/480px breakpoints, hamburger nav with backdrop, collapsible Gantt track labels (toggle button, persisted to localStorage), legend wrapping, stacked asset cards, pending event button stacking, user management column hiding, compact dashboard headers.
- **Duration shortcuts:** Event form has quick-select buttons (30m, 1h, 1.5h, 2h, 3h, 4h) + custom duration display.
- **Event page segments:** Admin-editable segment table with time-only Flatpickr pickers, duration display, IMPROMPTU/STOPPED badges.
- **Konami easter egg:** Hidden feature triggered by Konami code input.
