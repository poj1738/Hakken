# Progress

One file, current state only. Overwrite it as things change — the history lives in
`docs/HANDOFF.md` and in git. Read this first at session start.

**Last updated:** 2026-10-25 01:20 AEDT by Arpon

## Status

**The track is decided: MedTrace**, medication reconciliation across four siloed
systems. Roles, contracts and today's hour-by-hour plan are in
`docs/PLAN_2026-10-24.md` — read it before starting work.

Phase 1 is complete. Of the MedTrace build, the domain-pack contract exists and is
frozen; nothing downstream of it is built yet.

| Area | Owner | State |
|---|---|---|
| Preflight (`make preflight`) | — | working — **22 pass / 0 fail on Arpon's machine, 23 Oct** (his services only; re-run it on yours) |
| Config layer (`app/config.py`) | — | working — validated, secrets as `SecretStr`, `ZETARIS_TIMEOUT_S` 180 |
| Secret scan + pre-commit hook | — | working, verified to block a commit |
| Tests | — | **456 green** on any machine — no services, isolated from any local `.env`. Verified on a fresh clone under Python 3.11 (CI's version), and the suite now changes **0 tracked files**: it used to regenerate `data/synthetic/` and the committed fixtures in place |
| Team workflow, CI, onboarding | — | working |
| **MedTrace contract** (`app/domain/packs/medtrace/types.py`) | Arpon | **frozen, on `main`.** Shared file — changes need sign-off, a HANDOFF entry and a PR line |
| **SQL templates** (`queries.py`) | Arpon | **written and run live** — the real Q1 executed verbatim against a union view on 24 Oct. Q4 (TGA) deliberately unwritten |
| `identity.decide()`, `SOURCE_TRUST_PRIORS` | Arpon | **real and usable today** |
| Clinical logic — `parse`, `safety`, `identity`, `normalise` | Arpon | **implemented** (PLAN step 7). `parse` is tested against fixtures proven byte-identical to the live views. `identity`: precision 1.000, recall 0.952, **0 false merges**. `normalise`: daily dose 977/977 |
| Clinical logic — `coverage`, `supply`, `fuse`, `detect`, `triage` | Arpon | **skeleton** — exact signatures, every body raises `NotImplementedError("Arpon: <file>")` |
| Reference data (PBS lexicon, APINCHS, nicknames) | Arpon | **done** — 224 lexicon rows, **203 with a real PBS code** (schedule 4751). Hand-built clinical content, real codes joined in. The lexicon also carries each item's real PBS pack quantity and repeats, which the generator now reads |
| `docs/DATA_SPEC.md` | Arpon | **on `main`** (#5), names aligned to the plan and the frozen types |
| Synthetic generator, ground truth, fixtures | Arpon | **done** — 40 patients, 61 planted findings, identity traps, **30 Zetaris envelopes** for `SAMPLE_MODE`. Dispensing rebuilt on real PBS pack sizes (max 14 fills/year, median 5) |
| `datasvc/` | Arpon | **done** — 7 endpoints, whole-table `{"records": [...]}` |
| TGA shortages (`scripts/load_tga_shortages.py`) | Arpon | **parses** — 1,010 rows, 514 notifiable, impact rating Critical 90 / Medium 178 / Low 742. **Not registered**; Q4 is optional and `q_shortages` still raises |
| `scripts/register_sources.py` | Arpon | **APPLIED live.** 7 of 8 views verified — counts match `datasvc` exactly and all 6 live-vs-fixture diffs match. **`medtrace.nicknames` is broken** (see Blocked on). `all_sources` = 2 898 rows in ~2 s |
| Zetaris / Meterless adapters | Arnav | **stub** — both unblocked, contracts fully known |
| Orchestrator, agents, API, trace | Arnav | not started |
| H-MEM, World Model | Arnav | not started — World Model first, `identity.decide` waits on it |
| Web UI | Anshu | not started |
| Docker run path | — | not started — the Dockerfile has never been built |

## Observed on Arpon's machine (one machine, one day — not team-wide)

Nobody else has run the services yet (`docs/ENVIRONMENTS.md`). **Run `make preflight`
on your own machine** rather than trusting this. API behaviour that holds everywhere is
in `CLAUDE.md`.

- **Zetaris latency tracks bytes scanned: ~1 s + 2–3 s per MB** [24 Oct, corrected].
  `SELECT 1` ~1.0 s; our 4 200-row union view 2.3 s; `taxi_zones` (789 rows but
  14 KB each, ~11 MB) 17.0 s; `taxi_trips` (500 k rows) 164.2 s. **An earlier
  conclusion that this was a fixed per-query floor and that smaller silos would not
  help was wrong** — it generalised from one fat table. At our data size (~1 MB per
  silo) a query is 1–3 s and a run costs ~10 s of Zetaris, well inside the budget.
  Keeping the silos small is the main lever; column pruning saves payload, not scan.
  The design rules still hold (no joins at agent time, budget 8, harmonised views,
  one batched verification query) — now prudent rather than forced. See
  `docs/DECISIONS.md`.
- **Zetaris** answering on `localhost:8888`, envelope `{headers, data, total, timeUsed}`,
  **every value a string**. Catalogue discovery needs `SHOW LIGHTNING DATABASES` +
  `SHOW TABLES IN <db>`; `SHOW DATASOURCES` returns 0 rows.
- **Nightshift** `online`. `meterless/auto` was answered by
  `nvidia/nemotron-3.5-super-vl-120b-a12b`. **Lane pinning was not honoured** on this
  runtime (build `m1-m4`) — record `routed_model`, never `provider_model`.

## Blocked on

**One thing, and it needs Arpon: `medtrace.nicknames` fails every query in Zetaris.**

A Lightning REST table infers its schema **once, at creation**, and keeps it —
`REFRESH TABLE` returns ok and changes nothing. `MT_REF.nicknames_raw` inferred
`struct<canonical, variant>` before `sex` was added, so it now reads rows wider than
its schema and Spark throws `ArrayIndexOutOfBoundsException`. A stale cached copy hid
this for a day. The fix drops and re-creates that one already-broken table:

```bash
python3 scripts/register_sources.py --recreate-drifted
```

Nothing else waits on it: nicknames only affects fuzzy given-name matching, and
`identity.py` builds its own nickname map in `parse.py`. The other 7 views are green
and all 6 live-vs-fixture diffs match.

**Generalise from it:** adding a column to any generated file silently breaks its
REST table the same way, and you will not see it until the cache is dropped.
`--recreate-drifted` detects that case for every table.

**The three largest risks were closed on 24 Oct** by the step-1
spike (`docs/DECISIONS.md`):

1. ~~Can the Zetaris containers reach `host.docker.internal:8100`?~~ **Yes** — HTTP 200
   in ~20 ms from both `zetaris-api-1` and `zetaris-driver-1`, and a real REST table
   pointed at that URL fetched our data. The MinIO/Parquet and Postgres-over-JDBC
   fallbacks are retired.
2. ~~Does the union view register, cache and query?~~ **Yes** — `UNION ALL` over two
   `explode()` views: 4 200 rows, 2.3 s. The four-separate-views fallback is retired.
   Confirmed on our own view shape that it **cannot be referenced twice** in one query.
3. ~~No SQL in `queries.py` has been run against Zetaris.~~ **It has.** The real
   `q_identity_candidates()` output ran verbatim against a live union view: 23 rows,
   2.6 s. Doing so found a silent escaping bug (`''` deletes the apostrophe) that 104
   passing tests had agreed with.

What remains unproven is only the real data: the generator, the actual `medtrace.*`
views and their counts (steps 4–6).

## `make test` no longer regenerates your data

The determinism test used to run the generator **in place**, so the suite quietly
rewrote `data/synthetic/` and the committed fixtures. On a fresh clone that meant CI
regenerated the silos *without* the gitignored real PBS codes and then asserted
against data nobody had committed — the same commit scored 0.846 locally and 0.820 on
CI. It now writes under a temp directory.

So: **if `data/synthetic/silos/` is missing, the generator tests skip.** Run
`make synth` yourself; nothing will create it for you any more.

## If you regenerate the data, re-cache Zetaris

`make synth` changes the files, but `CACHE TABLE` on an already-cached table is a
no-op, so a plain re-`--apply` leaves Zetaris serving the **previous** generation and
every committed fixture then disagrees with the live views. Run:

```bash
python3 scripts/register_sources.py --refresh      # creates and drops nothing
```

`datasvc` no longer needs restarting — its cache is keyed on file mtime now.

## Waiting on Arpon (blocks nothing else, but these are decisions only he can make)

1. ~~Go-ahead to apply the registration.~~ **Done 24 Oct — live and verified.**
2. **Two ATC/APINCHS calls** (`data/reference/atc_crosscheck.csv`): **sotalol** —
   DATA_SPEC `C07AA07` (not APINCHS) vs PBS `C01BD` (**Ext**, i.e. high-risk); and
   **paracetamol/codeine** — DATA_SPEC `N02AJ06` (**N**) vs PBS `N02BE01` (loses the
   codeine). DATA_SPEC wins in the build; nothing was applied silently.
3. **DATA_SPEC §4.2 bundle 6** anchor shares sum to **0.95**, not 1.00.
4. **Four formulation-trap drugs have only one form in §4.2** (metoprolol, gliclazide,
   venlafaxine, tamsulosin), so no IR/MR pair can be planted for them.
5. **Population size** — at 20 tune patients, §5.2's "≥15 tune instances per type" is
   unreachable for the low-rate types. Raise `--patients` before the final eval run.

## Next up

1. **Arpon** — steps 1–7 are done. Run `--recreate-drifted` (Blocked on), then
   Sunday's modules: `fuse`, `detect`, `triage`, `scripts/eval.py`. `detect` and
   `triage` have brief 8's never-flag/always-flag rules to build against, already
   recorded as data in `triage.py`.
2. **Arnav** — adapters and orchestrator need nothing from Arpon. Import
   `app.domain.packs.medtrace.*` rather than writing your own stubs; use a
   fixture-backed fallback in your own code where a body still raises. World Model
   before H-MEM.
3. **Anshu** — `web/` against Arnav's example JSON in `tests/fixtures/api/`. No Zetaris
   and no Nightshift, ever.

Claim an item in your handoff entry before starting it.
