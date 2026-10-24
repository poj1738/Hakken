# Decisions

Decision, why, date. Newest first.

Anything discovered by observation rather than from a published contract is marked
**[live]** with **whose machine and when**, so a later reader can tell evidence from
assumption — and can tell a team-wide fact from one person's setup. A `[live]` finding
is one data point: it may not reproduce on your machine, on a different runtime build,
or after a provider update. Re-verify before depending on it, and add your own
observation rather than editing someone else's.

---

## 2026-10-24 — PBS reference data: PLAN §3's backbone is not publicly obtainable; the hand-built lexicon becomes the primary **[live, 24 Oct]**

PLAN §3 names "the PBS monthly *PBS API CSV files* ZIP (October 2026 bundle, about 5 MB)"
as the backbone, with the join spine
`PBS item code → AMT MP/MPP/TPP via amt-items → primary ATC via item-atc-relationships → APINCHS`.
**None of that is reachable without credentials.** Checked, in order:

| Source | Result |
|---|---|
| `data.pbs.gov.au` | 200, but states **"The legacy outputs have been discontinued. The PBS embargo API is now the only source of embargo data available."** The CSV bundle PLAN §3 relies on is gone. |
| `data-api.health.gov.au/pbs/api/v3/schedules` | **401** — `"Access denied due to missing subscription key"`, header `Subscription-Key`. Requires registration. |
| "Developer Downloads" on `data.pbs.gov.au` | "Available to all authorised users who have a **login** to the embargo downloads area." |
| `data.gov.au` — PBS **Item Report** (CC BY 3.0 AU) | Downloaded, 27 MB. Columns: `Year, Item_number, State, Scheme, Month, Patient_Category, Services, Benefits ($)`. **No drug names, no ATC codes, no strengths.** |
| `data.gov.au` — PBS **ATC Report** (CC BY 3.0 AU) | Downloaded, 207 KB. Columns: `Year, Month, State, ATC_Classification, Scheme, Services, Benefits ($)`, where `ATC_Classification` is an **ATC level-1 name** ("Alimentary Tract and Metabolism"). **No ATC codes, no item codes.** |
| `data.gov.au` — any PBS dataset with drug names or a Date of Supply file | Only three PBS datasets exist there (Item, ATC, Patient Category), all utilisation statistics. No Date of Supply. |

So the two open mirrors are **dispensing statistics**, not the schedule. Neither carries
`item_number → drug_name → ATC code`, which is the join the whole lexicon depends on.
That mapping exists only in the current schedule, behind the subscription key or the
embargo login.

**Decided: PLAN 11's named fallback becomes the primary** — *"the hand-built ~150-row
lexicon, marked as our own, using codes from the sample."* With one amendment: there is
no PBS sample to take codes from, so the ATC codes are written from general
pharmacological knowledge for a small set of common medicines. That is a defensible
position and it is **not** a redistribution of the WHO ATC/DDD index (which PLAN §3
forbids committing): it is roughly 80 individual, widely-published classification facts,
hand-entered, for drugs we chose. It is stated plainly in `docs/DATA_LICENCES.md` and the
README rather than implied to be PBS-derived.

**Consequences.**
- **No credential is introduced.** Pursuing the API would have added a
  `Subscription-Key` secret to manage, against the grain of "no credentials anywhere
  shared" (PLAN §9).
- **The licence question dissolves.** PLAN §3 and PLAN 11 both flagged the PBS licence as
  *unconfirmed* and made committing PBS-derived rows conditional on reading a `_meta`
  copyright block. Hand-built reference data is our own work under the repo's licence, so
  there is nothing to confirm and nothing to gitignore for licence reasons. The two
  CC BY 3.0 AU mirrors are declared in `docs/PREEXISTING.md` as *consulted and not used*.
- **`dos_weight` loses its real basis.** It was to come from PBS Date of Supply volumes.
  The Item Report has real volumes but no drug identity, so they cannot be attached to a
  named medicine. Weights are therefore hand-assigned on clinical plausibility and
  **labelled as such** — they only bias sampling toward common medicines, and no result
  depends on them being accurate.
- **Reduced from ~150 products to ~80.** The generator is now 40 patients at 5–12 meds
  (decided 24 Oct), so ~80 products covering the PLAN 4.4 condition bundles and every
  APINCHS class is ample. Padding to 150 would add hand-written content that nothing
  samples.
- `scripts/fetch_reference.py` is kept, and **documents this investigation and fails
  loudly with the reason** rather than being deleted. If someone obtains a subscription
  key later, the regeneration path is already written down.

**Honesty note for the README.** We should say that our medicines reference data is
hand-built and why, rather than claiming an open-data pipeline we do not have. The
synthetic *patients* were always synthetic; this makes the *medicines* our own work too.

---

## 2026-10-24 (later) — **Correction: Zetaris latency tracks bytes scanned, not a fixed per-query floor** **[live — Arpon's machine, 24 Oct]**

**This supersedes the central claim of the "Zetaris latency is the binding constraint"
entry below.** That entry says: *"This is per-query engine overhead, not data volume.
A `COUNT` on 789 rows costs ~4 s warm. Smaller synthetic silos will not make it
meaningfully faster — the floor stays."* **That is wrong, and it was wrong in the
direction that matters.** It was inferred from one table without checking a second.

Measured across four tables of very different size:

| Query | Rows | Approx. bytes | Time |
|---|---|---|---|
| `SELECT 1` | — | — | ~1.0 s |
| our union view, `COUNT(*)` | 4 200 | ~1.1 MB | **2.3 s** |
| `NY_TAXI.taxi_zones`, `COUNT(*)` | 789 | ~11 MB (14.2 KB/row — multipolygon geometry) | **17.0 s** |
| `NY_TAXI.taxi_trips`, `COUNT(*)` | 500 000 | ~50 MB | **164.2 s** |

Roughly **~1 s fixed + 2–3 s per MB scanned**, consistent across all four. The 789-row
table is slow because its rows are 14 KB each, not because 789 rows are expensive.
`taxi_zones` was the worst possible table to generalise from: it is the smallest by row
count and nearly the largest by volume, which is exactly what produced the false
"volume doesn't matter" reading.

**What this changes.**

- **Keeping the silos small and narrow is the primary latency lever**, not a
  nice-to-have. The previous entry said the opposite. A 200-patient dataset at ~1 MB
  per silo queries in 1–3 s.
- **A realistic run is ~4 queries × 2–3 s ≈ 10 s of Zetaris**, not minutes. The 5–10
  minute judging budget is comfortable, and Zetaris is **not** the dominant cost at our
  data size. Yesterday's "Zetaris, not the model, is the judging time budget" held only
  for the sample tables.
- **The `91.2 s` join from yesterday is explained**: it scanned `taxi_trips` against
  `taxi_zones`'s 11 MB of geometry. It was not evidence of a join penalty in general.
- **Column pruning does not avoid the scan.** A narrow two-column projection on
  `taxi_zones` took 15.3 s against 17.0 s for a full `COUNT(*)` — a 10% saving, not the
  order of magnitude a columnar format would give. So trimming Q1 to 12 columns helps
  the response payload, not the scan. **Generate less data; do not rely on selecting
  fewer columns from more.**

**What does not change.** The design decisions the earlier entry drove are still the
right ones, for reasons that survive the correction: no `JOIN`s at agent time (the
union view cannot be referenced twice anyway — see the spike entry), harmonise in
registered views, one batched verification query, a hard query budget. They are now
*prudent* rather than *forced*, and `ZETARIS_TIMEOUT_S=180` stays — 164 s on a 50 MB
table is exactly the kind of worst case it exists for.

**Method lesson, recorded because it caused the error.** One table, one shape, one
afternoon, generalised into an architectural constraint, written into `DECISIONS.md`,
`TODO.md` and `PROGRESS.md`, and reported as the finding of the day. The fix was a
single extra query against a second table. Before a measurement becomes a design
constraint, vary the thing you are claiming is irrelevant.

---

## 2026-10-24 — The reachability spike passed, and the whole REST→explode→view→union chain works **[live — Arpon's machine, 24 Oct]**

PLAN step 1. **No fallback is needed.** `datasvc` can sit on the host and Zetaris will
read it, which keeps `docker-compose.yml` as it is and retires the MinIO/Parquet and
Postgres-over-JDBC contingencies (PLAN 11).

**The network path.** A throwaway `python3 -m http.server 8100 --bind 0.0.0.0`, then
from inside the containers:

| From | Result |
|---|---|
| `zetaris-api-1` → `http://host.docker.internal:8100/records.json` | **HTTP 200 in 0.023 s** |
| `zetaris-driver-1` → same | **HTTP 200 in 0.020 s** |

That only proves the containers' own network. The part that matters is whether
Zetaris's **REST-table client** honours it, so the full chain was registered against
two throwaway silos (2400 and 1800 records, 643 KB and 479 KB):

| Step | Result |
|---|---|
| `CREATE LIGHTNING DATABASE MT_SPIKE` | ok, 0.52 s |
| `CREATE LIGHTNING REST TABLE … endpoint "http://host.docker.internal:8100/…"` | ok, 0.51 s |
| `SELECT * FROM MT_SPIKE.emr_raw` — **does Zetaris fetch our URL?** | **yes**, the records array came back |
| `CREATE SCHEMASTORE CONTAINER medtrace_spike` | ok, 0.10 s |
| `CREATE SCHEMASTORE VIEW … LATERAL VIEW explode(records) AS r` | ok, 0.34 s |
| `SELECT COUNT(*)` through the explode view | **2400**, 1.42 s |
| `CREATE SCHEMASTORE VIEW all_sources … UNION ALL …` | ok, 0.84 s |
| `SELECT COUNT(*) FROM medtrace_spike.all_sources` | **4200**, 2.34 s |
| **The real `q_identity_candidates()` output, run verbatim** | **23 rows, 2.63 s** |

**Three things this settles.**

1. **The union view registers, caches and queries.** PLAN 2.1 listed this as a spike
   and the fallback was four separate per-source views on a budget of 14. Not needed.
2. **`queries.py` generates SQL that Zetaris accepts.** The Q1 built by the real
   function — `IN` list of DOB spellings, nested `UPPER`/`LIKE` on three name columns,
   the anchor clause, 12-column projection — ran unmodified against a live union view
   over explode views, including `UPPER(name_family) LIKE 'O\'BR%'` against a real
   `O'Brien` row. That retires "no SQL here has touched Zetaris".
3. **The "reference the union view only once" rule is confirmed on *our* view shape**,
   not just the reference repo's. A self-join on `medtrace_spike.all_sources` failed
   with exactly the documented error:
   `MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION … attribute(s) "records"
   missing … in operator !Generate explode(records#13223)`. The error names `records`,
   the pre-explode array column — so the failure is in the explode, and **any** second
   reference breaks it, not just a self-join. `queries.py`'s no-subquery /
   no-window-function rule is therefore load-bearing, and a test asserts the view
   appears exactly once per template.

**`CACHE TABLE` is not the latency lever we assumed.** Measured either side of it on
the 4200-row union:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| before `CACHE TABLE` | 1.39 s | 1.66 s | 1.06 s |
| after `CACHE TABLE` | 2.01 s | 1.07 s | 1.33 s |

No measurable difference. The sponsor's 49.7 s → 1.2 s figure
(`REFERENCE_NOTES` 1.3) was a **rate-limited external API**; our `datasvc` is a local
HTTP server on the same machine, where a refetch of 643 KB is free. Keep
`CACHE TABLE` — it still stops a demo hammering `datasvc` on every query, and it is
harmless — but it is **not** the thing that makes runs fast, and the earlier
"`CACHE TABLE` mandatory" framing overstated it. The real lever was avoiding joins.

**A NULL is not a string.** `CAST(NULL AS STRING)` in a view came back as JSON `null`
(Python `None`), not `"null"` — see `REFERENCE_NOTES` 1.1. `parse.py` must treat it as
absent rather than stringifying it, or `name_previous`, `sex` and every other
source-specific null become the literal text `"None"` and read as present,
non-matching values in identity scoring and `evidence_state`.

**Cleanup.** `MT_SPIKE`, its two REST tables, `medtrace_spike` and its three views are
throwaway and dropped. There is **no SQL path to drop a SchemaStore container**
(`REFERENCE_NOTES` 1.3), so `medtrace_spike` may linger as an empty container; that is
cosmetic and does not collide with the real `medtrace` container.

**Method note for anyone repeating this:** my spike script's stdout was block-buffered
because it was not attached to a tty, so a long run looked like a hang with an empty
output file. Use `print(..., flush=True)` in anything whose progress you intend to
watch.

---

## 2026-10-24 — `''` is **not** an escaped quote in Lightning SQL; it silently deletes the apostrophe **[live — Arpon's machine, 24 Oct]**

**Use `\'` (backslash). Never `''` (doubled quote).**

The standard-SQL doubled quote does not escape in this dialect. It **closes one
string literal and opens another**, and adjacent literals are concatenated — so the
apostrophe is deleted, the quotes stay balanced, nothing raises, and the value is
quietly corrupted.

Measured directly:

| Statement | Returns |
|---|---|
| `SELECT 'O''Brien'` | `OBrien` — **length 6, not 7** |
| `SELECT LENGTH('' '' '' '')` (four quotes) | `0` |
| `SELECT 'AB' 'CD'` | `ABCD` — adjacent literals concatenate |
| `SELECT 'O\'Brien'` | `O'Brien` — correct |

And against real rows (`NY_TAXI.taxi_zones`, 789 rows, 2 zones containing an apostrophe):

| Predicate | Rows | Truth |
|---|---|---|
| `zone LIKE '%''%'` | **789 of 789** | pattern collapsed to `%%` |
| `zone LIKE '%\'%'` | **12** | correct |
| `zone = 'Eltingville/Annadale/Prince''s Bay'` | **0, no error** | silently wrong |
| `zone = 'Eltingville/Annadale/Prince\'s Bay'` | **3** | correct |

**Why this matters more than it looks.** For MedTrace it is a patient-safety bug, not
a style issue. `O'Brien`, `D'Souza`, `O'Connor` are ordinary Australian surnames. With
the doubled form the name reaches Zetaris as `OBrien`, matches nothing, and the
pharmacist is told **"GP: no record found" for a record that exists** — a fabricated
coverage gap, produced by a query that succeeded. No exception, no empty-result
warning, nothing in a trace to notice. It would have looked like a data problem.

**Decided:** `queries.sql_literal()` escapes `\` → `\\` then `'` → `\'`. Backslash is
escaped, not refused (the earlier code refused it, on the assumption that doubling the
quote was the safe path — the exact inversion of the truth). Verified to round-trip
every value these templates embed, and hostile input (`x' OR 1=1 --`, `x'; SELECT 1 --`)
comes back as an inert string rather than altering the statement. Semicolons and
control characters are still refused outright, because no template embeds free text and
refusing keeps the statement-level "one statement, no semicolon" guard sound.

**Caught by testing the dialect rather than trusting it.** The templates had been
written to the published SQL rules and a recorded response envelope, and reviewed, and
had 104 passing tests — one of which asserted the *wrong* escaping as correct. Nothing
short of sending the SQL to the engine would have found it.

**Also measured, same session** — the construct costs for a Q1-shaped predicate on 789
rows, which is the realistic shape of our identity-blocking query:

| Shape | Time |
|---|---|
| `COUNT(*)` with `IN ('a','b','c')` | 3.8 s |
| `COUNT(*)` with `UPPER(col) LIKE 'AST%'` | 8.1 s |
| `COUNT(*)` with `LIKE '%...%'` | 6.6 s |
| 4-column projection, full Q1-shaped `OR` chain (IN + LIKE + nested ORs) | **24.5 s** |
| 6-column projection, 789 rows, no `WHERE` | 9.5 s |

`UPPER()` and `LIKE` are not free, and the `OR` chain is the expensive part. At ~25 s
for Q1 the 8-query budget still fits the 5–10 minute judging limit, but with less room
than the plan assumed. Confirms the no-`JOIN` rule and makes trimming Q1 to the 12
identity columns (rather than all 25) worth keeping.

**Verified safe for `NULL`:** `UPPER(CAST(NULL AS STRING)) LIKE 'A%'` returns 0 rows
rather than erroring. Q1's `OR` chain over `name_previous` — null for three of the four
sources — depends on that.

---

## 2026-10-24 — Zetaris latency is the binding constraint on the whole design **[live — Arpon's machine, 24 Oct]**

> **⚠️ Superseded in part by the correction entry above (24 Oct, later).** The
> measurements here are accurate, but the conclusion drawn from them — *"per-query
> engine overhead, not data volume … smaller synthetic silos will not make it
> meaningfully faster"* — **is wrong.** Latency tracks bytes scanned (~1 s + 2–3 s/MB).
> `taxi_zones` is 789 rows of 14 KB each, so it is a large table that looks small.
> Read the correction before relying on anything below.

**Measured**, against the install's own `NY_TAXI` sample data:

| Query | Rows involved | Time |
|---|---|---|
| `SELECT 1` | — | ~1.1 s |
| `SHOW LIGHTNING DATABASES` | 2 | 0.15 s |
| `COUNT(*) FROM taxi_zones` | 789 | 20.7 s cold, then 11.2 / 3.9 / 6.1 s warm |
| `SELECT * ... LIMIT 5` | 789 | 5.8 / 3.4 / 3.7 s |
| 2-table `JOIN` + `GROUP BY` | ~8 k ⋈ 789 | **timed out once, then 91.2 s** |

**This is per-query engine overhead, not data volume.** A `COUNT` on 789 rows costs
~4 s warm. Smaller synthetic silos will not make it meaningfully faster — the floor
stays. It is Lightning/Spark planning and dispatch on every REST call.

**Decisions that follow.**

1. **`ZETARIS_TIMEOUT_S` raised from 60 to 180.** 60 was below the observed worst case:
   the 91 s join would have failed, and one attempt timed out outright. A too-low
   timeout would have read as "Zetaris is broken" rather than "the query is slow".
2. **`CACHE TABLE` after registration is mandatory, not an optimisation.** Already
   required because a REST table re-calls its source per query; now doubly so.
3. **Push joins into `CREATE SCHEMASTORE VIEW` at registration time.** Agents should
   query flat, pre-joined views, not compute joins live. A 91 s join inside an agent
   loop is unaffordable; the same join computed once at setup costs nothing per run.
4. **The Evaluator must batch verification.** Re-deriving each cited number with its
   own query — the obvious implementation — is the single easiest way to blow the
   judging budget. One query returning all the figures to check, not one per claim.
5. **The orchestrator needs a per-run query budget**, not just `MAX_AGENT_ITERATIONS`.
   At ~4 s per trivial query, 30 queries is 2 minutes of pure latency before any model
   call. `RUN_TIMEOUT_S=600` must cover Zetaris time, model time and retries together.
6. **Keep the synthetic silos genuinely small** and prefer `LIMIT`-ed reads.

**Why this matters for judging.** The brief requires a run that finishes in 5–10 minutes
on a CPU-only machine. Model calls are fast (~0.4–1.2 s to a Nemotron). **Zetaris, not
the model, is the latency budget.** Any design that issues joins per claim fails that
requirement on timing alone, with correct code.

Re-measure on each machine: these numbers are from one install under Docker Desktop on
Apple Silicon, with the driver sharing the host.

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
