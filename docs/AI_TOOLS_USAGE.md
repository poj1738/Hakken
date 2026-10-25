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
| 2026-10-24 | Arpon | Claude Code | Opus 5 | Steps 2/4/5/6: PBS fetch + hand-built lexicon, synthetic generator, datasvc, Zetaris registration (dry run) |
| 2026-10-24 | Arpon | Claude Code | Opus 5 | Zetaris registration applied live + verified; step 7 began: `parse.py` and `safety.py` |
| 2026-10-24 | Arpon | Claude Code | Opus 5 | Step 7: `identity.py` (0 false merges) and `normalise.py`; research briefs for an outside consultant |
| 2026-10-25 | Arpon | Claude Code | Opus 5 | Applied consultant briefs 6-10: real PBS pack sizes in the generator, TGA field mapping, brief 8 suppression rules, vetted pitch claims; fixed two silent-staleness bugs in `datasvc` and the registration verifier |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | `fuse`, `detect`, `triage` and `scripts/eval.py` (detector scorecard against ground truth); 11 defects fixed across the generator, `normalise`, `coverage` and `identity`; consultant briefs 11-14 |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Applied consultant briefs 11-14 to the detector; population to 200; identity fix for combined names; schema review for Arnav (#12) |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Loose ends: `coverage` staleness off the wall clock, core vs extended high-risk recall in the scorecard, stale PROGRESS decisions struck |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Demo data: staged learning-demo pair with CI test, showcase replay fixtures, five `input_examples/`, replay set in the Docker image |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Recorded Track 1 across metadata, README, TODO and PROGRESS; README status rewritten to match the code |
| 2026-10-25 | Anshu | Claude Code (cloud session) | Opus 5.5 | Web UI in `web/`: all ten PLAN §6 items in mock mode against `tests/fixtures/api/`, checked with Playwright screenshots |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Q4 shortages query (gated on licence), scorecard JSON and dashboard, data-licence audit (PBS copyright notices), fresh-clone audit via a subagent |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | Applied the fresh-clone audit: reproducible data build checked in CI, honest make targets, README/metadata/Docker fixes |
| 2026-10-25 | Arpon | Claude Code | Opus 5.5 | TGA cleared and Q4 switched on (registration left to Arpon); identity evidence verdict prefix for the UI |
| 2026-10-25 | Arpon | Claude Code (multi-agent workflow) | Opus 5.5 | Codebase scan: 7 reviewers, 2 skeptics per finding, 34 verified items; Docker web-stage fix; handover to Arnav |
| 2026-10-25 | Anshu | Claude Code (cloud session) | Opus 5.5 | UI review item by item against PLAN §6, with fixes; followed schema #23 and identity verdict prefixes #24; checked with Playwright |

The README's **AI and model usage** section summarises this for judges.
