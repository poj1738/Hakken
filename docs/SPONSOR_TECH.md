# Sponsor technology

Draft for the submission's sponsor-tech explanation. **Claims here must match the code
and the traces.** Anything unproven is marked *pending*, not asserted.

## Zetaris — the data layer

**Zetaris Scoring Methodology evidence: [`docs/zetaris_usl/README.md`](zetaris_usl/README.md).**
It maps every item (1a–2c) to a file and live, timestamped results. Headline: the Unified
Semantic Layer `medtrace_usl` turns 6 sources into 1 view, and its native DQ rule
`strength_is_a_real_product` caught 14 violations in 13,856 records.

**Verified live, 24–26 Oct, on two machines.** Agents get every fact by sending
Lightning SQL to the Zetaris REST API (`POST /sql-editor/sqls/run`, Bearer key,
`X-Org-ID`, a fresh `X-Request-ID` per call). They never read data files.

- **Federation over fragmented silos.** Four synthetic silos (hospital EMR, GP,
  pharmacy, patient interview) are each served by a local service. Zetaris registers
  each one as a Lightning REST table, flattens and harmonises it with a SchemaStore view,
  and caches it. A `medtrace.all_sources` view `UNION ALL`s them, so one query spans every
  silo and no agent computes a join live (`scripts/register_sources.py`).
- **Read-only agents.** `app/adapters/zetaris.py` allows only
  `SELECT`/`SHOW`/`DESCRIBE`/`WITH`, enforces a `LIMIT`, and caps a run at 8 queries.
  Registration DDL runs only from the registration script, never from an agent.
- **No model-written SQL.** The Planner states needs. The Executor fills SQL templates
  (Q1 identity, Q2 medicines, Q3 verification, Q4 shortages) that were verified live
  against committed fixtures (`make verify`).
- **Verification is a Zetaris query.** Before anything is shown, the Evaluator re-reads
  every cited row in a single Q3 query. A finding is blocked if any of its rows is missing
  or has changed.
- **Evidence.** Every query's SQL, row count and timing is in the run's trace, and each
  finding's evidence names the row it rests on. `output_examples/live/` holds real traces.

## Meterless — engines and provider

**Engines: both implemented and conformance-green** (`make conformance`: 22 checks).
These are Python ports of the official reference implementations (Apache-2.0, commit
`1742dec`, attribution in each file). Each port is verified by that engine's own
conformance suite, translated to pytest: H-MEM 13/13 vectors (the official
`vectors.json`, copied verbatim) and World Model 8/8. Where the World Model spec and its
conformance runner disagree on the merge band, we follow the runner (0.85) and document
it in `docs/DECISIONS.md`.

| User-facing feature | Engine service | Spec area | Test |
|---|---|---|---|
| Records for one patient across four systems are linked, each with its Zetaris query as provenance | World Model: `upsert_entity`, `relate` (`same-person-as`), audit log | Entities, relationships, provenance, audit | `tests/unit/test_identity_memory.py::test_linked_records_are_written_with_provenance` |
| Identity scoring bands (auto-merge / review / separate) | World Model resolve: banded merge decision | Entity resolution (runner band 0.85) | `tests/engines/test_world_model_conformance.py` |
| Whose medicines to fetch comes from the graph | World Model: `view` / neighbours | Graph queries | `test_identity_memory.py::test_medicines_are_read_for_the_linked_set_in_the_graph` |
| A pharmacist's identity decision is remembered; the next run doesn't ask again | World Model: `relate` (`same-person-as` / `distinct-from`, context `source:<src>`) | Relationships, bitemporal edges | `test_identity_memory.py::test_a_confirmed_identity_is_not_asked_again`, `::test_a_rejected_identity_stays_rejected`, `::test_decisions_survive_a_restart_with_local_storage` |
| Source trust that fusion uses | H-MEM: `add` (long-term records, one per source × attribute) | Records, provenance | `tests/unit/test_trust_memory.py::test_trust_is_seeded_from_the_priors_as_hmem_records` |
| The pharmacist's verdict changes trust, durably | H-MEM: `feedback` (specified deltas, clamped, ledger) | Feedback, ledger | `test_trust_memory.py::test_a_verdict_is_hmem_feedback_with_a_ledger_entry`, `::test_the_learning_demo_survives_a_restart` |
| The learning demo: reject P0003's GP dose, then P0007 resolves differently | H-MEM feedback → fusion | Feedback | `tests/unit/test_learning_demo.py`; `output_examples/*/example_4*` and `example_5*` |
| The Planner recalls past verdicts before it plans (`memory_used`) | H-MEM: `query` (hybrid retrieval) | Retrieval | `test_trust_memory.py::test_the_next_run_recalls_the_verdict_for_the_planner` |
| Findings cite the trust records behind them (`hmem_record_ids`) | H-MEM record ids | Records | `test_trust_memory.py::test_findings_cite_real_hmem_trust_records` |

**Provider** (**verified 2026-10-23, in use since 25 Oct**): Meterless Nightshift is the
app's only AI provider. Every agent model call goes through it. The adapter implements
the published contract:
- URL normalisation to `<host>/v1` (never `/v1/v1`)
- `Authorization: Bearer` on every call
- `meterless-app` and `meterless-scope: user` headers
- `GET /v1/models` as the status oracle: 401/403 → `unauthorized`, and 200 with
  `meterless/*` ids → `online`
- Auto Detect across ports 8088/8090/8787/11434
- a 180 s timeout

Structured output comes from the prompt plus pydantic validation, with exactly one repair
retry. A truncated answer is detected by `completion_tokens == max_tokens`. If a call
fails, that step degrades to a grounded template, and the response's `caveats` say so.

## NVIDIA — Nemotron through Nightshift

The NVIDIA API key exists **only** in Nightshift → Setup → Providers. It is absent from
this repo, from `.env`, from logs and from every submission artefact.

**Verified 2026-10-23:** a request on `meterless/auto` was answered by
`nvidia/nemotron-3.5-super-vl-120b-a12b` (tier C, 1 M context), and another by
`nvidia/nemotron-3.5-lightning-30b-a3b` (tier A). The runtime exposes eight Nemotron
lanes. Which one answered is recorded per request from the `meterless` compute receipt
(`routed_model`, `winning_route{model,label,provider,kind,tier}`), together with
per-phase latency, tokens and cost.

**In the product (25–26 Oct):** in every live run in `output_examples/live/`, every
Planner, Executor, Writer and Evaluator call was answered by
`nvidia/nemotron-3.5-lightning-30b-a3b`, as recorded in `model_calls[].routed_model` and
the trace.

**Honest limitation:** lane pinning is **not** honoured on Runtime build `m1-m4`.
Every request races six lanes under a learned router, and a concrete `nvidia/...` id is
not respected. Our role→disposition mapping (Planner/Executor → fast,
Evaluator/Writer → deep) is therefore a declared *intent*; the trace records the model
that actually ran. We do not claim lane control.

## AI coding tools

We build with **Claude Code**, and `CLAUDE.md` carries the working rules the agent
follows. Every session is logged in `docs/AI_TOOLS_USAGE.md`, which is what the AI
Usage Policy asks for.

**We do not use Cursor.** The official resources disagree on whether it is mandatory:
the event page reads as required, while other resources call it optional. We would
rather declare honestly what we used than claim a tool we did not touch. The repo
briefly carried a mirrored `.cursor/rules` file. We removed it because a duplicated rules
file drifts from the original.

## What was unique

Each of these is backed by code, tests and traces:

- **Verified, not asserted.** One Zetaris query re-reads every row a finding cites
  before anyone sees it. The Writer's prose is then checked against those rows, by code
  rules and by a Nemotron faithfulness verdict. Anything still disputed after the last
  round is replaced with a grounded template.
- **Clinical logic in code, language in the model.** Linkage, fusion, detection and
  triage are deterministic and scored against a planted answer key: held-out
  F1 0.95 and 0 false merges across 200 patients. Nemotron plans, resolves free text,
  explains, and checks the explanation. It never writes SQL and never decides a finding.
- **Memory that visibly changes behaviour.** A pharmacist's verdict is H-MEM feedback
  with a ledger entry, and the next patient's medicines resolve differently. An identity
  decision becomes a World Model edge, and the same question is never asked twice. Both
  survive a restart.
- **Honest provider reporting.** We show what the router actually did, including that
  we cannot choose the lane, rather than claiming control we lack.
