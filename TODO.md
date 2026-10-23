# TODO

Ordered by judging impact. Scoring /100: Impact 30, Technical 20, Innovation 15,
Demo 15, Product & UX 10, Sponsor tech 10.

## Blocked on someone else

- [ ] **Zetaris stack up** — Arpon runs `docker compose up -d` + `verify.sh`, creates an
      API key, puts it in `.env`, then tells us to re-run `make preflight`.
- [ ] Decide the **track**, then write the domain pack (§12 of the kickoff brief).

## Phase 2 — adapters (next)

- [ ] `app/adapters/meterless.py`: client, lane routing, receipt capture into traces,
      offline reasoner for SAMPLE_MODE. Unit-test status states and URL normalisation.
- [ ] `app/adapters/zetaris.py`: **inspect one real 200 response first** to find where
      column names live, then the parser, read-only SQL guard, schema discovery,
      retries, typed errors, fixture-backed sample mode.

## Phase 3 — data layer

- [ ] `scripts/generate_synthetic.py` — 3 seeded silos with deliberate inconsistencies.
- [ ] `datasvc/` serving each silo whole at one URL; `CACHE TABLE` after each register.
- [ ] `data/zetaris/NN_*_create.sql` + `_select.sql`; `scripts/register_sources.py`
      with `--dry-run` / `--skip-exists`, then verify row counts against the source.
- [ ] **Spike first:** prove Zetaris can reach `host.docker.internal:8100`. Fallbacks in
      order: datasvc on the Zetaris compose network → MinIO/Parquet → Postgres JDBC.

## Phase 4 — engines and agent loop

- [ ] H-MEM in Python + 13 ported conformance checks + a memory-carries-over feature test.
- [ ] World Model in Python + 8 ported conformance checks (merge band **0.85**).
- [ ] Orchestrator: bounded Planner/Executor/Evaluator/Writer with a critique→revise loop.
- [ ] `app/tracing.py`: JSONL per run, official fields + receipt, secret masking.

## Phase 5 — entry points, Docker, UI, Cursor

- [ ] `run.py --input` and `run.py serve` for real; verify `docker build` and `docker run`.
- [ ] `web/`: timeline, evidence table, memory panel, Nightshift status pill, feedback thumbs.
- [ ] Keep `docs/AI_TOOLS_USAGE.md` current — one row per session, whichever tool is used.

## Phase 6 — judge-proofing

- [ ] ≥3 genuinely different `input_examples/`; `scripts/generate_examples.py` from real runs.
- [ ] `scripts/validate_submission.sh` — the full disqualification checklist, including
      the step people skip: no `.env`, services unreachable, `SAMPLE_MODE=true`, still succeeds.
- [ ] Finish README, `docs/SPONSOR_TECH.md`, `metadata.json`, `docs/DATA_SOURCES.md`.
