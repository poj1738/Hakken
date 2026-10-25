# MedTrace — Hakken Agent

> **Work in progress: Open Agent Hackathon 2026, team Hakken. Track 1.**
>
> **The data pipeline and the clinical logic are built and measured. The agent loop,
> API and UI are not finished yet.** Everything below says which is which. The
> sections marked **TBD** are deliberately empty rather than aspirational.

Team Hakken (Anshuman, Arpon, Arnav).

**100% synthetic data. Not medical advice.** No real patient record is used anywhere.

## One-line pitch

MedTrace reconciles an admitted patient's pre-admission medicines across four
systems that don't talk to each other: the hospital EMR, the GP, the community
pharmacy and the bedside interview. It queries every source through Zetaris, says
"unknown" rather than "not taking" when a source is missing, ranks discrepancies so
high-risk ones reach the pharmacist first, and learns from the pharmacist which
source to trust.

## What actually works today

| Piece | State |
|---|---|
| **Synthetic data** (`scripts/generate_synthetic.py`, `make synth`) | **works.** 200 seeded patients across four silos, ~13,900 rows, with planted discrepancies and identity traps, and a ground-truth answer key. Real Australian medicine reference data (PBS, ATC, APINCHS). See `docs/DATA_SPEC.md`. |
| **Zetaris data layer** (`scripts/register_sources.py`) | **works on Arpon's machine.** Four silos registered as REST tables, a harmonised `medtrace.all_sources` view, and every query template verified live against committed fixtures. Each query takes about 2–3 s at 200 patients. |
| **Clinical domain pack** (`app/domain/packs/medtrace/`) | **works.** Identity linkage, normalisation, coverage, trust-weighted fusion, discrepancy detection, the safety gate and triage. Real code, no model calls. |
| **Detector scorecard** (`scripts/eval.py`) | **works.** Scores the real chain against the answer key. Held-out, with simulated pharmacist review: **precision 0.95, recall 0.95, F1 0.95** (today's code prints recall 0.97 / F1 0.96, which includes one fix found while studying held-out misses; 0.95 is the clean figure, `docs/DECISIONS.md`); core APINCHS high-risk recall **30/32** (95% CI 0.80–0.98); **0 false merges** across 200 patients. Pinned by tests. |
| **Sample inputs** (`input_examples/`) | **five**, each with replay fixtures and a written expected outcome, including a staged learning-demo pair (see `docs/DECISIONS.md`). |
| `scripts/preflight.py`, `app/config.py`, `scripts/secret_scan.py` | **work.** Preflight, validated settings with secrets as `SecretStr`, and a pre-commit secret scan. |

### Not finished

The Zetaris and Meterless **adapters**, the agent loop (Planner → Executor →
Evaluator → Writer), the H-MEM and World Model engines, `POST /run`, `run.py`,
`SAMPLE_MODE`, the web UI, and the Docker run path. `run.py` exits non-zero and says
so. No model call goes through Nightshift in the product yet. Nothing here fakes a
result: the stubs raise `NotImplementedError` or exit non-zero.

## Quickstart

```bash
make setup                      # .venv, pinned deps, pre-commit hook
cp .env.example .env            # then fill it in yourself
make preflight                  # read-only: what is reachable and what is missing
make test                       # passes; ~43 tests skip until you build the data below
```

Build the data (no network needed) and run the full suite, scorecard included:

```bash
make lexicon                    # reference tables; PBS codes stay synthetic without `make data`
make synth                      # 200 synthetic patients; uses the committed lexicon, so the
                                # committed fixtures come out byte-identical
make test                       # now nothing skips for missing data
.venv/bin/python scripts/eval.py --split heldout   # the scorecard
```

Docker: **not working yet.** The image builds, but `run.py serve` exits 2 with "not
implemented yet" until the API lands. The intended commands, once it does:

```bash
docker compose up --build
curl -X POST localhost:8000/run -H 'content-type: application/json' \
     -d @input_examples/example_1.json
```

## Setup: Zetaris and Nightshift

Both run **on the host**, not in our compose file.

- **Zetaris** — install per the Participant Setup Guide (`zetaris-platform` compose).
  Web UI `http://localhost:3000`, REST API `http://localhost:8888/api/v1.0`, org ID `1`
  on a local install. Create an API key in **Management → API Tokens** (shown in
  plaintext once) and put it in `.env` as `ZETARIS_API_KEY`.
  **Never call port 8889** — it is internal.
- **Nightshift** — copy the Runtime URL and token from **Nightshift → Console** into
  `METERLESS_BASE_URL` and `METERLESS_RUNTIME_TOKEN`.
- **NVIDIA** — the NVIDIA API key goes **only** in Nightshift → Setup → Providers.
  It must never appear in this repo, in `.env`, in logs, or in any submission material.

Inside a container, use `host.docker.internal` instead of `localhost` (our
`docker-compose.yml` already overrides both URLs).

## Architecture

TBD — mermaid diagram lands with the agent loop in Phase 4. The intended shape:

```
Planner → Executor(s) → [Zetaris SQL] → World Model ingest
   ↑                                        │
   └── critique ── Evaluator (re-derives every cited number) ──→ Writer
```

## Agents and roles

TBD (Phase 4). At least two named agents with distinct roles, real handoffs, and at
least one critique → revise loop, all bounded.

## Data sources

Synthetic patients only, in four silos (hospital EMR, GP, pharmacy, patient
interview), generated by `scripts/generate_synthetic.py` with a fixed seed. The
medicine reference data is real and public: PBS items, WHO ATC codes and the ACSQHC
APINCHS high-risk classes. Origin, licence and how to regenerate are in
`docs/DATA_SOURCES.md` and `docs/DATA_LICENCES.md`; the data model is in
`docs/DATA_SPEC.md`. The sponsor's pre-existing `NY_TAXI` and `TPCDS_DB` databases
are not used.

## Sample mode

`SAMPLE_MODE=true` is intended to run the real agent logic against recorded Zetaris
results with no Zetaris, no Nightshift and no network, using a deterministic offline
reasoner labelled `offline-heuristic` in traces. It does real work on the cached data
and does **not** replay saved model text. **Not yet implemented** (Phase 2).

## Engines used

Planned: **H-MEM** (memory across runs, feeding the Planner and the trust ledger) and
**World Model** (shared evidence state with provenance). Both ported to Python from the
official specs, verified by their official conformance suites translated to pytest
(`make conformance`). **Not yet implemented** (Phase 4). See `docs/REFERENCE_NOTES.md`
§3–4 for the exact contracts, and `docs/DECISIONS.md` for the one place the engine spec
and its conformance runner disagree.

## AI and model usage

- **Models** reach us only through the **Meterless Nightshift Runtime**
  (OpenAI-compatible, default `http://127.0.0.1:8088/v1`). Observed `online` on Arpon's
  machine on 23 Oct 2026, where a request on `meterless/auto` was answered by
  `nvidia/nemotron-3.5-super-vl-120b-a12b`. Each teammate runs their own runtime.
- **Which model answered** *will be* recorded per request from the `meterless` compute
  receipt in the response body (`routed_model` / `winning_route`), not from the route we
  asked for. The receipt shape was confirmed on Arpon's runtime, but no tracing code
  exists yet. **Lane pinning was not honoured** there (build `m1-m4`): every request
  raced six lanes under a learned router, so role→disposition routing can only ever be
  a declared intent, and the trace will record what actually ran. Lane configuration is
  per-machine. See `docs/DECISIONS.md`.
- **AI coding tools used:** **Claude Code**, logged per session in
  `docs/AI_TOOLS_USAGE.md`. `CLAUDE.md` holds the working rules. Cursor is not used —
  see that log for why.
- **Open-source code to be materially adapted:** the H-MEM and World Model
  specifications and conformance vectors from the Meterless repo (Apache-2.0). Nothing
  is ported yet; when it is, each ported test file will carry an Apache-2.0 attribution
  header. The Zetaris REST call shape in our (stubbed) adapter follows that project's
  reference client, and four real Zetaris responses are recorded as test fixtures.
- **Data:** synthetic only, seeded and deterministic: `make lexicon && make synth`
  reproduces the committed data exactly, and CI checks that on every push. Real PBS
  codes come from the committed lexicon; rebuilding them needs `make data` (a
  rate-limited PBS API fetch) plus a manual download of the data.gov.au PBS Item
  Report (`docs/DATA_LICENCES.md` §5). The Zetaris instance carries the sponsor's own
  pre-existing sample databases, declared in `docs/PREEXISTING.md` and unused.

## Responsible use

Synthetic data only; no real personal, clinical or financial records. **Not medical
advice:** MedTrace drafts a reconciliation for a pharmacist to review and never
changes a chart itself. Built in the domain pack: an identity near-miss stops for a
human before any of that record is read; a missing source is shown as *unknown*,
never as "not taking"; high-risk (APINCHS) medicines are ranked first; a dose that
can't be confirmed (warfarin, insulin, prednisolone, methotrexate) becomes a task to
confirm with the patient, not a guess; and every finding must cite the source rows
it rests on, or the safety gate blocks it. The disclaimer in the UI is not built yet.

## Limitations

- **The product is not finished.** The data layer and clinical logic work and are
  measured; the agent loop, engines, API and UI are unbuilt.
- Scores come from synthetic patients and a simulated pharmacist review. They show the
  logic does what it was designed to do, not how it performs on real records. 32 core
  high-risk cases cannot support a "100% recall" claim, and we don't make one.
- The Zetaris and Meterless *adapters* are stubs. Both services and the Zetaris
  response envelope were verified on **one machine on one day** (Arpon's, 23 Oct) and
  on no other; see `docs/ENVIRONMENTS.md` for who can currently run what.
- We cannot choose *which* Nemotron answers a request (see above).
- The Nightshift compute receipt we rely on for evidence is an undocumented,
  build-specific response shape; the adapter must degrade gracefully without it.

## Pre-existing components

No pre-existing code of our own. Declared in `docs/PREEXISTING.md`: the Meterless engine
specifications and conformance vectors (Apache-2.0), the Zetaris getting-started
reference repo, the sponsor's `zetaris-platform` install, and the `NY_TAXI` (15 tables)
and `TPCDS_DB` (308 tables) sample databases that shipped with that install. The sample
databases are declared because they predate the build window; they are not used.

## Licence

MIT — see `LICENSE`.
