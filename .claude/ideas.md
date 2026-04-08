# Ideas

Open questions and things to figure out later.

## CLAUDE.md ownership in a multi-developer repo

CLAUDE.md is checked into the repo, which means it enforces one person's AI workflow preferences on all contributors. If Hollis (or a future dev) uses Claude Code with different conventions, the shared CLAUDE.md could create friction.

**Questions to resolve:**
- Should CLAUDE.md contain only project facts (architecture, models, APIs) and leave workflow/style preferences to each dev's `~/.claude/` config?
- Should there be a `.claude/settings.json` policy — project-level for shared rules, personal overrides in `settings.local.json`?
- How do other multi-dev teams handle this? Research needed.

## Domain glossary → ASI context KB

`.claude/docs/domain-glossary.md` has ASI-specific vocabulary (ASAM, MMM, AOZ, Mobius, etc.) that Claude needs for this project. A curated ASI knowledge base is being built at `~/asi/blitz/blitz-qa/koltersaurey/asi-context/`. Once that KB is mature, the domain glossary should migrate there (possibly via git submodule) so all ASI projects share the same context rather than each maintaining their own copy.
