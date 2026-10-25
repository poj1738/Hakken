# TODO

Ordered by judging impact. Scoring /100: Impact 30, Technical 20, Innovation 15,
Demo 15, Product & UX 10, Sponsor tech 10. Ties go to Impact, then the earlier
submission. **Hard deadline 2026-10-27 23:45 UTC** (Wed 28 Oct 10:45 AEDT).

## Done

- [x] Phase 0 — reference review (`docs/REFERENCE_NOTES.md`), preflight script.
- [x] Phase 1 — skeleton, `app/config.py`, `.env.example`, `.gitignore`, secret scan
      with a pre-commit hook, 52 tests.
- [x] Preflight green, 22 pass / 0 fail: Zetaris answering, Nightshift `online` and a
      Nemotron returning a string.
- [x] Zetaris response envelope resolved and recorded as fixtures
      (`headers` + `data`, every value a string).

## Decisions made

- [x] **Track: Track 1.** The product is **MedTrace**, medication reconciliation across
      four siloed systems (`docs/PLAN_2026-10-24.md`).
- [x] **Synthetic-only data.** The sponsor's `NY_TAXI` and `TPCDS_DB` are declared in
      `docs/PREEXISTING.md` and not used.

## Phase 2 — adapters (next to build; both now fully unblocked)

- [ ] `app/adapters/meterless.py` — the contract is fully known:
      - URL normalisation is already implemented and tested in `app/config.py`; reuse it.
      - `Authorization: Bearer`, `meterless-app` on every call, `meterless-scope: user`
        on chat, 180 s timeout.
      - Status from `GET /v1/models`: 401/403 → `unauthorized`, 200 with `meterless/*`
        → `online`, else `offline`. Keep unknown `meterless/*` ids.
      - Auto Detect across 8088/8090/8787/11434 on three hosts.
      - **Never send a tight `max_tokens`** (see `docs/DECISIONS.md`).
      - Capture the whole `meterless` receipt into the trace; read it defensively and
        degrade to `response.model` if absent.
      - Structured JSON by prompt + pydantic validation + exactly one repair retry;
        do not rely on native tool-calling.
- [ ] `app/adapters/zetaris.py` — parse `headers` + `data` into dicts, cast strings,
      read-only guard (`SELECT`/`SHOW`/`DESCRIBE`/`WITH` only, enforced `LIMIT`),
      schema discovery via `SHOW LIGHTNING DATABASES` **and** `SHOW TABLES IN <db>`
      (not `SHOW DATASOURCES`, which returns 0 rows), timeouts, bounded retries,
      typed `ZetarisError`. Unit-test against `tests/fixtures/zetaris/`.
- [ ] Offline reasoner for `SAMPLE_MODE`: real rule-based work on cached data,
      labelled `offline-heuristic`. Must not replay saved model text.

## Phase 3 — data layer (done, 24–25 Oct)

- [x] `scripts/generate_synthetic.py` — 4 seeded silos with deliberate inconsistencies,
      200 patients, ground truth, replay fixtures.
- [x] `datasvc/` serving each silo whole at one URL; every table `CACHE`d.
- [x] Harmonised view `medtrace.all_sources` built at registration, so agents query
      one flat view and never compute a join live.
- [x] `scripts/register_sources.py` (generates its own SQL; `--apply`, `--refresh`,
      `--recreate-drifted`, `--verify-only`), verified live against the fixtures.
- [x] Spike: the Zetaris containers reach `datasvc` on the host.
- [x] `scripts/eval.py` — detector scorecard against the ground truth.

## Phase 4 — engines and agent loop

- [ ] H-MEM in Python + the 13 ported conformance checks + a memory-carries-over
      feature test (run 1 learns, run 2 visibly uses it).
- [ ] World Model in Python + the 8 ported conformance checks. Merge band **0.85**,
      per the runner and against its own prose spec.
- [ ] Orchestrator: bounded Planner → Executor → Evaluator → Writer with at least one
      real critique → revise loop; `RUN_TIMEOUT_S` returns `status: "partial"`.
- [ ] Evaluator independently re-queries Zetaris to re-derive every cited number and
      blocks unsupported claims. **Cast the strings first**, and **batch the checks into
      one query** — a 2-table join was measured at 91 s, so one query per claim blows
      the 5-10 min judging budget (see `docs/DECISIONS.md`).
- [ ] Orchestrator needs a **per-run Zetaris query budget**, not just an iteration cap:
      ~4 s per trivial query warm means 30 queries is 2 minutes before any model call.
- [ ] `app/tracing.py` — JSONL per run, official fields + our extensions + the receipt,
      with secret masking.

## Phase 5 — entry points, Docker, UI

- [ ] `run.py --input` and `run.py serve` for real.
- [ ] **Actually build and run the Docker image** — the Dockerfile and compose file are
      written but have never been executed.
- [ ] `web/`: question box, live agent timeline, evidence table linking each number to
      its SQL, "what memory was used" panel, Nightshift status pill, feedback thumbs.
      Accessible: labels, keyboard nav, contrast.

## Phase 6 — judge-proofing

- [ ] ≥3 genuinely different `input_examples/`; `scripts/generate_examples.py` writing
      `output_examples/` from real runs; a test asserting the outputs differ.
- [ ] `scripts/validate_submission.sh` — the full disqualification checklist, including
      the step people skip: fresh clone, no `.env`, both services unreachable,
      `SAMPLE_MODE=true`, and a run must still succeed with real logic.
- [ ] Finish `README.md`, `docs/SPONSOR_TECH.md`, `metadata.json`,
      `docs/DATA_SOURCES.md`, `docs/ARCHITECTURE.md` (mermaid from real code).
- [ ] Keep `docs/AI_TOOLS_USAGE.md` current — one row per session, whichever tool.
- [ ] **Make the repo public before submission** (it is private now).

## Housekeeping

- [ ] **Rotate both credentials after the event.** The Nightshift Runtime token and the
      Zetaris API key were pasted into a chat transcript. Neither is in git history
      (verified), but both are exposed to anyone with that transcript.
