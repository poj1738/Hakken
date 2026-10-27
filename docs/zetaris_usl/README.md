# MedTrace on Zetaris — Scoring Methodology evidence

**Team Hakken · MedTrace (medication reconciliation) · synthetic patient data.**

Start here. Every scoring item maps to a file below, and every query result in these files is
the saved output of a live run against our Zetaris instance
([`results/`](results/), each with its SQL, row count, latency and UTC timestamp) — nothing is
typed by hand. The USL itself is
**`lightning.metastore.medtrace.medtrace_usl`**: three related tables over six sources, with a
native data-quality rule.

| Item | What was asked | Where | Evidence |
|---|---|---|---|
| **1a** | Use case and ≥3 data sources | [01 Use case and sources](01_use_case_and_sources.md) | 6 sources: hospital EMR, GP, community pharmacy, patient interview (synthetic); PBS medicines lexicon, ACSQHC APINCHS (real) |
| **1b** | Onboard, verify operable, 2–3 exploratory queries per source | [02 Exploratory queries](02_exploratory_queries.md) | 15 live queries across the 6 sources, each answering a real question; onboarding + `make verify` in [01](01_use_case_and_sources.md#how-each-source-is-onboarded) |
| **1c** | 1 USL + its DDL; 2–3 queries showing it is active; 1 DQ rule executing | [03 The USL](03_usl.md) | DDL in [`data/zetaris/usl/`](../../data/zetaris/usl/) (created live); 4 "USL is active" results; native `REGISTER DQ` / `RUN DQ` / `SHOW DQ INVALID RECORD` with counts and the failing rows |
| **2a** | How the USL saved time vs hand-coding (bonus: build and compare) | [04 Time saved](04_time_saved.md) | **Bonus built:** the same question hand-coded in Python ([`scripts/handcoded_comparison.py`](../../scripts/handcoded_comparison.py)), identical results, measured lines, mapping steps and runtime — including where hand-coding was faster |
| **2b** | Would the USL help in our work (bonus: a project that would benefit, with forecast) | [05 Would it help](05_would_it_help.md) | Where it helped and where it did not; **bonus:** cross-LHD medication-safety audit with a stated-assumption forecast |
| **2c** | Make the USL stronger, as a PM requirement (bonus: example + mock) | [06 Killer requirement](06_killer_requirement.md) | Declarative code crosswalks: problem, user, requirement, acceptance criteria, priority; **bonus:** labelled mock DDL; friction table from our build log |

## Headline

**6 sources → 1 view.** `medication_statement` resolves every medicine line from four silos —
coded three different ways, plus free text — to a PBS medicine, its ATC code and its high-risk
class. **The data-quality rule `strength_is_a_real_product` caught 14 violations in 13,856
records**, every one a charted strength that no product is made in (checked against our answer
key in [03](03_usl.md)).

## Reproduce

```bash
python3 scripts/register_sources.py --usl            # dry run: print the USL statements
python3 scripts/register_sources.py --usl --apply    # create it (needs the sources registered first)
python3 scripts/zetaris_eval.py                      # run 1b + 1c live, save results/*.json
python3 scripts/handcoded_comparison.py              # 2a comparison
python3 scripts/zetaris_docs.py                      # render 02, 03 and the 04 table from results/
```

Credentials are read from `.env` by name (`ZETARIS_REST_URL`, `ZETARIS_ORG_ID`,
`ZETARIS_API_KEY`) and never printed.
