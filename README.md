# Hakken Agent

> **Work in progress: Open Agent Hackathon 2026, team Hakken.**
>
> **Only two things are built: the preflight script and the config layer.** There is no
> agent, no data pipeline, no UI. The track is not chosen yet. Everything else in this
> repo is scaffolding with honest stubs, and the sections marked **TBD** are deliberately
> empty rather than aspirational. `TODO.md` lists what is left.

Team Hakken (Anshuman, Arpon, Arnav).

The intent is a track-agnostic template, so that choosing a track later means writing a
*domain pack* (data sources, prompts, output schema) rather than rewriting plumbing.
That is the plan, not yet an achievement.

## One-line pitch

TBD — set when the track is chosen.

## What actually works today

Two pieces of working code:

| Piece | State |
|---|---|
| `scripts/preflight.py` (`make preflight`) | **works.** Read-only. Checks tooling, which env-var *names* are set, Zetaris REST reachability, and the Meterless Nightshift provider contract. Last run **22 pass / 0 fail on Arpon's machine, 23 Oct**; run it on your own. |
| `app/config.py` | **works.** Validated settings; secrets held as `SecretStr` so they cannot leak through `repr`/`str`/`model_dump`; `safe_dump()` reports presence only. |
| `scripts/secret_scan.py` (`make scan`) | **works.** 8 patterns, installed as a pre-commit hook, verified to block a commit. Supporting, not a product feature. |

### What is verified but *not* built

Reachability is not a feature. The preflight proved these services answered **on one
machine on one day**; **no application code uses either one yet**, and no other
teammate has run them (see `docs/ENVIRONMENTS.md`).

| | Observed on Arpon's machine, 23 Oct 2026 | Built? |
|---|---|---|
| Meterless Nightshift | state `online`; a request on `meterless/auto` was answered by `nvidia/nemotron-3.5-super-vl-120b-a12b`, returning a plain string | **no** — `app/adapters/meterless.py` is a stub |
| Zetaris | `SELECT 1` → `1`; catalogue discovery worked; the response envelope is recorded from that instance in `tests/fixtures/zetaris/` | **no** — `app/adapters/zetaris.py` is a stub |

### Not started

Agents, the orchestrator and its critique loop, H-MEM, World Model, tracing, the
synthetic data pipeline, `datasvc`, sample mode, the web UI, and the Docker run path.
`run.py` exits non-zero and says so. The Dockerfile and `docker-compose.yml` are
written but **have never been built or run**.

Nothing here fakes a result: the stubs raise `NotImplementedError` or exit non-zero
rather than returning plausible-looking output. 52 tests cover the config layer and the
secret scanner — nothing else, because nothing else exists.

## Quickstart

```bash
make setup                      # .venv, pinned deps, pre-commit hook
cp .env.example .env            # then fill it in yourself
make preflight                  # read-only: what is reachable and what is missing
make test
```

Docker (Phase 5, not yet verified):

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

TBD — synthetic only, three fragmented "silos" with deliberate inconsistencies to
reconcile. Documented in `docs/DATA_SOURCES.md` with origin, licence and how to
regenerate. See `docs/DECISIONS.md` for why each silo is served whole at one URL.

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
- **Data:** none generated yet. The plan is synthetic only, seeded and deterministic
  so any reviewer can reproduce it. The Zetaris instance carries the sponsor's own
  pre-existing sample databases, declared in `docs/PREEXISTING.md` and currently unused.

## Responsible use

Synthetic data only. No real personal, clinical or financial records — and at present
no data at all. If a medical domain pack is chosen, the safety layer *to be built* is:
small-cell suppression, causal-language caveats, a human-review flag on high-risk
outputs, and a clear **not medical advice** disclaimer. None of it is implemented yet.

## Limitations

- **The product does not exist yet.** Two scripts and a config layer work; the agent,
  data layer, engines and UI are unbuilt.
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
