# Reference notes

What the sponsor reference repos actually require of us. Read from `.refs/zetaris`
(github.com/zetaris/getting-started) and `.refs/meterless`
(github.com/Meterless/Meterless), both cloned `--depth 1` and gitignored.

Two kinds of statement are mixed here, and the difference matters:

- **Unmarked** — read from a published contract or reference repo. Applies to everyone.
- **[live — Arpon's machine, 23 Oct]** — *observed on Arpon's machine on 23 Oct 2026*, against his Zetaris
  2.4.3.1 install and his Nightshift build `m1-m4`. One machine, one day, one build.
  It may not reproduce on yours. **Re-verify before depending on it**, and add your own
  observation rather than overwriting his.

Nobody else has run either service yet — see `docs/ENVIRONMENTS.md`.

Rule of thumb from both repos: the spec documents intent, the **conformance suite /
live response is binding**. Where they disagree, follow the runnable artefact and
record the discrepancy here.

---

## 1. Zetaris (data layer)

### 1.0 One machine's state — not a team-wide fact **[live — Arpon's machine, 23 Oct]**

On **Arpon's machine** the stack was up and verified on 23 Oct 2026;
`scripts/preflight.py` reported 22 pass / 0 fail there. It has since been shut down, so
that result is stale, and **no other teammate has run Zetaris at all.** The findings
below describe that one instance:
`SELECT 1` returns `1`, `GET /datasource/datasources` returns 200, and
`SHOW LIGHTNING DATABASES` lists two pre-existing sample databases.

History worth keeping, because it misled us once: before `docker compose up -d` the
machine had zero containers and zero volumes, which is **indistinguishable from a
pruned install**. It was simply never started — the `docker compose pull` was still
running. Zero containers before `up -d` is the expected condition, not evidence of
loss. Arpon owns `up -d`, `verify.sh` and API-key creation; we only talk to the
instance over REST.

**Pre-existing data on *that* instance** (yours may differ, and a fresh install's
sample data is whatever the sponsor's bundle ships)**:** `NY_TAXI` (15 tables: trips, drivers,
customers, surge_pricing, taxi_zones, ...) and `TPCDS_DB` (308 tables). These shipped
with the sponsor's install, so they predate the build window and are declared in
`docs/PREEXISTING.md`. Our own synthetic silos will be separate Lightning databases.

### 1.1 The REST call shape — binding

From `.refs/zetaris/scripts/zetaris_sql.py` (`RestChannel`):

```
POST {ZETARIS_REST_URL}/sql-editor/sqls/run
headers: Authorization: Bearer <ZETARIS_API_KEY>
         X-Org-ID: <ZETARIS_ORG_ID>          # numeric org ID, 1 on a local install
         X-Request-ID: <fresh uuid4>
         Content-Type: application/json
body:    {"queryId": "<uuid4>", "sql": "<ONE statement, no trailing ;>",
          "source": "SqlEditor", "limit": <n>}
```

**The envelope, resolved against a live instance [live, 2026-10-23]:**

```json
{
  "headers": ["col", ...],      // column names, positionally aligned with each row
  "data":    [["v", ...], ...], // rows as positional lists
  "total":   2,                 // row count
  "timeUsed": 294               // milliseconds
}
```

Column names live in **`headers`**, zipped positionally with each row in `data`. The
reference client discards everything but `data`, which is why this had to be observed
rather than read. Recorded fixtures are in `tests/fixtures/zetaris/`.

**Every value arrives as a string**, confirmed directly: `SELECT 1` yields `"1"`,
`2.5` yields `"2.5"`, `true` yields `"true"`. The adapter must cast, and the Evaluator
must cast before re-deriving any cited number. An empty result is `data: []` with
`total: 0` and populated `headers` — **not** an error.

The same envelope is used by `SHOW` and `SELECT` alike, so one parser covers both.

Error meanings (from `AGENTS.md` and the troubleshooting tables):
- `401` → bad `ZETARIS_API_KEY` (regenerate in the UI; shown in plaintext once).
- `400 Not Allowed` → `X-Org-ID` is not the numeric org ID.
- `400` on a valid statement → `queryId` / `X-Request-ID` are not UUIDs.
- `Operation not permitted` before any HTTP status → sandbox network restriction,
  **not** a credential failure. Do not "fix" it by changing the URL or key.

### 1.2 SQL rules that constrain our agents

- **Lightning SQL only.** Not Spark SQL, not Hive SQL. Never start a local Spark session.
- **One statement per REST call, no trailing semicolon.** Qualified names: `<source>.<table>`.
- Values come back as **strings**, and decimals may use exponent notation. Cast and
  convert before comparing — this directly affects the Evaluator's number re-derivation.
- `SHOW DATASOURCES` does **not** list REST or file registrations. Use
  `SHOW LIGHTNING DATABASES` for those. Our schema discovery must use both.
  **Confirmed [live — Arpon's machine, 23 Oct]:** on this instance `SHOW DATASOURCES` returns **0 rows** while
  `SHOW LIGHTNING DATABASES` returns `NY_TAXI` and `TPCDS_DB`. Discovery that relied on
  `SHOW DATASOURCES` alone would conclude the instance is empty.
- `SHOW TABLES IN <db>` works and returns
  `headers: ["table_identifier", "catalog_name", "catalog_type"]`, with the identifier
  already qualified (`NY_TAXI.taxi_trips`). That is the catalogue the Planner sees.
- Referencing the same `UNION ALL`-of-`explode()` view twice in one query fails with
  `MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION`. Use a window function
  in one pass instead of a self-join or an `IN`/`HAVING` subquery.
- `DESCRIBE BY "..."` accepts letters, digits, spaces and `_ . - ,` only.
  Parentheses, slashes and colons fail validation.

### 1.3 Registering our synthetic silos

The REST-table recipe we copy is
`.refs/zetaris/open_data/rest_apis/sql/non_rate_limited/02_pokeapi_create.sql`:

```sql
CREATE LIGHTNING DATABASE <DB> DESCRIBE BY "<plain description>";
CREATE SCHEMASTORE CONTAINER <container>;
CREATE LIGHTNING REST TABLE <tbl> FROM <DB> REQUEST(
    endpoint "<url>", method "get", response_type "json", http_encoding "URLENCODED"
) HEADER ( ) BODY ();
CREATE SCHEMASTORE VIEW <view> WITH CONTAINER <container> AS
SELECT ... FROM <db>.<tbl> LATERAL VIEW explode(<array_field>) AS r;
```

Consequences for our `datasvc` design:

- A REST table binds **one fixed endpoint URL**. There is no paging parameter, so each
  silo must be served whole at one URL (`GET /silos/<name>` returning
  `{"records": [...]}`), not as paged pages. One table + one `explode` view per silo.
- `CREATE SCHEMASTORE CONTAINER` has **no `IF NOT EXISTS`** — a re-run fails on the
  duplicate. `scripts/register_sources.py` needs `--skip-exists` to tolerate this.
- **A REST table may re-call its source on every query.** On one reference source a
  `CACHE TABLE` cut a count from 49.7 s to ~1.2 s. We must `CACHE TABLE` each raw
  silo table right after creating it, or agent runs will be slow and hammer `datasvc`.
- `CREATE LIGHTNING DATABASE <db>` must exist before any `FROM <db>` reference.
- Teardown: `DROP VIEW <container>.<view>` works; `DROP LIGHTNING DATABASE TABLE` and
  `DROP LIGHTNING DATABASE` worked on 2.4.3.1. There is **no SQL path to drop a
  container** — that is a Data Explorer / API action.

### 1.4 Verification discipline (non-negotiable per the HOWTO)

For every registered table: `SELECT COUNT(*)` in Zetaris, then count the same array
straight from the source, and compare before trusting anything. A successful `CREATE`
does **not** prove a usable table — the reference repo has sources that register fine
and then fail every query.

### 1.5 Safety rules we inherit

Read-only first (`SHOW` / `DESCRIBE` / `SELECT`). Dry-run every create script and get
an explicit go-ahead. Never call **port 8889** on a local instance. Keys never go in
prompts, logs, source files, commits or URLs.

### 1.6 Naming difference to watch

The reference repo reads **`.env.local`** and refuses `.env`. Our app uses **`.env`**
(the hackathon's official variable names). If we ever run `.refs/zetaris/scripts/*`
directly it will need its own `.env.local`; our code must not depend on that file.

---

## 2. Meterless Nightshift (primary AI provider)

### 2.1 The Power contract — implement exactly

From `.refs/meterless/docs/agent-ready/add-meterless-provider.md` (Runtime 0.90.0):

| Rule | Detail |
|---|---|
| Base URL | Default `http://127.0.0.1:8088/v1`. Accept a pasted URL with or without scheme, `/v1`, `/v1/chat/completions`, `/v1/models` or `/healthz`; normalise to `<host>/v1`. **Never produce `/v1/v1`.** |
| Auth | `Authorization: Bearer <token>` on **every** call. The placeholder `rt-local` is rejected. Store under the key `meterless_runtime_token`. |
| Headers | `meterless-app: <stable lowercase app id>` on every request; `meterless-scope: user` on chat. |
| Model ids | Routing **modes**, not models: `meterless/<disposition>`, `meterless/<class>`, `meterless/<class>.<disposition>`. Read them from `GET /v1/models` and **keep any `meterless/*` id you don't recognise**. |
| Status | `/healthz` only proves the process is up. **`GET /v1/models` decides**: 401/403 → `unauthorized` (show a token field); 200 with meterless ids → `online`; anything else → `offline`. |
| Auto Detect | Ports 8088, 8090, 8787, 11434 on `127.0.0.1`, `localhost`, `[::1]`; save the first online-or-unauthorized hit. |
| Plain text | Text requests stay a **string**, exactly like OpenAI. |
| Timeout | **180 s** — a cold model load can take minutes. Short timeouts read as false outages. |

Definition of done (the contract's own): a wrong token shows `unauthorized` not
`offline`, Auto Detect finds the runtime, and a plain-text request on `meterless/auto`
returns a string.

### 2.2 What one runtime actually returned **[live — Arpon's machine, 23 Oct]**

Arpon's build `m1-m4`, served at `http://127.0.0.1:8088`, `engine_ready: true`. The
model list and lane behaviour below are **that machine's configuration**: his Nightshift
has lanes `deep-reasoner`, `fast-tools` and `deep-verifier`, all cloud Nemotron with no
local models. A teammate's runtime will expose a different set. **Never write code that
assumes a lane name or a specific model id exists** — read `GET /v1/models` at runtime.

- `GET /healthz` → 200, and reports `providers.cloud.keys: ["nvidia"]`, so an NVIDIA
  key **is** configured in Nightshift. It also warns no device model is cached yet.
- `GET /v1/models` with no token and with `rt-local` → **401** with
  `{"error":{"code":"unauthorized",...}}`. The contract's `unauthorized` state is real
  and testable, exactly as specified.
- `GET /v1/models` with the real Runtime token → **200**, state `online`.

**The models list is bigger than the contract implies.** It returned 22 entries in
three families, not just dispositions:

| Family | Count | Ids |
|---|---|---|
| `meterless/*` dispositions | 6 | `auto`, `fast`, `deep`, `cheap`, `local`, `fusion` |
| `nvidia/*` Nemotron cloud lanes | 8 | `nemotron-3.5-super-vl-120b-a12b` (tier C, 1 M ctx), `nemotron-3.5-lightning-30b-a3b` (A, 262 k), `nemotron-3-ultra-550b-a55b` (C, 1 M), `nemotron-3-super-120b-a12b` (B, 262 k), `nemotron-3-nano-30b-a3b` (A, 131 k), `llama-3.1-nemotron-ultra-253b-v1` (C, 131 k), `llama-3.3-nemotron-super-49b-v1.5` (B, 131 k), `nemotron-3-embed-1b` (A, embeddings) |
| `webllm/*` on-device | 8 | Llama 3.2 1B/3B, Qwen 2.5 1.5B/3B/Coder-3B, Gemma 2 2B, Phi 3.5 Mini, SmolLM2 1.7B |

Each entry carries a `meterless` block: dispositions have `mode`/`name`/`description`;
concrete lanes have `kind` (`cloud`/`local`), `tier` (A/B/C), `context` and `price`
(all `0` per million for the Nemotron lanes). **No `meterless/<class>` ids exist on
this build**, so `meterless/fast` and `meterless/deep` are the only disposition-level
handles, and the concrete `nvidia/nemotron-*` ids are the only way to name a specific
Nemotron.

### 2.3 Trace evidence lives in the response **body**, not the headers **[live — Arpon's machine, 23 Oct]**

`meterless-*` **response headers: none returned.** Instead every response carries a
`meterless` object, which on a failed call looked like:

```json
"meterless": {"request_id": "chatcmpl-...", "requested_model": "nvidia/nemotron-3-nano-30b-a3b",
              "provider_model": "meterless/auto", "app": "hakken-agent",
              "mode": "auto", "scope": "user"}
```

So the adapter must capture `response.model` **and** this `meterless` body block
(`request_id`, `requested_model`, `provider_model`, `mode`, `scope`) into the trace.
That is our NVIDIA-award evidence. Using `with_raw_response` for headers alone would
record nothing on this build.

**Resolved on a successful call: lane pinning is NOT honoured.** `provider_model`
returns `meterless/auto` on every call regardless of what is requested — it reports the
resolved *mode*, not the model. Requesting `nvidia/nemotron-3-super-120b-a12b` was
served by `nemotron-3.5-lightning-30b-a3b`; `meterless/deep` came back with
`mode_coerced: true`. Every request races six lanes under
`routing.policy: "learned-router"`. The field that names the actual model is
`routed_model` / `winning_route.model`. Full evidence and consequences in
`docs/DECISIONS.md`; the receipt shape is in §2.6 below.

### 2.4 Provider-key blocker — found and fixed **[live — Arpon's machine, 23 Oct]**

Initially **every** chat completion failed with HTTP 502 wrapping
`meterless_detail: "nvidia_401: {...\"detail\":\"Invalid unsecured/JWS/JWE header:
Invalid JSON object\"}"` — NVIDIA rejecting the key stored in Nightshift, while our
Runtime token was fine (it had authenticated `/v1/models`). Replacing the key in
**Nightshift → Setup → Providers** fixed it; calls now return 200. `meterless/local`
separately returned `privacy_floor_blocks_all_routes`, a Nightshift privacy setting,
with no on-device model cached.

Diagnostic worth keeping: an upstream provider failure surfaces as **our** 502, so
always read `error.meterless_detail` before blaming our own code. The prefix names the
real culprit (`nvidia_401`, `privacy_floor_blocks_all_routes`,
`<model>_empty_response`).

### 2.6 The compute receipt **[live — Arpon's machine, 23 Oct]**

A successful response's `meterless` block is a `meterless.compute_receipt.v1`, far
richer than the contract doc implies, and it is where our sponsor evidence comes from:
`routed_model` and `winning_route{model,label,provider,kind,tier}` (which Nemotron
answered), `request_id`/`receipt_id`/`decision_id`, `phases[]` with per-phase model and
tokens, `usage`, `cost{actual_usd,naive_usd,baseline}` and `savings`, `cache.status`,
`privacy.path`, `egress{destination,sent,withheld}`, `routing{policy,width,predicted,
winner}`, `consensus`, `host_pressure`, and a provider-side
`cross_check{status,checks[],requires_review,recommended_action}` safety gate.

It is an undocumented, build-specific shape, so read it defensively — every field
optional, and degrade to `response.model` alone if the receipt is missing.

**Operational trap:** do **not** send a tight `max_tokens`. These lanes spend hidden
reasoning tokens, so a one-word answer cost 42–49 completion tokens; `max_tokens: 16`
truncated it to nothing and failed as `<model>_empty_response`, which reads like an
outage. Leave it unset or ≥512.

### 2.5 Structured output

Do **not** depend on native tool-calling: support through Nightshift to Nemotron is
unverified on this build. Default to "respond with JSON matching this schema",
validate with pydantic, allow exactly one repair retry, then a structured error.

---

## 3. H-MEM engine (`.refs/meterless/engines/hmem`)

`AGENTS.md` is the spec; `conformance/runner.ts` + `conformance/vectors/vectors.json`
are the definition of done ("green scorecard"). 13 checks across 7 sections:
`record-validation` (2), `feedback-deltas` (5), `ranking-order` (2),
`sleep-guardrails` (1), `conflict-gate` (1), `ledger-audit` (1), `dream-boundary` (1).
Vectors pin `clock: 1750000000000`. All 13 translate cleanly to pytest — none depends
on TypeScript semantics.

Exact-tier numbers we must match:

- **Hybrid retrieval score** (spec §6.1), the one formula the suite leans on:
  ```
  raw = 0.35·semantic + 0.20·keyword + 0.10·tag + 0.10·domain
      + 0.15·entity   + 0.05·layer   + 0.05·recency − 0.20·superseded
  score = clamp01(raw) × confidence
  ```
  keyword = Jaccard over the top-8 query tokens; layer weights long_term 1.0 /
  working 0.8 / short_term 0.6; recency = exponential decay on `lastAccessed` with a
  ~14-day constant; `superseded` = 1 when `supersededBy` is set.
  Threshold **0.35 on the final score**, top-N **5**.
  Absolute scores are **not** asserted (they depend on the embedder) — only the
  ordering the spec makes embedding-independent.
- **Feedback deltas** (§9.2): helpful `+0.05` confidence **and** `accessCount +1`;
  not_helpful `−0.03`, no access change; wrong `−0.20` **plus a `review` tag**. All
  clamped to [0, 1] — the vectors test both clamps.
- **Record validation**: a record with **no `source` must be rejected by
  construction**. `confidence` and `source` are both mandatory.
- **Ledger** (§9.1): append-only, 17 canonical action types. `feedback` entries must
  carry `previousState.confidence` and `newState.confidence`, and
  `ledger.history(id)` must return actions in order (`["create", "feedback"]`).
- **Sleep** (§8): `preview()` must **not mutate the store**; guardrail-protected
  records (derived / superseding / relationship hubs) must never be archived or
  deleted; `execute()` must return a non-empty `backupId`. Archive threshold is
  ≥30 days old **and** accessCount ≤2 **and** unreferenced.
- **Conflicts** (§10): an `always`/`never` pair on similar content must be detected;
  auto-resolve only at decision confidence **≥0.70**, else queue; the loser is marked
  `supersededBy` and **kept** — resolution must **never delete** a record.
- **Dreaming** (§7): must produce ≥1 proposal from two related preferences, and must
  **materialise nothing before approval**; an approved proposal becomes `long_term`
  with non-empty `derivedFrom`.

Required surface (per the conformance README): an `HMEM` class taking `{ clock }`,
with `add`, `query`, `feedback`, plus `store`, `ledger`, `sleep`, `dreaming` and
`conflicts` services. Our Python port keeps those names so the mapping to the official
runner is one-to-one and auditable.

Caps: 10 entities and 5 `relatedTo` links per memory.

---

## 4. World Model engine (`.refs/meterless/engines/world-model`)

`conformance/runner.ts` has **no vectors file** — its 8 cases are inline: `sid-001`,
`sid-002`, `band-001`, `prov-001`, `idem-001`, `idem-002`, `bitemp-001`, `audit-001`.
Required exports: `WorldModel`, `entityIdFromName`, `normalizeName`, `decide`.

- **Stable ids** (`docs/stable-ids.md`): externally keyed entities use
  `"{type}:{system}:{externalId}"`; name-keyed use
  `ent_ + sha256(f"{type}:{normalizeName(name)}").hexdigest()[:16]`.
  `normalizeName` = lowercase → **NFKD** → strip combining marks → collapse
  whitespace → trim. The suite checks `"José  García"` (with an NBSP) normalises to
  `"jose garcia"`, that `"Acme Corp"` ≠ `"Acme Corporation"` (no over-normalisation),
  and that **type participates in the key** (`person:x` ≠ `org:x`).
  Context ids include the parent; relationship ids hash `from+type+to+context?+validFrom?`.
- **⚠ Merge bands — the specs disagree, and the suite wins.**
  `docs/ingest-pipeline.md` says ≥0.92 auto-merge / 0.82–0.92 review / <0.82 new.
  `conformance/runner.ts` asserts `decide(0.85)=="auto-merge"`, `decide(0.84)=="review"`,
  `decide(0.82)=="review"`, `decide(0.81)=="new"`, matching the **≥0.85** name-similarity
  threshold in `AGENTS.md` §merge-detection. **Implement `decide` as ≥0.85 auto-merge,
  ≥0.82 review, else new**, note the discrepancy in `docs/DECISIONS.md`, and never
  weaken the check to make a test pass.
- **Provenance is mandatory**: a write with no `source` must be rejected
  (`prov-001`). Provenance is `{kind, url?, at, checksum?}`, attached at normalize and
  enforced at validate.
- **Idempotency** must be real and falsifiable: re-ingesting the same batch reports
  `changed == false` and leaves `stateShapeCanonical()` byte-identical (`idem-001`);
  one edited observation reports `changed == true` and a different shape (`idem-002`).
  So we need a canonical state serialiser and a content-addressed dedupe key.
- **Bitemporal edges**: a superseding `relate()` closes the previous edge;
  `neighborsOf(id, {via, at})` must answer as of a past timestamp (`bitemp-001`).
- **Audit**: every mutation appends an entry with a **strictly increasing** `seq`
  (`audit-001`).
- Merges are never destructive: the loser becomes an **alias** that still resolves.

The six-stage write path is extract → normalize → resolve → validate → append →
project, each stage idempotent and resumable.

---

## 5. Optional engines (skimmed, not planned yet)

- **Markovian** — chunked reasoning: each step sends only the goal summary plus
  compressed carryover state, so per-step context is ~O(1) in chain length instead of
  cumulative O(n²). Has a marker protocol, run/step records, cumulative stats and
  reference token-efficiency formulas (§6) we could log as projected-vs-actual savings
  on one long investigation. Has its own `conformance/runner.ts`.
- **Scout Intent** — a pre-flight decision layer: sense intent (scored, multi-label) →
  check risk (prompt injection, policy, scope drift) → route tools → select a model →
  emit a signed execution contract. Note it is **spec-only by design** (no `src/`), and
  it is verified by an **eval harness** rather than a conformance runner.

---

## 6. The starter's shape (`.refs/meterless/templates/agentathon-starter`)

A CLI whose memory *is* H-MEM, and the judging hint is explicit: it publishes a table
mapping each user-facing command to the named engine service and spec section
(`remember` → MemoryMiningService §4/§3, `ask` → MemoryRetrievalService §6,
`audit` → TrustLedgerService §9, `sleep` → SleepCycleService §8). It notes the rubric
weights engine usage heavily and says "nothing is faked". We should publish the same
kind of table in `docs/SPONSOR_TECH.md`, pointing at our own code paths and tests.
It also runs retrieval-only with **no API key** by default and labels which mode
produced each answer — the same honesty our `SAMPLE_MODE` needs.
