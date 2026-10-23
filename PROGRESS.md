# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-24 11:15 AEDT by Arpon

## Status

**Phase 1 complete. Nothing from Phase 2 onward is started.** Two pieces of working
code exist: `scripts/preflight.py` and `app/config.py`. There is no agent, no data
pipeline, no engine, no UI.

| Area | State |
|---|---|
| Preflight (`make preflight`) | working — **22 pass / 0 fail on Arpon's machine, 23 Oct** (his services only; stale since he shut them down) |
| Config layer (`app/config.py`) | working — validated, secrets as `SecretStr` |
| Secret scan + pre-commit hook | working, verified to block a commit |
| Tests | **52 green** on any machine — isolated from any local `.env`, no services needed |
| Team workflow, CI, onboarding | working |
| Per-machine vs shared facts | separated — `CLAUDE.md` is team-wide only; see `docs/ENVIRONMENTS.md` |
| Zetaris adapter | **stub** — unblocked; response envelope recorded from Arpon's instance in `tests/fixtures/zetaris/` |
| Meterless adapter | **stub** — unblocked; contract fully known |
| Agents, orchestrator, tracing | not started |
| H-MEM, World Model | not started |
| Data pipeline, `datasvc` | not started |
| Web UI, Docker run path | not started — the Dockerfile has never been built |

## Observed on Arpon's machine, 23 Oct 2026

**One machine, one day.** These are not team-wide facts — nobody else has run the
services yet (see `docs/ENVIRONMENTS.md`), and Arpon's were shut down after this run,
so even his are stale. **Run `make preflight` on your own machine** rather than
trusting the list below. API behaviour that holds everywhere is in `CLAUDE.md`.

- **Zetaris** answering on `localhost:8888`. `SELECT 1` → `1`. Response envelope is
  `{headers, data, total, timeUsed}`; **every value arrives as a string**.
  Catalogue discovery needs `SHOW LIGHTNING DATABASES` + `SHOW TABLES IN <db>` —
  `SHOW DATASOURCES` returns 0 rows.
- **Nightshift** `online`. A request on `meterless/auto` was answered by
  `nvidia/nemotron-3.5-super-vl-120b-a12b`, returning a plain string.
- **Lane pinning was not honoured** on Arpon's runtime (build `m1-m4`): it raced six
  lanes under a learned router. Lane names and routing are per-machine configuration. Record `routed_model`, never `provider_model`. See `docs/DECISIONS.md`.

## Blocked on

**Pick the track.** Everything in Phase 2+ is shaped by it, and the domain pack cannot
be written without it. Candidates and the engines each emphasises are in `TODO.md`.

## Next up

1. **Decide the track** (team decision, blocks everything).
2. Then, in parallel and independent of each other:
   - `app/adapters/meterless.py` — contract fully known, see `TODO.md` Phase 2.
   - `app/adapters/zetaris.py` — parse `headers`+`data`, cast strings, read-only guard.
3. Then the Phase 3 spike: can the Zetaris containers reach `host.docker.internal:8100`?

Roles are **not assigned**. Claim an item in your handoff entry before starting it so
two people don't build the same adapter.
