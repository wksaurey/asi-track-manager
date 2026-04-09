---
globs: cal/templates/cal/calendar.html, cal/utils.py, cal/static/cal/css/styles.css
---

# Gantt Day View Patterns

Default calendar view. Six event states with distinct visual treatments:

- **Scheduled** — solid bar in track color (upcoming approved, no segments)
- **Active** — ghost bar (opacity 0.4) + solid segment with pulsing right-edge glow
- **Paused** — ghost bar + solid segments with diagonal-striped gaps between them; trailing pause gap pulses and grows live via JS from last segment end to current time (opacity 0.45)
- **Completed** — faded (opacity 0.55, desaturated) ghost bar + solid segment
- **No-show** — dashed amber border, subtle amber tint fill, dark amber text (past, never stamped)
- **Pending** — 12% track-color tinted fill with solid track-color border, bold colored text

Events with segments use a separate `.gantt-block-text` overlay (z-index 5) so text stays readable above segments regardless of opacity stacking contexts. Text shadow on all Gantt blocks and overlays for readability on faded/semi-transparent backgrounds.

"Now" red line. Sticky collapsible "Key" legend at bottom-left (state persisted to localStorage).

Rich hover tooltips on all event blocks (scheduled bar, segments, pause gaps) showing title, status badge, creator, scheduled time, tracks/vehicles, actual segments with durations, pause time, and description.

Connector lines link disconnected scheduled bars and segments (solid for early starts, dashed for late starts). Scheduled boundary markers (white edge lines) appear when segments visually cover those edges; segment start markers (white left-edge line) on actual/active segments.

Full-track events render in a dedicated "All" parent lane above subtracks (not as an overlay spanning subtracks). `_assign_rows` uses visual extent (scheduled + actual segments) to prevent overlapping events; subtrack rows expand height when events need stacking.

**Track color palette:** 16 Tailwind colors, all WCAG AA compliant (≥4.5:1 contrast ratio with white text at 12px). Warm/green/cyan hues use -700 shades; cool hues use -600. Auto-assigned on track creation; manually overridable via asset form.
