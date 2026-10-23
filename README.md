# Hakken Agent

> **Status: Phase 1 (skeleton).** Track not yet chosen. This is a track-agnostic
> template: choosing a track later means swapping a *domain pack* (data sources,
> prompts, output schema), not rewriting plumbing. Sections marked **TBD** are
> deliberately empty rather than aspirational — see `TODO.md` for what is left.

Team Hakken (Anshuman, Arpon, Arnav) — Open Agent Hackathon 2026.

## One-line pitch

TBD — set when the track is chosen.

## What works today

| Piece | State |
|---|---|
| Preflight (`make preflight`) | **working** — checks tools, env-var names, Zetaris REST, the Nightshift contract |
| Secret scan + pre-commit hook (`make scan`) | **working**, with tests |
| Config layer (`app/config.py`) | **working** — validated settings, secrets as `SecretStr` |
| Nightshift provider | **verified reachable and answering**; adapter is Phase 2 |
| Zetaris data layer | **not yet exercised** — stack not started on the dev machine |
| Agents, engines, UI, Docker run | **not built yet** (Phases 2–6) |

Nothing in this repo fakes a result. The stubs raise `NotImplementedError` or exit
non-zero rather than returning plausible-looking output.

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
  (OpenAI-compatible, `http://127.0.0.1:8088/v1`). Verified online 2026-10-23; a
  request on `meterless/auto` was answered by `nvidia/nemotron-3.5-super-vl-120b-a12b`.
- **Which model answered** is recorded per request from the `meterless` compute receipt
  in the response body (`routed_model` / `winning_route`), not from a route we asked
  for. **Lane pinning is not honoured** on this Runtime build: every request races six
  lanes under a learned router, so role→disposition routing is our declared intent and
  the trace records what actually ran. See `docs/DECISIONS.md`.
- **AI coding tools used:** logged honestly in `docs/AI_TOOLS_USAGE.md`. Cursor is
  optional for this project — the repo is Cursor-ready (`.cursor/rules/project.mdc`)
  but not tied to it, and Claude Code did the work recorded so far.
- **Open-source code materially adapted:** the H-MEM and World Model specifications and
  conformance vectors from the Meterless repo (Apache-2.0), attributed in the ported
  test files. The Zetaris REST call shape follows that project's reference client.
- **Data:** synthetic and generated by us, seeded and deterministic.

## Responsible use

Synthetic data only. No real personal, clinical or financial records. If a medical
domain pack is chosen: small-cell suppression, causal-language caveats, a human-review
flag on high-risk outputs, and a clear **not medical advice** disclaimer.

## Limitations

- Zetaris integration is unverified against a live instance as of this commit.
- We cannot choose *which* Nemotron answers a request (see above).
- The Nightshift compute receipt we rely on for evidence is an undocumented,
  build-specific response shape; the adapter must degrade gracefully without it.

## Pre-existing components

None except the reference specifications and open-source libraries. See
`docs/PREEXISTING.md`.

## Licence

MIT — see `LICENSE`.
