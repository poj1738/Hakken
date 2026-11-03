# Demo video facts

Gathered 3 Nov 2026 by Claude Code (read-only). Every value cites its file or the live query that produced it. Live queries ran against Arpon's Zetaris (`localhost:8888`) through `scripts/register_sources.py`'s read-only client; one statement each, no semicolon. Nothing was created or dropped. `.env` was not opened.

## 1. Zetaris names

Each silo is a REST table in its own Lightning database (`MT_EMR.emr_raw`, `MT_GP.gp_raw`, `MT_PHARMACY.pharmacy_raw`, `MT_PATIENT.patient_raw`, reference tables in `MT_REF` / `MT_TGA`), exposed as a harmonised SchemaStore **view** in the `medtrace` container. Agents query the views. Source: `scripts/register_sources.py` (SILOS, REFERENCES, TGA), `app/domain/packs/medtrace/queries.py` (SOURCE_VIEWS, REFERENCE_VIEWS, TGA_VIEW).

| Source | View the app queries | Raw table | Patient ID column | Drug / generic | Strength | Dose |
|---|---|---|---|---|---|---|
| Hospital EMR | `medtrace.emr` | `MT_EMR.emr_raw` | `source_patient_id` (MRN, e.g. MRN0000008) | `med_text`, `med_code` (AMT MP) | `strength_text` | `dose_text`, `freq_text` |
| GP | `medtrace.gp` | `MT_GP.gp_raw` | `source_patient_id` (GPP000008) | `med_text`, `med_code` (AMT MPP) | `strength_text` | `freq_text` (directions) |
| Pharmacy | `medtrace.pharmacy` | `MT_PHARMACY.pharmacy_raw` | `source_patient_id` (C000008) | `med_text` (brand), `med_code` (PBS) | `strength_text` | `qty`, `days_supply` |
| Patient interview (the "patient list") | `medtrace.patient_report` | `MT_PATIENT.patient_raw` | `source_patient_id` (INT00008) | `med_text` (patient's words) | — | `freq_text`, `status_text` |
| PBS lexicon | `medtrace.med_lexicon` | `MT_REF.lexicon_raw` | — | `generic`, `brand`, `pbs_code` | `strength` | `pack_qty` |
| TGA shortages | `medtrace.tga_shortages` | `MT_TGA.tga_raw` | — | `medicine_name`, `ingredients` | in `medicine_name` (`salt_quantity` is salt mass, not strength) | — |

All 4 silo views share 25 harmonised columns (`DESCRIBE medtrace.emr`, 1.84 s): `source`, `row_id`, `source_patient_id`, `ihi_syn`, `name_given`, `name_family`, `name_previous`, `dob_text`, `sex`, `postcode`, `record_kind`, `doc_date`, `med_text`, `med_code`, `code_system`, `strength_text`, `dose_text`, `route_text`, `freq_text`, `status_text`, `note_text`, `qty`, `days_supply`, `pharmacy_id`, `script_type`.

`medtrace.med_lexicon` (15 columns): `pbs_code`, `brand`, `generic`, `amt_mp`, `amt_mpp`, `amt_tpp`, `atc_primary`, `strength`, `form`, `release`, `pack_qty`, `repeats`, `is_combination`, `ingredients`, `dos_weight`.

`medtrace.tga_shortages` (12 columns): `artg_id`, `medicine_name`, `sponsor`, `ingredients`, `salt_quantity`, `dosage_form`, `status`, `shortage_start`, `expected_resolution`, `impact_rating`, `availability`, `reason`.

Also: `medtrace.all_sources` (UNION ALL of the 4 silos, 13,856 rows) and `medtrace.apinchs` (ACSQHC high-risk classes, 42 rows).

**USL:** `lightning.metastore.medtrace.medtrace_usl`, with tables `high_risk_class`, `medicine` and `medication_statement`. `medication_statement` (21 columns): `row_id`, `source_system`, `patient_id`, `record_kind`, `doc_date`, `med_text`, `code_system`, `med_code`, `generic`, `atc`, `high_risk_class`, `resolved_by`, `strength_text`, `dose_text`, `freq_text`, `status_text`, `qty`, `days_supply`, `pharmacy_id`, `script_type`, `strength_listed`. The patient column is `patient_id` and the silo column is `source_system`. DDL: `data/zetaris/usl/03_usl_compile_medtrace_usl.sql`. Note: the USL's six sources are the 4 silos + PBS lexicon + APINCHS (`docs/zetaris_usl/01_use_case_and_sources.md`); TGA is a separate optional overlay, not inside the USL.

## 2. Ready-to-run SQL (each run once live)

### a. First 5 rows of each source

**EMR**
```sql
SELECT * FROM medtrace.emr LIMIT 5
```
_Ran live 2026-11-03T05:02:26 UTC · 5 rows · 1.83 s_

**GP**
```sql
SELECT * FROM medtrace.gp LIMIT 5
```
_Ran live 2026-11-03T05:02:27 UTC · 5 rows · 1.37 s_

**Pharmacy**
```sql
SELECT * FROM medtrace.pharmacy LIMIT 5
```
_Ran live 2026-11-03T05:02:29 UTC · 5 rows · 1.73 s_

**Patient interview**
```sql
SELECT * FROM medtrace.patient_report LIMIT 5
```
_Ran live 2026-11-03T05:02:30 UTC · 5 rows · 0.4 s_

**PBS lexicon**
```sql
SELECT * FROM medtrace.med_lexicon LIMIT 5
```
_Ran live 2026-11-03T05:02:30 UTC · 5 rows · 0.47 s_

**TGA shortages**
```sql
SELECT * FROM medtrace.tga_shortages LIMIT 5
```
_Ran live 2026-11-03T05:02:31 UTC · 5 rows · 0.63 s_

### b. The USL filtered to one patient (P0008, all 4 silo IDs)

```sql
SELECT source_system, patient_id, med_text, generic, strength_text, dose_text, freq_text, high_risk_class FROM lightning.metastore.medtrace.medtrace_usl.medication_statement WHERE patient_id IN ('MRN0000008','GPP000008','C000008','INT00008') ORDER BY generic, source_system
```
_Ran live 2026-11-03T05:02:41 UTC · 103 rows · 10.22 s_

The USL resolves every line, from all four systems, to one generic, ATC code and high-risk class.

### c. The federated JOIN (pharmacy → lexicon → shortages)

**No such JOIN is saved in the repo.** Searched `docs/`, `scripts/`, `data/zetaris/` and `app/`. The repo's own "federated query" is the cross-silo identity query Q1 over `medtrace.all_sources` (`docs/PLAN_2026-10-24.md:139`; `app/domain/packs/medtrace/queries.py` `q_identity_candidates`), and the app's shortage check is Q4 `q_shortages` (exact-ingredient match, no JOIN). The query below was **written for the video** and run once:

```sql
SELECT p.source_patient_id, p.med_text AS dispensed, p.strength_text, l.generic, t.medicine_name AS tga_product, t.status, t.expected_resolution FROM medtrace.pharmacy p JOIN medtrace.med_lexicon l ON p.med_code = l.pbs_code JOIN medtrace.tga_shortages t ON lower(t.ingredients) LIKE concat(l.generic, '%') WHERE p.source_patient_id = 'C000008' AND t.status IN ('Current', 'Anticipated') AND t.ingredients NOT LIKE '%|%'
```
_Ran live 2026-11-03T05:02:45 UTC · 141 rows · 4.28 s_

It returns one row per (fill × shortage report), so 141 rows for one patient. For screen, add `GROUP BY l.generic, t.medicine_name, t.status, t.expected_resolution` and select those four columns: 15 distinct reports across metformin, rosuvastatin, ezetimibe, levothyroxine and sertraline.

### d. The data-quality rule

Native rule (registered in Zetaris; `data/zetaris/usl/08_usl_dq_strength_is_a_real_product.sql`):
```sql
REGISTER DQ strength_is_a_real_product TABLE lightning.metastore.medtrace.medtrace_usl.medication_statement AS
COALESCE(strength_listed, true)
```
Run natively with `RUN DQ strength_is_a_real_product TABLE lightning.metastore.medtrace.medtrace_usl.medication_statement` in the Zetaris SQL editor (≈38 s per `docs/zetaris_usl/03_usl.md`; the app's read-only adapter refuses `RUN DQ`). The same predicate as a SELECT, run live:

```sql
SELECT COUNT(*) FROM lightning.metastore.medtrace.medtrace_usl.medication_statement WHERE NOT COALESCE(strength_listed, true)
```
_Ran live 2026-11-03T05:02:57 UTC · 1 rows · 12.01 s_ → **14**

## 3. The data-quality rule

- **Plain English:** a medicine line that names a medicine and a strength must name a strength that medicine is actually sold in.
- **Current violations:** **14** of 13,856 lines (query above).
- **Native or ours:** both. The rule is a **native Zetaris DQ rule** (`REGISTER DQ`, run with `RUN DQ`); the `strength_listed` flag it tests is computed by our USL activation SQL (`data/zetaris/usl/07_usl_activate_medication_statement.sql`), and our SELECT re-counts it.
- **Planted?** **Yes, all 14.** Each row's `row_id` is in a planted `dose` finding in `data/synthetic/ground_truth.json` (checked 14/14). The generator plants a chart dose error by halving the strength (`scripts/generate_synthetic.py`, the `plant("dose", …)` branch: `halved = dose / 2`), which produces non-existent products such as aspirin 50 mg, telmisartan 20 mg and rosuvastatin 2.5 mg. DATA_SPEC §5 lists the `dose` type.

## 4. Demo patient candidates

Criteria: in all 4 silos, one medicine at different strengths across silos, and a Current/Anticipated TGA report for that medicine. 17 patients qualify (computed from `data/synthetic/silos/*.json`, `data/synthetic/ground_truth.json` and `data/reference/tga_shortages.json`). **No clean perindopril, telmisartan or levothyroxine case exists:** the only perindopril one (P0127) is muddled by a perindopril/amlodipine combination. The three clearest:

| Rank | Patient | IDs (EMR · GP · Pharmacy · Patient) | Medicine | Chart | GP | Pharmacy | TGA |
|---|---|---|---|---|---|---|---|
| **1** | P0008 | MRN0000008 · GPP000008 · C000008 · INT00008 | metformin | **500 mg** 1 bd | 1000 mg morning and night | Diabex 1000 mg | METFORMIN SANDOZ 500 mg, 850 mg, XR 500 mg (Current) |
| 2 | P0124 | MRN0000124 · GPP000124 · C000124 · INT00124 | rosuvastatin | **5 mg** | 10 mg | 10 mg | CAVSTAT 20 mg (Anticipated) |
| 3 | P0057 | MRN0000057 · GPP000057 · C000057 · INT00057 | amlodipine | **2.5 mg** | 5 mg | 5 mg | 4 amlodipine reports |

P0008 is in the `SAMPLE_MODE` replay set (16 replayable patients) and its chart error is a planted `dose` finding. The patient described the medicine as **"sugar tablet", morning and night, still taking: yes**, a good lay-term moment. P0124 (held-out) also has a warfarin dose-unconfirmable finding.

**Per-silo queries for P0008** (run live):

```sql
SELECT row_id, source_patient_id, med_text, strength_text, dose_text, freq_text, record_kind FROM medtrace.emr WHERE source_patient_id = 'MRN0000008' AND lower(med_text) LIKE 'metformin%'
```
_Ran live 2026-11-03T05:03:09 UTC · 1 rows · 0.74 s_

```sql
SELECT row_id, source_patient_id, med_text, strength_text, freq_text, status_text FROM medtrace.gp WHERE source_patient_id = 'GPP000008' AND lower(med_text) LIKE '%metformin%'
```
_Ran live 2026-11-03T05:03:09 UTC · 1 rows · 0.31 s_

```sql
SELECT row_id, source_patient_id, med_text, strength_text, qty, days_supply, doc_date FROM medtrace.pharmacy WHERE source_patient_id = 'C000008' ORDER BY doc_date
```
_Ran live 2026-11-03T05:03:10 UTC · 71 rows · 0.5 s_

```sql
SELECT row_id, source_patient_id, med_text, freq_text, status_text FROM medtrace.patient_report WHERE source_patient_id = 'INT00008'
```
_Ran live 2026-11-03T05:03:10 UTC · 11 rows · 0.36 s_

For P0124 or P0057, swap the IDs (`MRN0000124`/`GPP000124`/`C000124`/`INT00124`) and the medicine name.

## 5. Live MedTrace run on P0008

Run: `SAMPLE_MODE=false .venv/bin/python run.py --input <{"patient_id": "MRN0000008"}>` on 3 Nov 2026, against live Zetaris and Nightshift. Full response saved during the session (not committed).

- **Status:** `success`. **Run time:** 247 s (wall clock 249 s, about 4 min 9 s). **Zetaris queries:** 4.
- **Discrepancies:** 3.

| Type | Medicine | Severity | High-risk class | Pharmacist review flag | What it says |
|---|---|---|---|---|---|
| stale_listing | rivaroxaban | low | H | yes | The GP record lists Xarelto 20 mg one a day as active dated 14/08/2026 (GP-000067), while pharmacy records show Xarelto  |
| dose | metformin | medium | — | no | charted 1000 mg/day against 2000 mg/day before admission |
| omission | rosuvastatin | medium | — | no | Rosuvastatin (Crestor) is listed as active in the GP record at 10 mg one a day on 14/08/2026 (GP-000058), with Crestor 1 |

- **High-risk:** rivaroxaban (APINCHS class `H`, an anticoagulant): a **stale listing** (the GP still lists it, but it's no longer dispensed). The summary puts it first: "Confirm the rivaroxaban stale listing first, as pharmacist review is required before any chart action. Verify the intended metformin regimen because it is chart…"
- **Metformin, the demo conflict:** found as a **dose discrepancy**, "charted 1000 mg/day against 2000 mg/day before admission" (chart 500 mg bd vs GP/pharmacy 1000 mg bd).
- **Pharmacist-review flag:** **yes**. Every recommendation has `requires_human_review: true`; per finding, see the `needs_pharmacist` column above.
- **Shortage notices:** 16 "known shortage" notices across 6 medicines. Metformin's text, verbatim: "Known shortage listed for METFORMIN SANDOZ metformin hydrochloride 500mg tablet blister pack (Current, expected to resolve 2026-12-31). The patient's product (Diabex 1000 mg) is a different one.". **Caveat for the video:** after Arnav's S42 change, every notice says the shortage is a **different product** from the patient's own (e.g. Diabex 1000 mg is not short). So this patient shows the matching logic working, but **no shortage affects the patient's own medicine**. If the video needs "the patient's own product is short", a different patient is needed.
- **Section caveat, shown once:** "The TGA shortage database is incomplete: a listed shortage is not a statement that a medicine is unavailable, and a medicine not listed may still be short."
- **Nemotron models in the trace (`model_calls[].routed_model`):** `nvidia/nemotron-3.5-super-vl-120b-a12b`. 7 calls (Planner, Executor, Writer ×3, Evaluator ×2), all answered through Nightshift, none degraded.


## 6. The UI

- **Dev UI:** http://localhost:5173 (`cd web && VITE_API_MODE=live VITE_API_URL=http://localhost:8000 npm run dev`), API on http://localhost:8000 (`SAMPLE_MODE=false .venv/bin/python run.py serve`). In Docker the API also serves the built UI at http://localhost:8000 (`app/main.py:152`, `StaticFiles`).
- **Choosing a patient:** a **search box plus a patient list** (`web/src/components/Picker.tsx`: a text input that filters the list; click a patient to run).
- **Panels** (`web/src/components/`): `Header` (status pill: Zetaris, Nightshift, last routed model, sample mode) · `Pipeline` (agent pipeline lighting up per step) · `Timeline` / `Agent` (live agent timeline; each model step names its Nemotron) · `IdentityReview` · `Coverage` / `Silos` · `Grid` with `Compare` (side-by-side per source) · `Flags` (findings, evidence rows, Confirm / Reject with reason) · `Tasks` · `Supply` (TGA known shortages) · `TrustPanel` (H-MEM trust before → after) · `LearningHero` · `TechDetails` (SQL, query ids, evidence) · `Footer` (disclaimer).

## 7. Hand-coded comparison (`docs/zetaris_usl/04_time_saved.md`)

| | USL | Hand-coded |
|---|---|---|
| Code to answer the question | 1 SQL statement | 51 lines of Python (`scripts/handcoded_comparison.py`) |
| One-time setup | 43 lines of activation SQL | none |
| Manual mapping steps at question time | 0 | 11 |
| Runtime | 19.11 s | 0.34 s |
| Identical results | yes | |

The doc reports, as is, that hand-coded was faster at this size; the saving is in reuse: each new question is one `SELECT` instead of re-applying 11 mapping steps.

## 8. Live-proof rerun (nothing changed)

- **What datasvc serves for pharmacy:** `GET /silos/pharmacy` serves `data/synthetic/silos/pharmacy.json` whole (`datasvc/main.py`, `SILOS`); Zetaris's REST table `MT_PHARMACY.pharmacy_raw` points at `${DATASVC_PUBLIC_URL}/silos/pharmacy`.
- **Does Zetaris cache REST tables?** Yes. Registration runs `CACHE TABLE` on every raw table (`scripts/register_sources.py` `plan_statements`), and `CACHE TABLE` on an already-cached table is a no-op, so after a data change you must `UNCACHE` + `CACHE` (`register_sources.py --refresh`, i.e. `make refresh`). CLAUDE.md records this.
- **How to test it on camera, without changing the committed data:** (1) `SELECT COUNT(*) FROM medtrace.pharmacy` → 9216. (2) Watch the datasvc log while re-running it: no new `GET /silos/pharmacy` request, because Zetaris answers from its cache. (3) `make refresh`: the datasvc log now shows a `GET /silos/pharmacy`, the moment Zetaris re-reads the source. (4) Optionally, with a regenerated or modified **copy** of the file served by a second datasvc on another port, show the count change only after refresh, then restore with `make synth && make refresh` (CI checks the committed data reproduces byte for byte).

## 9. Evaluation numbers

- **Planted-truth scorecard, held-out patients** (`scripts/eval.py --split heldout`; README §"Evidence"; `docs/DECISIONS.md` 25 Oct): **precision 0.95, recall 0.95, F1 0.95** (the clean figure; today's code prints recall 0.97 / F1 0.96 after one fix found via held-out). Core APINCHS high-risk recall **30/32** (95% CI 0.80–0.98), extended 5/5, **0 false identity merges**. Pinned by `tests/eval/test_scorecard.py`.
- **"Adversarial verifier":** there are two, so don't conflate them. (a) **In the product**, the Evaluator re-reads every cited row in one Zetaris query and Nemotron critiques each explanation; anything still objected to after the last round is replaced by a grounded template (`docs/ARCHITECTURE.md`; per-run outcome in each trace, e.g. `output_examples/live/*.trace.jsonl`). (b) **The codebase scan**, 25 Oct: 7 reviewers raised 57 findings, 2 skeptics per finding tried to refute each, and **55 survived** (`docs/SCAN_2026-10-25.md`). Not a product metric.

## 10. Repository

**Public:** https://github.com/poj1738/Hakken (`gh repo view poj1738/Hakken`, visibility PUBLIC).
