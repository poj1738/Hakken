# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-25 by Anshu

> **On `main`:** consultant rulings applied, population 200, held-out F1 0.95, high-risk 35/37 (core APINCHS 30/32, extended 5/5). **Arpon's section is done**, including demo data: 5 `input_examples/` with replay fixtures, a staged learning-demo pair (P0003 → P0007, `docs/DECISIONS.md`), and sample data in the Docker image. Everything left is in Arnav's and Anshu's layers.

## Status

**Track 1. The product is MedTrace**, medication reconciliation across four siloed systems.
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
| **Detector scorecard** (`scripts/eval.py`) | Arpon | **200 patients, held-out: precision 0.95, recall 0.95, F1 0.95, high-risk 35/37 — core APINCHS 30/32 [0.80, 0.98], extended 5/5** (simulated review); 0.93 F1 with no human review. Tune 0.93 (one deliberate miss: the learning-demo chart error, visible only after feedback), high-risk 34/34. Consultant rulings 11–14 applied. Pinned by `tests/eval/test_scorecard.py` |
| Identity linkage | Arpon | 200 patients: 0 false merges; 535 true links auto-merge, 31 go to review, 2 lost |
| Reference data | Arpon | **done** — 224 lexicon rows, 203 with a real PBS code |
| Synthetic generator, ground truth | Arpon | **done** — 40 patients, 60 planted findings, identity traps. Ground truth now cites only the patient's own rows (9 of 20 omissions used to cite someone else's) |
| Fixtures for `SAMPLE_MODE` | Arpon | **done** — Q0 (admissions, new), Q1–Q3 for 10 patients, Q_REF. All diffed against live Zetaris: identical |
| `datasvc/`, Zetaris registration | Arpon | **live and verified, 25 Oct** — 8/8 views, 6/6 fixture diffs, `--verify-only` exits 0 |
| TGA shortages loader | Arpon | parses 1,010 rows; **not registered** (Q4 optional) |
| `app/schemas.py` (API contract) | Arnav | **done and signed off.** #12, plus Arpon's two asks: `Finding.detail`, and `FeedbackRequest.source`/`attribute` (required for `source_outdated`). Structured `Task` deferred |
| API example fixtures for the UI | Arnav | **done, regenerated for the 25 Oct data.** Every UI state; the review example is now P0015 (file name unchanged for `web/`) |
| Meterless adapter (Nightshift) | Arnav | **done, verified live on Arnav's machine, 25 Oct** — status, chat and JSON answered by `nvidia/nemotron-3.5-lightning-30b-a3b`; 33 tests. SAMPLE_MODE uses `offline-heuristic`, never replayed text. Not yet called by any agent |
| Zetaris adapter | Arnav | **stub** — next |
| Orchestrator, agents, API, trace | Arnav | not started |
| **World Model + 8 conformance checks** | Arnav | **not started — a disqualification gate, due Sat 4pm.** `identity.decide` still uses Arpon's local copy |
| H-MEM + feedback | Arnav | not started |
| Web UI | Anshu | **on `main` (#22); review of all 10 PLAN §6 items done on `anshu/ui-review`**, mock mode only. Follows #23 (`detail`, `source_outdated` names its record) and #24 (identity verdict prefixes). Never run against a live API. Six open questions for Arnav in HANDOFF (dose unit, `TraceEvent.model`, task order …) |
| Docker run path | — | not started — the Dockerfile has never been built |

## Sunday's goal

By tonight: `POST /run` on P0001 returns a real `RunResponse` end to end —
`SAMPLE_MODE` first, then live — with at least one Nemotron call through Nightshift,
World Model conformance green, and the UI rendering it in mock mode. H-MEM and the
feedback loop by Monday morning at the latest.

## Next up

**Arnav's session: read `docs/TODO_ARNAV.md` first** — everything needed from Arpon's side, in order.

1. **Arnav** — in disqualification-risk order: Meterless adapter; orchestrator wired
   to the domain pack with the Writer as the first real Nemotron call; API and
   `run.py`; World Model and its 8 checks (then swap Arpon's local `decide`); H-MEM
   and feedback. Everything you need from Arpon is on `main`, including a Q0
   fixture (one row per chart *line* — dedupe on `source_patient_id`).
2. **Anshu** — merge `anshu/ui-review`. Then point the UI at the live API as soon as
   Arnav's `POST /run` exists (`VITE_API_MODE=live`), and rehearse the 30-second demo
   arc in mock mode.
3. **Arpon** — section done; schema review posted on #12. World Model stays with
   Arnav. Free to pick up whatever Arnav or Anshu hand back in HANDOFF.

## Waiting on Arpon (decisions only he can make)

Nothing. Briefs 1–5 were decided 24 Oct and briefs 11–14 on 25 Oct (`docs/DECISIONS.md`):
sotalol stays `C07AA07`, bundle 6 gained desvenlafaxine and sums to 1.00, and
metoprolol/gliclazide/diltiazem now have IR/MR pairs (venlafaxine and tamsulosin have no
Australian pair).

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
