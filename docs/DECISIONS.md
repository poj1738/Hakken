# Decisions

Decision, why, date. Newest first.

Anything discovered by observation rather than from a published contract is marked
**[live]** with **whose machine and when**, so a later reader can tell evidence from
assumption — and can tell a team-wide fact from one person's setup. A `[live]` finding
is one data point: it may not reproduce on your machine, on a different runtime build,
or after a provider update. Re-verify before depending on it, and add your own
observation rather than editing someone else's.

---

## 2026-10-24 — Two datasvc URLs, because two networks reach it

**Decision.** `DATASVC_PUBLIC_URL` is what **Zetaris** uses and goes verbatim into the
`CREATE LIGHTNING REST TABLE ... endpoint` SQL. `DATASVC_INTERNAL_URL` is what **our own
app** uses. `docker-compose.yml` overrides only the internal one, and `config.py`
rejects a `datasvc:` host for the public one.

**Why.** The first draft of `docker-compose.yml` set
`DATASVC_PUBLIC_URL: http://datasvc:8100` — correct for our app on our compose network,
and wrong for its documented purpose. Zetaris runs in a **separate compose project** and
cannot resolve `datasvc`. The registration SQL would have embedded that hostname, the
`CREATE` would have succeeded, and every query against the table would then have failed.

That is precisely the failure the Zetaris HOWTO warns about — "a successful `CREATE`
alone does not confirm a usable table" — and it is slow to diagnose, because the symptom
appears one step away from the cause. Caught by reading the compose file against
`.env.example`, before Phase 3 existed to be broken by it. A validator now makes the
mistake impossible to reintroduce silently, with a test for both directions.

**Still unproven:** whether the Zetaris containers can reach `host.docker.internal:8100`
at all. That is the Phase 3 spike, with fallbacks in order: put datasvc on the Zetaris
compose network, MinIO/Parquet, then Postgres over JDBC.

## 2026-10-24 — `finish_reason` cannot be trusted to detect truncation **[live — Arpon's machine, 24 Oct]**

**Decision.** The Meterless adapter must detect a truncated response by comparing
`usage.completion_tokens` against the `max_tokens` we sent, **not** by reading
`finish_reason`. On truncation it must raise, not return the partial text.

**Why.** Same prompt, two budgets:

| `max_tokens` | `finish_reason` | `completion_tokens` | Output |
|---|---|---|---|
| 2048 | **`"stop"`** | 2048 (exactly the cap) | cut off mid-table, mid-sentence |
| 8192 | `"stop"` | 3001 | complete, ends on a full sentence |

`finish_reason` reported `"stop"` in **both** cases. A truncated answer is
indistinguishable from a complete one by that field alone. Left unchecked, the Writer
would emit half an evidence table and the Evaluator would validate truncated JSON as
if it were whole — exactly the failure the Evaluator exists to prevent.

The tell is `completion_tokens == max_tokens`. Treat that as truncation, always.

**Consequence for the agent loop.** Reasoning-heavy roles need a generous budget: a
single hard analytical prompt legitimately consumed **3001 completion tokens**. Combined
with the earlier finding that a one-word answer costs ~45 tokens, the rule is: never
set a tight cap, and always verify the response was not cut off.

---

## 2026-10-24 — The Nightshift race settings are a ceiling, not behaviour; disable the nondeterministic ones for reproducibility, not provenance **[live — Arpon's machine, 24 Oct, ~40 calls]**

**Context.** Nightshift's global Preferences expose race width (set to 6), optimistic
streaming, consensus escalation, adaptive compute, self-refine and answer fusion. The
worry was that these could put a non-Nemotron model into a request and weaken our
NVIDIA evidence.

**What the receipts actually show.** Across roughly forty calls, including a
deliberately hard analytical prompt chosen because that is when adaptive compute is
supposed to engage:

- **Race width is a ceiling, not a behaviour.** Observed `routing.width` of **1–2 out
  of 4 ready lanes**, never 6, and the router narrows itself by confidence
  (`reason: "confident-exploit"` → width 1; `"leaning"` → width 2).
- **`consensus.raced` was `1` on every single call.** One lane produces the answer. No
  multi-model race is happening in practice.
- **Every optional feature was null, every time:** `fusion`, `synthesis`, `refine`,
  `gen_verifier`, `debate`, `quality_race`, `reasoning_scaffold`, `test_time_compute`,
  `consensus_escalation`, `budget_degrade`. Self-refine is **not** firing on our calls.
- **One phase per response** (`final_synthesis`), one model. No draft-then-upgrade, so
  optimistic streaming is not splicing in another model.
- **`egress.destination: "nvidia"` on every call**, and every answering model was a
  Nemotron.

**So the provenance risk is low, for a reason unrelated to those settings:** all four
ready lanes are cloud Nemotron, no on-device model is cached, and `meterless/local`
returns `privacy_floor_blocks_all_routes`. Optimistic streaming has no local model to
draft with even if it fired.

**The real reason to turn them off is reproducibility.** The answering model still
alternates run to run between `nemotron-3.5-super-vl-120b-a12b` and
`nemotron-3.5-lightning-30b-a3b` on identical input. Our outputs must change with
*inputs*; they should not change randomly between identical runs, or `output_examples/`
and the demo become unexplainable. So before recording examples or demoing, disable the
nondeterministic features — and note in the README that the model can vary.

**Keep cross-check on.** It returned `status: "passed"` with
`recommended_action: "allow"` and per-check results for destructive actions, PII and
schema validity. That is free, provider-side governance evidence toward the
human-review requirement.

**Turn self-refine off anyway**, despite it not currently firing: if Nightshift ever
critiques and revises internally, our own Evaluator → Planner loop gets less credit and
the traces become harder to explain.

**Receipts are unsigned, confirmed.** `served: "in-tab"` and `receipt_envelope: null`
on every call, consistent with `meterlessd` answering 501 — the app window is serving
without a daemon signature. Signed receipts would be stronger evidence, so this is
worth a mentor question. Not blocking: `routed_model` and the rest of the receipt are
present either way.

**`syncTraceRetention` is not findable from outside the app.** It does not appear
anywhere in the Meterless repo, and Nightshift's application-support directory holds
only `keys.json` (the provider key — deliberately not opened). Settings live in the
app's own web storage, so Engineer mode / the command palette are the only route in.

## 2026-10-24 — Keep the pinned role→route mapping; it satisfies the NVIDIA rule but does not choose a lane **[live — Arpon's machine, 24 Oct, 24 samples]**

**Decision.** Keep sending a pinned disposition on every call — `METERLESS_MODEL_FAST`
and `METERLESS_MODEL_DEEP`, mapped by role in `app.config.lane_for()`, never `auto`.
Keep recording what actually answered. Do **not** claim the route selects the model.

**What was tested.** The full procedure: discover route ids from `GET /v1/models`, put
them in `.env`, map role→route in code, then verify from `response.model`. Eight
samples per route with distinct prompts to avoid cache hits.

| Requested route | Answered by | Samples |
|---|---|---|
| `meterless/fast` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |
| `meterless/deep` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |
| `meterless/auto` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |

**Two findings, and they point in opposite directions.**

1. **The NVIDIA requirement is satisfied.** 24/24 calls were answered by an NVIDIA
   Nemotron, and `response.model` names which one. By the test "if it shows a Nemotron
   id, the pin is working", it works.
2. **The route does not choose the lane.** `fast`, `deep` and `auto` are
   indistinguishable — all three converge on the same model, and every response still
   carries `mode_coerced: true`. There is nothing to pin *between*.

**Why an earlier test looked like the lanes differed.** A 3-sample run had
`meterless/fast` return `nemotron-3.5-lightning-30b-a3b` once and `super-vl-120b`
twice, which read as a real distribution difference. It was not: the receipt's
`routing` block shows `policy: "learned-router"` with `reason: "cold-explore"` and
`confidence: 0`. The router was exploring. Once it converged it chose `super-vl-120b`
every time regardless of route. **Three samples were not enough to tell exploration
from routing policy** — worth remembering before concluding anything else from a small
sample against this runtime.

This also corrects the earlier entry below, which inferred "pinning is not honoured"
from a single call per id. The direction was right, the mechanism was not: it is not
that a requested id is overridden arbitrarily, it is that **every mode is coerced to
`auto`** and one learned router decides.

**Where lane control would actually live.** Not in our code. The published API surface
is only `GET /v1/models`, `GET /healthz` and `POST /v1/chat/completions`, and none
takes a lane. The receipt exposes `app_policy{has_rule, lanes, race_width}` — `lanes`
is `null` for us and `race_width` is 6 — so Nightshift has a per-app policy concept
selected by our `meterless-app` header. Configuring it is a Nightshift-side action on
one machine, not a repo change. Arpon's Nightshift has lanes `deep-reasoner`,
`fast-tools` and `deep-verifier` defined, and **none of them appear in
`GET /v1/models`**, so they are internal fleet lanes, not addressable routes.

**What we therefore claim.** That every model call goes through Nightshift to an NVIDIA
Nemotron, and that we record exactly which one per request. Not that we direct a role
to a specific model. Re-test if a later Nightshift build exposes `app_policy.lanes` or
stops coercing the mode.

## 2026-10-23 — Record `routed_model`, not `provider_model`, as the model-per-request evidence **[live — Arpon's machine, 23 Oct]**

**Decision.** The trace field that names which model answered is
`meterless.routed_model` (cross-checked against `meterless.winning_route.model` and
the top-level `response.model`, which agreed on every observed call).
`meterless.provider_model` is **not** that field and must not be presented as it.

**Why.** On this build (Runtime `m1-m4`), `provider_model` returned `meterless/auto`
on every single call — including when a concrete `nvidia/...` id was requested and
when `meterless/deep` was requested. It reports the resolved *mode*, not the model.
Logging it as "which model handled this request" would be actively misleading, and the
NVIDIA award asks for the model.

---

## 2026-10-23 — Lane pinning is NOT honoured; fall back to dispositions **[live — Arpon's machine, 23 Oct — superseded in detail by the 24 Oct entry above]**

**Decision.** Abandon pinning concrete `nvidia/nemotron-*` ids to the FAST and DEEP
lanes. Use the dispositions (`meterless/fast`, `meterless/deep`) and record the model
the router actually chose, honestly, per request. Do not claim lane control anywhere
in the README, video or slides.

**Why.** Tested directly, one request per id:

| Requested | `routed_model` (actual) | Honoured? |
|---|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | `nvidia/nemotron-3.5-lightning-30b-a3b` | yes |
| `nvidia/nemotron-3-super-120b-a12b` | `nvidia/nemotron-3.5-lightning-30b-a3b` | **no** |
| `meterless/deep` | `nvidia/nemotron-3.5-super-vl-120b-a12b`, with `mode_coerced: true` | coerced to `auto` |

Every request runs through `routing.policy: "learned-router"` with `width: 6` — a race
across six lanes — and the router picks the winner. `app_policy.lanes` is `null` and
`race_width` is 6, so the app cannot currently constrain it. The one apparent match
above was coincidence: on that call `routing.predicted` was a *different* model from
the winner.

**Consequence, and why the NVIDIA story survives.** We cannot choose *which* Nemotron,
but every winner observed was an NVIDIA Nemotron (`winning_route.provider: "nvidia"`,
`kind: "cloud"`), because NVIDIA is the only configured cloud provider and no on-device
model is cached. So "a Nemotron answered, and here is exactly which one" stays
provable per request from the receipt; "we direct role X to Nemotron Y" does not.
Role-to-disposition routing (Planner/Executor → `fast`, Evaluator/Writer → `deep`)
stays in the code as our declared *intent*, and the trace records what actually
happened next to it. Recheck if a later Nightshift build exposes `app_policy.lanes`.

---

## 2026-10-23 — Never send a small `max_tokens` **[live — Arpon's machine, 23 Oct]**

**Decision.** Do not set a tight `max_tokens` on any Nightshift call. Leave it unset,
or set it generously (≥512) with an explicit comment saying why.

**Why.** `max_tokens: 16` made every call fail with HTTP 502 and
`meterless_detail: "nvidia/nemotron-3.5-lightning-30b-a3b_empty_response"`, which
reads like an outage and cost real debugging time. The cause is that these Nemotron
lanes spend hidden reasoning tokens before the visible answer: a one-word reply
("ready") consumed 42–49 completion tokens. A 16-token budget truncates the response
to empty before any content exists. Raising the budget turned the identical request
into a 200 with the content `"ready"`.

---

## 2026-10-23 — Capture the whole `meterless` receipt into the trace, not response headers **[live — Arpon's machine, 23 Oct]**

**Decision.** The adapter records the `meterless` object from the **response body** on
every call. `with_raw_response` for headers is not sufficient.

**Why.** `meterless-*` **response headers: none returned** on this build. The body
instead carries a `meterless.compute_receipt.v1` receipt, which is much richer than the
contract doc implies and gives us evidence we would otherwise have to fabricate:

| Receipt field | What it buys us |
|---|---|
| `routed_model`, `winning_route{model,label,provider,kind,tier}` | which Nemotron answered — the NVIDIA award evidence |
| `request_id`, `receipt_id`, `decision_id` | correlate our trace to Nightshift's own record |
| `phases[]{phase,model,ms,tokensIn,tokensOut,outputTps}` | per-phase latency and tokens |
| `usage`, `cost{actual_usd,naive_usd,baseline}`, `savings` | real efficiency numbers, not projections |
| `cross_check{status,checks[],requires_review,recommended_action}` | a provider-side safety gate (destructive-action, PII, schema checks) we can surface in the UI toward the human-review requirement |
| `egress{destination,sent,withheld,redacted}` | where the data went — supports the data-governance story |
| `routing{policy,width,predicted,winner,confidence,reason}` | how the lane was chosen; the basis for the pinning finding above |
| `privacy.path`, `cache.status`, `consensus`, `host_pressure` | context for honest reporting |

**Caveat.** This is one build's undocumented response shape, not part of the published
contract. The adapter must read it defensively (every field optional, no KeyError) and
degrade to `response.model` alone if the receipt is absent.

---

## 2026-10-23 — World Model merge band: 0.85, per the conformance runner

**Decision.** Implement `decide()` as **≥0.85 → auto-merge, ≥0.82 → review, else new**.

**Why.** The engine's own documents disagree. `docs/ingest-pipeline.md` specifies
≥0.92 auto-merge / 0.82–0.92 review / <0.82 new. But `conformance/runner.ts`
(`band-001`) asserts `decide(0.85)=="auto-merge"`, `decide(0.84)=="review"`,
`decide(0.82)=="review"`, `decide(0.81)=="new"`, and that matches the ≥0.85
name-similarity threshold in `AGENTS.md` §merge-detection. Both engine repos say the
conformance suite is the definition of done, so the runnable artefact wins over the
prose. The discrepancy is noted in the test itself so nobody later "fixes" it the
wrong way, and the check is not weakened to make anything pass.

---

## 2026-10-23 — One Zetaris REST table per silo, served whole at one URL

**Decision.** `datasvc` serves each synthetic silo complete at a single endpoint
(`GET /silos/<name>` → `{"records": [...]}`), not as paged pages. One
`CREATE LIGHTNING REST TABLE` plus one `CREATE SCHEMASTORE VIEW` per silo, and a
`CACHE TABLE` immediately after each table is created.

**Why.** A Lightning REST table binds **one fixed endpoint URL** with no paging
parameter, so paged pages would need one table per page. And the reference repo
records that a REST table may re-call its source on *every query* — a `CACHE TABLE`
cut one count from 49.7 s to ~1.2 s. Without caching, every agent query would re-hit
`datasvc` and runs would blow the 5–10 minute judging budget.

---

## 2026-10-23 — Our app reads `.env`; the reference scripts read `.env.local`

**Decision.** The app uses `.env` with the hackathon's official variable names. We do
not read `.env.local` anywhere in `app/`.

**Why.** `.refs/zetaris` deliberately refuses `.env` and reads only `.env.local`. That
is *their* convention. Keeping ours separate means running a reference script never
pulls our config, and our app never depends on a file the hackathon doesn't define.
If we ever run `.refs/zetaris/scripts/*` directly it needs its own `.env.local`.
