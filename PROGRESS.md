# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-24 09:30 AEDT by Arpon

## Status

**Phase 1 complete. Nothing from Phase 2 onward is started.** Two pieces of working
code exist: `scripts/preflight.py` and `app/config.py`. There is no agent, no data
pipeline, no engine, no UI.

| Area | State |
|---|---|
| Preflight (`make preflight`) | working — **22 pass / 0 fail** against live services |
| Config layer (`app/config.py`) | working — validated, secrets as `SecretStr` |
| Secret scan + pre-commit hook | working, verified to block a commit |
| Tests | **52 green**, isolated from any local `.env` |
| Team workflow, CI, onboarding | working (this change) |
| Zetaris adapter | **stub** — unblocked; response envelope recorded in `tests/fixtures/zetaris/` |
| Meterless adapter | **stub** — unblocked; contract fully known |
| Agents, orchestrator, tracing | not started |
| H-MEM, World Model | not started |
| Data pipeline, `datasvc` | not started |
| Web UI, Docker run path | not started — the Dockerfile has never been built |

## Verified against live services (2026-10-23)

- **Zetaris** answering on `localhost:8888`. `SELECT 1` → `1`. Response envelope is
  `{headers, data, total, timeUsed}`; **every value arrives as a string**.
  Catalogue discovery needs `SHOW LIGHTNING DATABASES` + `SHOW TABLES IN <db>` —
  `SHOW DATASOURCES` returns 0 rows.
- **Nightshift** `online`. A request on `meterless/auto` was answered by
  `nvidia/nemotron-3.5-super-vl-120b-a12b`, returning a plain string.
- **Lane pinning is not honoured** — the runtime races six lanes under a learned
  router. Record `routed_model`, never `provider_model`. See `docs/DECISIONS.md`.

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
