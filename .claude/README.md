# .claude/ — Claude Code Project Config

Shared configuration for Claude Code sessions in this repo.

## What's here

| File | Purpose |
|---|---|
| `settings.json` | Shared hooks and permissions (tracked) |
| `docs/domain-glossary.md` | ASI-specific vocabulary (tracked) |
| `hooks/log-edits.sh` | Logs edited files for review (tracked) |
| `rules/` | Path-scoped UI pattern docs, loaded automatically when editing relevant files (tracked) |

## Personal overrides

To customize Claude Code for your own workflow without affecting others:

- **`settings.local.json`** — personal permission overrides (gitignored, auto-created by Claude Code when you approve tool use)
- **`retro.md`** — personal session log of decisions and lessons (gitignored)

These files are in `.gitignore` and will not be committed.
