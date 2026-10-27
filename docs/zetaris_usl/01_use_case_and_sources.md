# 1a — Use case and data sources

## The use case: medication reconciliation at hospital admission

When a patient is admitted, a hospital pharmacist has to work out what they were actually
taking before they came in (the *Best Possible Medication History*), and compare it with what
has been charted. The answer is spread across systems that do not talk to each other: the
hospital's own record, the GP's list, the community pharmacy's dispensing history and what
the patient says at the bedside. Each one is partial, each can be out of date, and each
describes the same medicine differently.

MedTrace reconciles them. Its agents query all four through Zetaris, resolve every line to a
medicine, rank the discrepancies (high-risk medicines first) and verify every cited row before
a pharmacist sees it. The Unified Semantic Layer described here is the single, typed view of
"every medicine line, from every source, resolved to a medicine" that this work rests on.

**All patient data is synthetic.** The two reference sources are real public data.

## The six sources, and why each is needed

| # | Source | Zetaris objects | Origin | Why MedTrace needs it |
|---|---|---|---|---|
| 1 | **Hospital EMR** (admission chart, prior discharges) | `MT_EMR.emr_raw` → view `medtrace.EMR` | synthetic silo | What has been charted now: the thing being checked |
| 2 | **GP medication list** | `MT_GP.gp_raw` → `medtrace.GP` | synthetic silo | What the GP prescribed; often stale, often "as directed" |
| 3 | **Community pharmacy dispensing** | `MT_PHARMACY.pharmacy_raw` → `medtrace.PHARMACY` | synthetic silo | What was actually supplied, and when |
| 4 | **Patient interview** | `MT_PATIENT.patient_raw` → `medtrace.PATIENT_REPORT` | synthetic silo | What the patient says they take, in their own words |
| 5 | **PBS medicines lexicon** | `MT_REF.lexicon_raw` → `medtrace.MED_LEXICON` | real: PBS item codes, AMT, WHO ATC | The only way to say two differently-coded lines are the same medicine, and which strengths exist |
| 6 | **ACSQHC APINCHS** high-risk classes | `MT_REF.apinchs_raw` → `medtrace.APINCHS` | real: ACSQHC APINCH list, keyed by ATC | Which medicines a pharmacist must review first (insulins, anticoagulants, opioids …) |

`medtrace.ALL_SOURCES` is a `UNION ALL` of the four harmonised silo views. Row counts and
real questions answered per source are in [02](02_exploratory_queries.md).

**Not used:** the sponsor install's pre-existing `NY_TAXI` and `TPCDS_DB` sample databases
(declared in [`docs/PREEXISTING.md`](../PREEXISTING.md)). The TGA medicine-shortage table that
MedTrace can also read is not registered on the instance this evidence was captured on, so it
is not one of the six.

## How each source is onboarded

All of it is generated and run by [`scripts/register_sources.py`](../../scripts/register_sources.py)
(dry run by default; `--apply` executes):

1. **Serve.** A small read-only service, `datasvc`, serves each silo and reference table
   whole at one fixed URL as `{"records": [...]}`. A Lightning REST table binds one fixed
   endpoint with no paging parameter, so "whole, at one URL" is forced, not chosen.
2. **Register.** Per source: `CREATE LIGHTNING DATABASE` → `CREATE LIGHTNING REST TABLE`
   (pointing at `datasvc`) → `CREATE SCHEMASTORE VIEW` that `explode()`s the records and
   harmonises the silo's own field names into one shape → `CACHE TABLE`. The four silo views
   are then unioned into `medtrace.ALL_SOURCES`.
3. **Verify it is operable.** `make verify` (`register_sources.py --verify-only`) counts every
   view against what `datasvc` serves and diffs live query results against committed
   fixtures; a mismatch is fatal. A successful `CREATE` alone does not prove a usable table.
4. **Explore it.** 2–3 real questions per source, run live: [02](02_exploratory_queries.md).
5. **Build the USL** on top: [03](03_usl.md).
