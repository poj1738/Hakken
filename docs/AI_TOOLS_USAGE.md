# AI coding tool usage log

**Cursor is optional for us.** The event's resource docs are inconsistent — the event
page's rules read as "must use Cursor", while other official resources call it
optional — so we keep the repo Cursor-ready (`.cursor/rules/project.mdc` mirrors
`CLAUDE.md`) without being tied to it. Any AI coding tool is fine: Cursor, Claude Code,
Copilot, Windsurf, Codex, or none.

What the AI Usage Policy actually requires is that we **declare honestly which tools we
used**. That is the point of this log. Fill in one row per session as work happens, and
do not backfill guesses. If a tool was never used, leave it out rather than listing it
to look compliant.

| Date (AEDT) | Who | Tool | Model / mode | What was built |
|---|---|---|---|---|
| 2026-10-23 | Arpon | Claude Code | Opus 5 | Phase 0 reference review and preflight; Phase 1 skeleton, config layer, secret scan |

The README's **AI and model usage** section summarises this for judges.

## Note on the `.cursor/` directory

`.cursor/rules/project.mdc` is generated from `CLAUDE.md` so both tools get identical
working rules. If you edit the rules, edit `CLAUDE.md` and re-mirror it; do not let the
two drift.
