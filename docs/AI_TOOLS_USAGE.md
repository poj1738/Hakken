# AI coding tool usage log

**We build with Claude Code.** `CLAUDE.md` is the single source of our working rules —
there is no second rules file to keep in sync.

## On Cursor

The event's resources are inconsistent: the event page's rules read as "must use
Cursor", while other official resources call it optional. We are not using it. The repo
previously carried a `.cursor/rules/project.mdc` mirroring `CLAUDE.md`; it has been
removed, because a duplicated rules file drifts from the original and then quietly
misleads whoever reads the stale copy.

If a teammate does choose to work in Cursor, point it at `CLAUDE.md` directly rather
than reintroducing a mirror, and add a row below.

What the AI Usage Policy actually requires is that we **declare honestly which tools we
used**. That is what this log is for.

## The log

One row per working session. Fill it in as work happens; do not backfill guesses. If a
tool was never used, leave it out rather than listing it to look compliant.

| Date (AEDT) | Who | Tool | Model / mode | What was built |
|---|---|---|---|---|
| 2026-10-23 | Arpon | Claude Code | Opus 5 | Phase 0 reference review and preflight; Phase 1 skeleton, config layer, secret scan |
| 2026-10-24 | Arpon | Claude Code | Opus 5 | Team workflow: handoff log, session-start hook, CI, onboarding docs |
| 2026-10-24 | Arpon | Claude Code | Opus 5 | MedTrace domain-pack skeleton: frozen `types.py`, SQL templates, trust priors, contract tests |
| 2026-10-24 | Arpon | Claude Code | Opus 5 | Live SQL dialect testing (found the `''` escaping bug), step-1 reachability spike, latency correction |

The README's **AI and model usage** section summarises this for judges.
