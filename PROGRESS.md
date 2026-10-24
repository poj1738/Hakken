# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-24 15:10 AEDT by Arpon

## Status

**The track is decided: MedTrace**, medication reconciliation across four siloed
systems. Roles, contracts and today's hour-by-hour plan are in
`docs/PLAN_2026-10-24.md` — read it before starting work.

Phase 1 is complete. Of the MedTrace build, the domain-pack contract exists and is
frozen; nothing downstream of it is built yet.

| Area | Owner | State |
|---|---|---|
| Preflight (`make preflight`) | — | working — **22 pass / 0 fail on Arpon's machine, 23 Oct** (his services only; re-run it on yours) |
| Config layer (`app/config.py`) | — | working — validated, secrets as `SecretStr`, `ZETARIS_TIMEOUT_S` 180 |
| Secret scan + pre-commit hook | — | working, verified to block a commit |
| Tests | — | **160 green** on any machine — no services, isolated from any local `.env` |
| Team workflow, CI, onboarding | — | working |
| **MedTrace contract** (`app/domain/packs/medtrace/types.py`) | Arpon | **frozen.** Shared file — changes need sign-off, a HANDOFF entry and a PR line |
| **SQL templates** (`queries.py`) | Arpon | **written** — Q_REF, Q0–Q3 real Lightning SQL. **Never run against Zetaris.** Q4 (TGA) deliberately unwritten |
| `identity.decide()`, `SOURCE_TRUST_PRIORS` | Arpon | **real and usable today** |
| Clinical logic (identity, normalise, coverage, supply, fuse, detect, safety, triage) | Arpon | **skeleton** — exact signatures, every body raises `NotImplementedError("Arpon: <file>")` |
| Reference data (PBS lexicon, APINCHS, nicknames) | Arpon | not started — PLAN step 2 |
| `docs/DATA_SPEC.md` | Arpon | not started — Arpon is writing it by hand |
| Synthetic generator, ground truth, fixtures | Arpon | not started — PLAN step 4 |
| `datasvc/`, `scripts/register_sources.py` | Arpon | not started — PLAN steps 5–6 |
| Zetaris / Meterless adapters | Arnav | **stub** — both unblocked, contracts fully known |
| Orchestrator, agents, API, trace | Arnav | not started |
| H-MEM, World Model | Arnav | not started — World Model first, `identity.decide` waits on it |
| Web UI | Anshu | not started |
| Docker run path | — | not started — the Dockerfile has never been built |

## Observed on Arpon's machine (one machine, one day — not team-wide)

Nobody else has run the services yet (`docs/ENVIRONMENTS.md`). **Run `make preflight`
on your own machine** rather than trusting this. API behaviour that holds everywhere is
in `CLAUDE.md`.

- **Zetaris latency is the constraint that shapes the architecture** [24 Oct]:
  `SELECT 1` ~1.1 s, `COUNT(*)` on 789 rows 20.7 s cold and ~4 s warm, a 2-table
  `JOIN` with `GROUP BY` **timed out once, then took 91.2 s**. Per-query overhead, so
  smaller silos do not help. Model calls take 0.4–1.2 s, so **Zetaris, not the model,
  is the judging time budget.** Hence: no joins at agent time, 3–4 queries per run
  (hard budget 8), harmonise in cached views at registration, one batched verification
  query. See `docs/DECISIONS.md`.
- **Zetaris** answering on `localhost:8888`, envelope `{headers, data, total, timeUsed}`,
  **every value a string**. Catalogue discovery needs `SHOW LIGHTNING DATABASES` +
  `SHOW TABLES IN <db>`; `SHOW DATASOURCES` returns 0 rows.
- **Nightshift** `online`. `meterless/auto` was answered by
  `nvidia/nemotron-3.5-super-vl-120b-a12b`. **Lane pinning was not honoured** on this
  runtime (build `m1-m4`) — record `routed_model`, never `provider_model`.

## Blocked on

Nothing is blocked on a decision. The open **risks**, in order of how much rests on
them:

1. **Can the Zetaris containers reach `host.docker.internal:8100`?** Unproven. If not,
   the fallbacks in order are: `datasvc` on the Zetaris network, then MinIO/Parquet,
   then Postgres over JDBC (`docs/DECISIONS.md`, PLAN 11). This is the next thing Arpon
   does.
2. **Does the union view register, cache and query?** `medtrace.all_sources` is a
   `UNION ALL` of `explode()` views, and a second reference to one of those in a single
   query is known to fail. Fallback: four per-source views queried separately.
3. **No SQL in `queries.py` has been run against Zetaris.** It is written to the
   recorded envelope and the documented dialect rules, not measured.

## Next up

1. **Arpon** — PLAN step 1: Zetaris up, then the `host.docker.internal:8100`
   reachability spike; message Arnav either way. Then step 2 (reference build), 4
   (generator + fixtures), 5 (`datasvc`), 6 (registration), 7 (fill in the skeleton).
2. **Arnav** — adapters and orchestrator need nothing from Arpon. Import
   `app.domain.packs.medtrace.*` rather than writing your own stubs; use a
   fixture-backed fallback in your own code where a body still raises. World Model
   before H-MEM.
3. **Anshu** — `web/` against Arnav's example JSON in `tests/fixtures/api/`. No Zetaris
   and no Nightshift, ever.

Claim an item in your handoff entry before starting it.
