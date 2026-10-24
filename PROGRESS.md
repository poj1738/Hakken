# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-25 12:30 AEDT by Arpon

> **On `arpon/population` (green, awaiting merge):** consultant rulings applied, population 200, held-out F1 0.95, high-risk 35/37. See the latest HANDOFF entry.

## Status

**The track is MedTrace**, medication reconciliation across four siloed systems.
Roles and contracts: `docs/PLAN_2026-10-24.md`.

**The clinical domain pack is complete.** Every function in
`app/domain/packs/medtrace/` has a real body except `queries.q_shortages` (Q4, the
optional TGA overlay). It is scored end to end by `scripts/eval.py` against the
planted ground truth.

**The critical path is now the agent layer, and every unmet disqualification rule
sits in it.** Both adapters, the four agents, the orchestrator, the API, tracing
and both engines are still stubs. That means: no model call goes through Nightshift
yet (rules 2 and 3), no Meterless engine or conformance test exists (rule 2),
`POST /run`, `run.py`, Docker and `SAMPLE_MODE` do not work (rule 8), and no agent
queries Zetaris yet (rule 1 — though the registration itself is live and verified).

| Area | Owner | State |
|---|---|---|
| Tests | — | **584 green.** No services needed; CI runs Python 3.11 on a fresh clone and the suite changes 0 tracked files |
| **MedTrace contract** (`types.py`) | Arpon | **frozen, on `main`.** Shared file — changes need sign-off, a HANDOFF entry and a PR line |
| SQL templates (`queries.py`) | Arpon | **done, run live.** Q0–Q3 and Q_REF; `q_shortages` (Q4) deliberately unwritten |
| Clinical logic — all 11 modules | Arpon | **done.** `fuse` (trust-weighted BPMH), `detect` (9 of 11 types emitted; 2 deliberately not — see `docs/DECISIONS.md` 25 Oct), `triage` (ranking with an absolute APINCHS floor) |
| **Detector scorecard** (`scripts/eval.py`) | Arpon | **200 patients, held-out: precision 0.95, recall 0.95, F1 0.95, high-risk 35/37** (simulated review); 0.93 F1 with no human review. Tune 0.93, high-risk 34/34. Consultant rulings 11–14 applied. Pinned by `tests/eval/test_scorecard.py` |
| Identity linkage | Arpon | 200 patients: 0 false merges; 535 true links auto-merge, 31 go to review, 2 lost |
| Reference data | Arpon | **done** — 224 lexicon rows, 203 with a real PBS code |
| Synthetic generator, ground truth | Arpon | **done** — 40 patients, 60 planted findings, identity traps. Ground truth now cites only the patient's own rows (9 of 20 omissions used to cite someone else's) |
| Fixtures for `SAMPLE_MODE` | Arpon | **done** — Q0 (admissions, new), Q1–Q3 for 10 patients, Q_REF. All diffed against live Zetaris: identical |
| `datasvc/`, Zetaris registration | Arpon | **live and verified, 25 Oct** — 8/8 views, 6/6 fixture diffs, `--verify-only` exits 0 |
| TGA shortages loader | Arpon | parses 1,010 rows; **not registered** (Q4 optional) |
| `app/schemas.py` (API contract) | Arnav | **done, on `main`** (#12). Additions beyond PLAN 2.8 await Arpon's sign-off |
| API example fixtures for the UI | Arnav | **done, on `main`** (#13) — every UI state |
| Zetaris / Meterless adapters | Arnav | **stub** — Zetaris adapter is his next item |
| Orchestrator, agents, API, trace | Arnav | not started |
| **World Model + 8 conformance checks** | Arnav | **not started — a disqualification gate, due Sat 4pm.** `identity.decide` still uses Arpon's local copy |
| H-MEM + feedback | Arnav | not started |
| Web UI | Anshu | **not started** — no commits or branches; `web/` holds only `.gitkeep` |
| Docker run path | — | not started — the Dockerfile has never been built |

## Sunday's goal

By tonight: `POST /run` on P0001 returns a real `RunResponse` end to end —
`SAMPLE_MODE` first, then live — with at least one Nemotron call through Nightshift,
World Model conformance green, and the UI rendering it in mock mode. H-MEM and the
feedback loop by Monday morning at the latest.

## Next up

1. **Arnav** — in disqualification-risk order: Meterless adapter; orchestrator wired
   to the domain pack with the Writer as the first real Nemotron call; API and
   `run.py`; World Model and its 8 checks (then swap Arpon's local `decide`); H-MEM
   and feedback. Everything you need from Arpon is on `main`, including a Q0
   fixture (one row per chart *line* — dedupe on `source_patient_id`).
2. **Anshu** — PLAN §6 items 1–10 in mock mode against `tests/fixtures/api/`. First:
   picker, timeline, grid and flags rendering `run_P0001_done.json`.
3. **Arpon** — review Arnav's schema additions (#12); then take work off Arnav —
   World Model is the strongest candidate (a disqualification gate with no coupling
   to his orchestrator), but **ask him what he has started first**.

## Waiting on Arpon (decisions only he can make)

1. ~~Population size~~ — **200, done 25 Oct.**
2. ~~Consultant briefs 11–14~~ — **answered and applied 25 Oct** (`docs/DECISIONS.md`).
3. **Sotalol** — DATA_SPEC `C07AA07` (not APINCHS) vs PBS `C01BD` (`Ext`).
4. **DATA_SPEC §4.2 bundle 6** shares sum to 0.95.
5. **Four formulation-trap drugs have one form each**, so no IR/MR pair can be planted.

## Operational notes

**`make test` does not build data.** `data/reference/` and `data/synthetic/silos/`
are gitignored; run `make lexicon` and `make synth`. Tests that need them skip — a
skip is a missing build, not a pass.

**After `make synth`, run `make refresh`** so Zetaris picks up the new rows
(`CACHE TABLE` on a cached table is a no-op), then `make verify`.

**If you add a column to a generated file**, run
`python3 scripts/register_sources.py --recreate-drifted`. A REST table infers its
schema once at creation and a view pins its SELECT list the same way; `COUNT(*)`
cannot detect the drift. It drops Zetaris objects, so ask first.

**To see the detector work:** `python3 scripts/eval.py --patient P0002` prints one
patient's grid, ranked findings and planted truth; `--split heldout --misses` the
scorecard with every miss and false positive.
