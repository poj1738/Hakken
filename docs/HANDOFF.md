# Handoff log

**Append-only. Newest first.** Add an entry at the end of every working session, above
the previous one. Never edit or delete someone else's entry — if something was wrong,
say so in a new entry.

Why it exists: three people on a five-day deadline, working at different hours. The
only way the next person starts from where you left off instead of rediscovering it is
if you write down what broke and what you need.

Copy this template:

```markdown
### YYYY-MM-DD HH:MM AEDT · <name> · <branch>

**Did:**
**Changed shared files:**
**Broken:**
**Needs from teammates:**
**Next:**
```

Fill every field, including the awkward ones. "Broken: nothing" is a useful sentence.
**Changed shared files** means anything a teammate will hit a conflict on or silently
depend on: `app/schemas.py`, `app/config.py`, `.env.example`, `CLAUDE.md`,
`requirements.txt`, `Makefile`, CI. If you changed one, say so here *and* in the PR.

---

### 2026-10-24 09:30 AEDT · Arpon · arpon/team-workflow

**Did:** Set up the team workflow, no features. Removed `.cursor/` and every reference
to it, so `CLAUDE.md` is now the single source of rules (a mirrored rules file drifts
and then misleads). Added this handoff log, `PROGRESS.md`, a SessionStart hook that
orients you automatically, GitHub Actions CI, and `docs/ONBOARDING.md`. Merged the
Cursor note into `docs/AI_TOOLS_USAGE.md`.

**Changed shared files:** `CLAUDE.md` (new "Team workflow" section; rule 4 rewritten
for Claude Code), `metadata.json` (`cursor.used: false`), `README.md`,
`docs/SPONSOR_TECH.md`, `docs/AI_TOOLS_USAGE.md`. New: `.claude/settings.json`,
`scripts/session_start.sh`, `.github/workflows/ci.yml`, `PROGRESS.md`,
`docs/HANDOFF.md`, `docs/ONBOARDING.md`. Deleted: `.cursor/`.

**Broken:** Nothing. 52 tests green, secret scan clean. Two caveats: `gh` is not
installed on this machine, so the PR could not be opened from the terminal and the
session-start hook skips its PR section gracefully. CI has not run before this push, so
its first run on this branch is also its first real test.

**Needs from teammates:** Roles are not assigned — nothing here allocates work. Each
person needs their own Zetaris API key and Nightshift Runtime token in their own local
`.env`; see `docs/ONBOARDING.md`. Nobody shares credentials.

**Next:** The blocking decision is still **which track** — see `TODO.md`. Both Phase 2
adapters are unblocked and contract-complete the moment that lands.
