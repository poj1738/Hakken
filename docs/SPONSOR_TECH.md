# Sponsor technology

Draft for the submission's sponsor-tech explanation. **Claims here must match the code
and the traces.** Anything unproven is marked *pending*, not asserted.

## Zetaris — the data layer

*Pending.* Role: agents obtain every fact by sending Lightning SQL to the Zetaris REST
API (`POST /sql-editor/sqls/run`); they never read data files. Three synthetic silos are
registered as Lightning REST tables over a local service, flattened with SchemaStore
views, so one SQL query can span fragmented sources. Integration lives in
`app/adapters/zetaris.py`, with a read-only guard that permits only
`SELECT`/`SHOW`/`DESCRIBE`/`WITH` and enforces a `LIMIT`; registration DDL runs only
from `scripts/register_sources.py`, never from an agent.

## Meterless — engines and provider

**Engines** (*pending*): H-MEM and World Model, implemented in Python from the official
`AGENTS.md` specifications, each verified by that engine's own conformance suite
translated to pytest (13 checks for H-MEM, 8 for World Model). Where the World Model
spec and its conformance runner disagree on the merge band, we follow the runner
(0.85) and document it — see `docs/DECISIONS.md`.

Each user-facing feature will be mapped to the named engine service and spec section,
in the style the official starter uses:

| User-facing feature | Engine service | Spec section | Test |
|---|---|---|---|
| _(pending)_ | | | |

**Provider** (**verified 2026-10-23**): Meterless Nightshift is the app's only AI
provider. The adapter implements the published contract — URL normalisation to
`<host>/v1` (never `/v1/v1`), `Authorization: Bearer` on every call, `meterless-app`
and `meterless-scope: user` headers, `GET /v1/models` as the status oracle
(401/403 → `unauthorized`, 200 with `meterless/*` ids → `online`), Auto Detect across
ports 8088/8090/8787/11434, and a 180 s timeout. Confirmed live: a wrong token reports
`unauthorized` rather than `offline`, Auto Detect finds the runtime on 8088, and a
plain-text request on `meterless/auto` returns a string.

## NVIDIA — Nemotron through Nightshift

The NVIDIA API key exists **only** in Nightshift → Setup → Providers. It is absent from
this repo, from `.env`, from logs and from every submission artefact.

**Verified 2026-10-23:** a request on `meterless/auto` was answered by
`nvidia/nemotron-3.5-super-vl-120b-a12b` (tier C, 1 M context); another was answered by
`nvidia/nemotron-3.5-lightning-30b-a3b` (tier A). The runtime exposes eight Nemotron
lanes. Which one answered is recorded per request from the `meterless` compute receipt
(`routed_model`, `winning_route{model,label,provider,kind,tier}`), together with
per-phase latency, tokens and cost.

**Honest limitation:** lane pinning is **not** honoured on Runtime build `m1-m4`.
Every request races six lanes under a learned router, and a concrete `nvidia/...` id is
not respected. Our role→disposition mapping (Planner/Executor → fast,
Evaluator/Writer → deep) is therefore a declared *intent*; the trace records the model
that actually ran. We do not claim lane control.

## AI coding tools

We build with **Claude Code**, and `CLAUDE.md` carries the working rules the agent
follows. Every session is logged in `docs/AI_TOOLS_USAGE.md`, which is what the AI
Usage Policy asks for.

**We do not use Cursor.** The official resources disagree on whether it is mandatory —
the event page reads as required, other resources call it optional. We would rather
declare honestly what we used than claim a tool we did not touch. The repo briefly
carried a mirrored `.cursor/rules` file; it was removed because a duplicated rules file
drifts from the original.

## What was unique

*To be written once the track is chosen.* Candidates so far, all evidence-backed:

- The Evaluator re-derives every cited number straight from Zetaris and blocks claims
  it cannot reproduce, so the evidence table is verified rather than asserted.
- Memory that visibly changes behaviour between runs, with an append-only trust ledger
  and user feedback that moves retrieval ranking by exact, specified deltas.
- Honest provider reporting: we surface what the router actually did, including the
  limitation that we cannot choose the lane, rather than claiming control we lack.
