# MedTrace Synthetic Data Specification (docs/DATA_SPEC.md)

MedTrace's synthetic world is 200 patients aged 60 to 90 (100 tune, 100 held-out), each with 5 to 12 regular medicines (mean about 8.4). About 2.4 findings per patient are planted across 11 finding types, so every core type has at least 15 tune instances. Rates are anchored to Cornish 2005 (0.93 unintended discrepancies per patient, 46.4% omissions) and Australian source-accuracy studies (Taylor 2014, Boyce 2013, Elliott 2023, Francis 2025).\[1\]\[2\] Every number is cited or flagged **[ASSUMPTION]** or **[OVERSAMPLED]**.

## Naming (authoritative)

These names are the contract between the generator, the ground truth, the Zetaris views
and Arnav's pipeline. They match `docs/PLAN_2026-10-24.md` and
`app/domain/packs/medtrace/types.py`, which is the frozen shared file:

| Thing | Name | Not |
|---|---|---|
| Source keys — everywhere a source is a value or a JSON key | `emr`, `gp`, `pharmacy`, `patient` | `EMR`, `GP`, `PHM`, `PAT` |
| `row_id` prefixes — unchanged, these are row identifiers, not source keys | `EMR-000001`, `GP-000001`, `PHM-000001`, `PAT-000001` | |
| Ground truth file | `data/synthetic/ground_truth.json` | `data/ground_truth.json` |
| Ground truth array of planted discrepancies | `planted` | `findings` |

`GP` stays uppercase in prose where it means "general practitioner" (as in "414 GP
letters"). The lowercase form is only ever the source key.

The 11 discrepancy types in section 5.2 and the 6 notice types in section 6 match
`types.DiscrepancyType` and `types.NoticeType` exactly; a change to either needs a
change to that frozen file.

## TL;DR

- **Population:** 200 synthetic patients, 5 to 12 regular medicines each, drawn from 16 condition bundles. Agent shares follow PBS Date of Supply volumes (2023-24: rosuvastatin 17.0M vs atorvastatin 11.9M scripts; pantoprazole ahead of esomeprazole). Polypharmacy follows AIHW: 5 or more medicines in 40% of people aged 75+ and 20% of people aged 65 to 74.\[3\]\[4\]
- **Findings:** about 2.4 planted per patient. Omission is anchored to Cornish 2005. Stale GP listings are anchored to Elliott 2023 (16.9% of exchange-derived medicines not current) and Boyce 2013 ("almost half of the discrepancies were related to non-current medications being recorded"). Formulation, route, duplication, dose_unconfirmable and identity_uncertain are oversampled to 15 or more tune instances each.
- **Hidden error rates:** set per (source, attribute) so the H-MEM trust model has a target. GP lists are stale. Pharmacy data is blind to private scripts and second pharmacies. The patient interview misses prescribed items but is the only source for complementary medicines (66.2% of adults aged 70+ used one in the past month, ASPREE).\[5\] Trust priors are deliberately offset from truth so convergence is measurable.

---

## 1. Purpose and scope

| Item | Value |
|---|---|
| Spec version | 1.0.0; `generator_version` = "1.0.0" |
| Generator | scripts/generate_synthetic.py |
| Seed | 20261024 (`numpy.random.Generator(PCG64(20261024))`; sub-streams via `SeedSequence.spawn`) |
| as_of | 2026-10-24 (admission date for all patients; source data truncated here) |
| Data | 100% synthetic, Australian context. No real patient data, identifiers or Medicare numbers |
| Governs | Generator, ground truth JSON, evaluation harness |
| Size driver | Zetaris latency about 4 s per query; each silo kept under about 2,500 rows |

**Synthetic identifier rules**

| Field | Format |
|---|---|
| ihi_syn | `SYN-` + 12 digits. Never 16 digits, never the real 800360 prefix |
| mrn / gp_pid / cust_no / intake_id | `MRN`+7 digits / `GPP`+6 / `C`+6 / `INT`+5 |
| pharmacy_id | `PHX01` to `PHX12` |
| prescriber | Synthetic names only ("Dr A. Nguyen-SYN"); no prescriber numbers |

---

## 2. Sources

Each source is served whole at one REST URL as `{"records": [...]}`, one flat row per medication statement with demographics repeated. A patient known to a source with no medicines gets one row with medication fields null. A patient absent from a source has no rows. `row_id` is unique and source-prefixed.

### 2.1 `emr` — EMR (hospital); `row_id` prefix `EMR-`

| Column | Type | Format / domain | Presence |
|---|---|---|---|
| row_id | string | `EMR-000001` | 100% |
| mrn | string | `MRN`+7 digits | 100% |
| ihi_syn | string, nullable | `SYN-`+12 digits | 95% |
| given_name, family_name | string | formal given name; current surname | 100% |
| dob | date | `YYYY-MM-DD` | 100% |
| sex | enum | `F`, `M` | 100% |
| postcode | string | 4 digits | 100% |
| record_kind | enum | `admission_chart`, `prior_discharge` | 100% |
| record_date | date | admission_chart = as_of; prior_discharge = as_of minus 14 to 180 days | 100% |
| med_name | string | generic as charted | per row |
| amt_mp_code | string | AMT MP from lexicon | 98% of med rows |
| strength, dose, dose_unit | string, number, enum | "5 mg"; 5; `mg`, `microgram`, `unit`, `mL`, `puff`, `patch` | per row |
| route | enum | `PO`, `SL`, `INH`, `SC`, `TOP`, `TD`, `EYE`, `PR` | per row |
| frequency | enum | `mane`, `nocte`, `daily`, `bd`, `tds`, `qid`, `weekly`, `monthly`, `6-monthly`, `prn` | per row |
| chart_note | string | "withheld: contrast", "withheld: AKI", "ceased: bleeding" | 8% of admission_chart med rows |
| discharge_action | enum | `continue`, `cease`, `start`, `change` (prior_discharge only) | 100% of prior_discharge med rows |
| action_reason | string | "dose reduced: eGFR 28" | 81% of non-continue actions |

Suggested addition: `admit_time` (HH:MM) for after-hours admissions. **[SUGGESTION]**

### 2.2 `gp` — GP practice summary; `row_id` prefix `GP-`

| Column | Type | Format / domain | Presence |
|---|---|---|---|
| row_id | string | `GP-000001` | 100% |
| gp_pid | string | `GPP`+6 digits | 100% |
| ihi_syn | string, nullable | `SYN-`+12 digits | 80% |
| first_name | string | may be nickname ("Peggy") | 100% |
| surname, previous_surname | string | previous_surname = maiden or prior married | previous_surname in 8% of females |
| birth_date | string | `DD/MM/YYYY` | 100% |
| gender | enum | `Female`, `Male` | 100% |
| postcode | string | 4 digits | 100% |
| drug_text | string | brand or generic ("Lipitor 40mg") | per row |
| amt_code | string, nullable | AMT MPP, TPP or MP | 85% of med rows |
| strength | string | "40 mg" | 97% of med rows |
| directions | string | "1 tab bd", "as directed per INR" | 92% of med rows |
| status | enum | `active`, `ceased` | per row |
| last_reviewed, list_last_updated | string | `DD/MM/YYYY` | 100% |

### 2.3 `pharmacy` — community dispensing; `row_id` prefix `PHM-`

| Column | Type | Format / domain | Presence |
|---|---|---|---|
| row_id | string | `PHM-000001` | 100% |
| cust_no | string | `C`+6 digits | 100% |
| ihi_syn | string, nullable | `SYN-`+12 digits | 70% |
| name | string | "SMITH, Margaret" | 100% |
| dob | date | `YYYY-MM-DD` | 100% |
| postcode | string | 4 digits | 100% |
| pharmacy_id | string | one exposed pharmacy per patient | 100% |
| dispensed_on | date | 12-month lookback | per row |
| pbs_code | string, nullable | null if private | per row |
| brand, strength, form | string | "Eliquis", "5 mg", "tablet" / "modified release tablet" | per row |
| qty, days_supply, repeats_left | integer | see section 9 | per row |
| script_type | enum | `PBS`, `private` | per row |
| prescriber | string | synthetic | per row |

### 2.4 `patient` — patient or carer interview; `row_id` prefix `PAT-`

| Column | Type | Format / domain | Presence |
|---|---|---|---|
| row_id | string | `PAT-000001` | 100% |
| intake_id | string | `INT`+5 digits | 100% |
| ihi_syn | string, nullable | `SYN-`+12 digits | 30% |
| name_given | string | free text ("Peg Smith") | 100% |
| dob | string | free text; may contain typo or day/month swap | 100% |
| med_described | string | "Lipitor", "my blood thinner", "fish oil" | per row |
| how_often | string | "morning and night" | per row |
| still_taking | enum | `yes`, `no`, `unsure` | per row |

---

## 3. Population

| Item | Value | Basis |
|---|---|---|
| Patients | 200; split 100 `tune` / 100 `heldout`, disjoint, stratified by age band, sex, bundle count | Fixed design |
| Trap families | Lookalike, twin and overlay pairs kept inside one split | Prevents leakage |
| Age 60 to 69 / 70 to 79 / 80 to 90 | 25% / 38% / 37% | **[ASSUMPTION]** Skewed older because admission rises with age: ABS 2024-25, 19.6% of people aged 65 to 74 vs 25.0% aged 85+ admitted in the year\[6\] |
| Sex | Female 53%, Male 47% | **[ASSUMPTION]** AIHW polypharmacy almost equal by sex (42% males, 39% females aged 75+), so sex does not modulate medicine count\[4\]\[7\] |
| DOB | as_of minus age years minus uniform(0, 364) days | Derived |

**Regular medicines per patient**

| Count | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|
| Probability | 0.12 | 0.13 | 0.14 | 0.14 | 0.13 | 0.12 | 0.11 | 0.11 |

- Mean about 8.4; 34% have 10 or more. **[ASSUMPTION]** calibrated to Elliott 2023 inpatients (median age 76, median 10 pre-admission medicines, IQR 6 to 14).\[8\]
- Community anchors: AIHW (Polypharmacy in Australia in 2025, published 7 Oct 2026) found one-third of people with polypharmacy on exactly 5, and "around 1 in 9 of people experiencing polypharmacy were regularly dispensed 10 or more different medicines" (219,000 people, 1% of the population). Page 2019 found continuous polypharmacy in 36.1% of Australians aged 70+.
- Complementary and OTC items are extra (section 6).
- Each patient draws 2 to 6 bundles. In PBS data, more than 79% of older Australians were dispensed medicines for 2 or more chronic conditions and more than 60% for 3 or more (Pharmacy 2018).\[9\]\[10\]

---

## 4. Condition bundles

### 4.1 Sampling

1. Draw medicine count N (section 3).
2. Include each bundle with probability = weight (sex-specific where shown); resample if fewer than 2.
3. Within a bundle, draw the anchor by share, then add-ons by probability, respecting exclusions.
4. Trim lowest-priority add-ons to N (never anticoagulants, insulin, levothyroxine), or add bundles by descending weight.
5. Map generic to lexicon (PBS item to AMT MP/MPP/TPP; primary ATC = highest ATC_PRIORITY_PCT). Brand weighted by PBS Date of Supply volume.

Weights are **[ASSUMPTION]**, ordered to PBS utilisation. 2023-24 top drugs by DDD/1000/day were rosuvastatin 84.59, atorvastatin 80.72, amlodipine 54.08, perindopril 53.65, candesartan 35.02, telmisartan 34.10, sertraline 30.64, escitalopram 28.65, metformin 28.32 and irbesartan 25.33 (Australian Prescriber).\[11\]

### 4.2 Bundles table

HR = high-risk (section 10). "+p" = add-on probability.

| # | Condition | Weight | Generic | AU brand(s) | Strength | Regimen | Share | ATC | HR |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Hypertension | 0.70 | perindopril (arginine / erbumine) | Coversyl | 5, 10 mg / 4, 8 mg | 1 mane | 0.22 | C09AA04 | N |
| | | | amlodipine | Norvasc | 5, 10 mg | 1 daily | 0.20 | C08CA01 | N |
| | | | candesartan | Atacand | 8 to 32 mg | 1 daily | 0.12 | C09CA06 | N |
| | | | telmisartan | Micardis | 40, 80 mg | 1 daily | 0.10 | C09CA07 | N |
| | | | irbesartan | Avapro | 150, 300 mg | 1 daily | 0.08 | C09CA04 | N |
| | | | ramipril | Tritace | 5, 10 mg | 1 daily | 0.06 | C09AA05 | N |
| | | | perindopril/indapamide | Coversyl Plus | 5/1.25 mg | 1 mane | 0.06 | C09BA04 | N |
| | | | irbesartan/HCT | Avapro HCT, Karvezide | 150/12.5, 300/12.5 mg | 1 daily | 0.06 | C09DA04 | N |
| | | | candesartan/HCT | Atacand Plus | 16/12.5 mg | 1 daily | 0.04 | C09DA06 | N |
| | | | telmisartan/amlodipine | Twynsta | 40/5, 80/5 mg | 1 daily | 0.03 | C09DB04 | N |
| | | | perindopril/amlodipine | Coveram | 5/5, 10/5 mg | 1 daily | 0.03 | C09BB04 | N |
| | | | add-on amlodipine (non-CCB anchor) | Norvasc | 5 mg | 1 daily | +0.30 | C08CA01 | N |
| 2 | Dyslipidaemia | 0.65 | rosuvastatin | Crestor | 5 to 40 mg | 1 daily | 0.52 | C10AA07 | N |
| | | | atorvastatin | Lipitor | 10 to 80 mg | 1 daily | 0.36 | C10AA05 | N |
| | | | simvastatin | Zocor | 20, 40 mg | 1 nocte | 0.04 | C10AA01 | N |
| | | | amlodipine/atorvastatin | Caduet | 5/10 to 10/80 mg | 1 daily | 0.04 | C10BX03 | N |
| | | | ezetimibe/rosuvastatin | Rosuzet | 10/10 to 10/40 mg | 1 daily | 0.04 | C10BA06 | N |
| | | | add-on ezetimibe | Ezetrol | 10 mg | 1 daily | +0.15 | C10AX09 | N |
| 3 | GORD | 0.40 | pantoprazole | Somac | 20, 40 mg | 1 daily | 0.50 | A02BC02 | N |
| | | | esomeprazole | Nexium | 20, 40 mg | 1 daily | 0.38 | A02BC05 | N |
| | | | rabeprazole | Pariet | 10, 20 mg | 1 daily | 0.07 | A02BC04 | N |
| | | | famotidine | Pepcidine | 20 mg | 1 bd | 0.05 | A02BA03 | N |
| 4 | Pain / osteoarthritis | 0.30 | paracetamol MR | Panadol Osteo | 665 mg | 2 tds | 0.55 | N02BE01 | N |
| | | | oxycodone CR | OxyContin | 10, 20 mg | 1 bd | 0.10 | N02AA05 | Y |
| | | | oxycodone/naloxone CR | Targin | 10/5, 20/10 mg | 1 bd | 0.08 | N02AA55 | Y |
| | | | buprenorphine patch | Norspan | 5 to 20 microgram/h | weekly | 0.08 | N02AE01 | Y |
| | | | tapentadol SR | Palexia SR | 50, 100 mg | 1 bd | 0.06 | N02AX06 | Y |
| | | | pregabalin | Lyrica | 75 mg | 1 bd | 0.08 | N03AX16 | N |
| | | | celecoxib | Celebrex | 100, 200 mg | 1 daily | 0.05 | M01AH01 | N |
| | | | add-on oxycodone IR | Endone | 5 mg | prn | +0.10 | N02AA05 | Y |
| 5 | T2DM | 0.28 | metformin IR | Diabex, Diaformin | 500 to 1000 mg | 1 bd | 0.24 | A10BA02 | N |
| | | | metformin XR | Diabex XR | 1000 mg | 1 to 2 nocte | 0.20 | A10BA02 | N |
| | | | gliclazide MR | Diamicron MR | 30, 60 mg | 1 to 2 mane | 0.10 | A10BB09 | Y (ext) |
| | | | empagliflozin | Jardiance | 10, 25 mg | 1 daily | 0.12 | A10BK03 | N |
| | | | dapagliflozin | Forxiga | 10 mg | 1 daily | 0.08 | A10BK01 | N |
| | | | sitagliptin/metformin | Janumet | 50/1000 mg | 1 bd | 0.06 | A10BD07 | N |
| | | | empagliflozin/metformin | Jardiamet | 12.5/1000 mg | 1 bd | 0.04 | A10BD20 | N |
| | | | insulin glargine | Optisulin, Toujeo | 100, 300 units/mL | 10 to 40 units nocte SC | 0.10 | A10AE04 | Y |
| | | | semaglutide | Ozempic | 0.5, 1 mg | weekly SC | 0.06 | A10BJ06 | N |
| | | | add-on gliclazide MR | Diamicron MR | 60 mg | 1 mane | +0.20 | A10BB09 | Y (ext) |
| | | | add-on insulin aspart (with glargine) | NovoRapid | units with meals | tds SC | +0.30 | A10AB05 | Y |
| 6 | Depression / anxiety | 0.25 | escitalopram | Lexapro | 10, 20 mg | 1 daily | 0.30 | N06AB10 | N |
| | | | sertraline | Zoloft | 50 to 200 mg | 1 daily | 0.28 | N06AB06 | N |
| | | | mirtazapine | Avanza | 15 to 45 mg | 1 nocte | 0.18 | N06AX11 | N |
| | | | venlafaxine XR | Efexor-XR | 75 to 225 mg | 1 daily | 0.12 | N06AX16 | N |
| | | | duloxetine | Cymbalta | 30, 60 mg | 1 daily | 0.07 | N06AX21 | N |
| | | | add-on temazepam | Normison | 10 mg | nocte prn | +0.12 | N05CD07 | Y |
| 7 | IHD | 0.25 | aspirin | Cartia, Astrix | 100 mg | 1 daily | 0.55 | B01AC06 | N |
| | | | clopidogrel | Plavix, Iscover | 75 mg | 1 daily | 0.25 | B01AC04 | N |
| | | | ticagrelor | Brilinta | 90 mg | 1 bd | 0.05 | B01AC24 | N |
| | | | aspirin/clopidogrel | CoPlavix, DuoCover | 100/75 mg | 1 daily | 0.05 | B01AC30 | N |
| | | | isosorbide mononitrate MR | Imdur, Duride | 60 mg | 1 mane | 0.10 | C01DA14 | N |
| | | | add-on GTN spray | Nitrolingual Pumpspray | 400 microgram/dose | SL prn | +0.40 | C01DA02 | N |
| | | | add-on metoprolol | Betaloc, Minax | 25 to 50 mg | 1 bd | +0.45 | C07AB02 | N |
| 8 | Atrial fibrillation | 0.18 | apixaban | Eliquis | 5 or 2.5 mg | 1 bd | 0.50 | B01AF02 | Y |
| | | | rivaroxaban | Xarelto | 20 or 15 mg | 1 daily | 0.28 | B01AF01 | Y |
| | | | warfarin | Marevan, Coumadin | 1, 2, 3, 5 mg | variable per INR | 0.17 | B01AA03 | Y |
| | | | dabigatran | Pradaxa | 110, 150 mg | 1 bd | 0.05 | B01AE07 | Y |
| | | | add-on digoxin | Lanoxin, Lanoxin PG | 62.5, 125 microgram | 1 daily | +0.12 | C01AA05 | Y (ext) |
| | | | add-on sotalol | Sotacor | 80 mg | 1 bd | +0.08 | C07AA07 | N |
| | | | add-on diltiazem CD | Cardizem CD | 180, 240 mg | 1 daily | +0.10 | C08DB01 | N |
| 9 | Osteoporosis | F 0.25, M 0.05 | denosumab | Prolia | 60 mg | 6-monthly SC | 0.40 | M05BX04 | N |
| | | | alendronate | Fosamax | 70 mg | weekly | 0.20 | M05BA04 | N |
| | | | alendronate/colecalciferol | Fosamax Plus | 70 mg/140 microgram | weekly | 0.15 | M05BB03 | N |
| | | | risedronate | Actonel | 35 mg / 150 mg | weekly / monthly | 0.15 | M05BA07 | N |
| | | | zoledronic acid | Aclasta | 5 mg | yearly IV | 0.10 | M05BA08 | N |
| | | | add-on colecalciferol (OTC) | Ostelin | 1000 IU | 1 daily | +0.50 | A11CC05 | N |
| 10 | BPH / bladder | M 0.20 (mirabegron F 0.06) | tamsulosin MR | Flomax | 400 microgram | 1 daily | 0.55 | G04CA02 | N |
| | | | dutasteride/tamsulosin | Duodart | 0.5/0.4 mg | 1 daily | 0.30 | G04CA52 | N |
| | | | mirabegron | Betmiga | 25, 50 mg | 1 daily | 0.15 | G04BD12 | N |
| 11 | COPD / asthma | 0.15 | tiotropium | Spiriva | 18 microgram | 1 daily INH | 0.25 | R03BB04 | N |
| | | | budesonide/formoterol | Symbicort | 200/6 microgram | 2 puffs bd | 0.20 | R03AK07 | N |
| | | | fluticasone/salmeterol | Seretide | 250/25 microgram | 2 puffs bd | 0.15 | R03AK06 | N |
| | | | fluticasone furoate/umeclidinium/vilanterol | Trelegy Ellipta | 100/62.5/25 microgram | 1 daily | 0.25 | R03AL08 | N |
| | | | umeclidinium/vilanterol | Anoro Ellipta | 62.5/25 microgram | 1 daily | 0.15 | R03AL03 | N |
| | | | add-on salbutamol | Ventolin, Asmol | 100 microgram/dose | 2 puffs prn | +0.80 | R03AC02 | N |
| 12 | Heart failure | 0.12 | furosemide | Lasix, Urex | 20 to 80 mg | 1 mane | 0.45 | C03CA01 | N |
| | | | sacubitril/valsartan | Entresto | 24/26 to 97/103 mg | 1 bd | 0.20 | C09DX04 | N |
| | | | bisoprolol | Bicor | 1.25 to 10 mg | 1 daily | 0.20 | C07AB07 | N |
| | | | carvedilol | Dilatrend | 6.25 to 25 mg | 1 bd | 0.10 | C07AG02 | N |
| | | | eplerenone | Inspra | 25 mg | 1 daily | 0.05 | C03DA04 | N |
| | | | add-on spironolactone | Aldactone | 25 mg | 1 daily | +0.40 | C03DA01 | N |
| | | | add-on dapagliflozin | Forxiga | 10 mg | 1 daily | +0.35 | A10BK01 | N |
| 13 | Hypothyroidism | F 0.15, M 0.05 | levothyroxine | Eutroxsig, Oroxine | 50 to 150 microgram | 1 mane | 1.00 | H03AA01 | N |
| 14 | Gout / CKD | 0.10 | allopurinol | Zyloprim, Progout | 100, 300 mg | 1 daily | 0.75 | M04AA01 | N |
| | | | febuxostat | Adenuric | 80 mg | 1 daily | 0.10 | M04AA03 | N |
| | | | calcitriol | Rocaltrol | 0.25 microgram | 1 daily | 0.15 | A11CC04 | N |
| 15 | Parkinson's / epilepsy / dementia | 0.06 | levodopa/carbidopa | Sinemet, Kinson | 100/25 mg | 1 tds | 0.35 | N04BA02 | N |
| | | | levodopa/benserazide | Madopar | 100/25 mg | 1 tds | 0.15 | N04BA02 | N |
| | | | levetiracetam | Keppra | 500 mg | 1 bd | 0.25 | N03AX14 | N |
| | | | sodium valproate | Epilim | 500 mg | 1 bd | 0.10 | N03AG01 | N |
| | | | donepezil | Aricept | 5, 10 mg | 1 nocte | 0.15 | N06DA02 | N |
| 16 | RA / PMR | 0.05 | methotrexate oral | Methoblastin | 2.5, 10 mg | 10 to 20 mg once weekly | 0.45 | L04AX03 | Y |
| | | | prednisolone | Panafcortelone, Solone | 1, 5, 25 mg | daily or taper | 0.45 | H02AB06 | Y (ext) |
| | | | hydroxychloroquine | Plaquenil | 200 mg | 1 bd | 0.10 | P01BA02 | N |
| | | | add-on folic acid (with MTX) | Megafol | 5 mg | weekly | +0.95 | B03BB01 | N |

**Exclusion rules and share evidence**

| Rule | Detail |
|---|---|
| Anticoagulants | At most one per patient, except planted duplication |
| RAS blockade | At most one ACE inhibitor or ARB (including combinations); sacubitril/valsartan excludes both |
| Statin shares | Rosuvastatin 17,020,106 vs atorvastatin 11,877,199 scripts in 2023-24 (59:41), applied as 0.52:0.36\[11\] |
| PPI shares | Pantoprazole 10,836,323 vs esomeprazole 8,270,226 scripts (57:43), applied as 0.50:0.38\[11\] |
| SSRI shares | Escitalopram 6,431,014 vs sertraline 6,041,182 scripts\[11\] |
| Anticoagulant shares | **[ASSUMPTION, extrapolated]** June 2016 prevalent users: warfarin 47.0%, rivaroxaban 27.1%, apixaban 18.7%, dabigatran 7.2%. New initiators: rivaroxaban 38.2%, apixaban 30.0%, warfarin 24.3%, dabigatran 7.5%.\[12\] The 2026 apixaban-led mix needs clinician confirmation |
| Apixaban 2.5 mg bd | 35% of apixaban patients aged 80+ **[ASSUMPTION]** |
| Perindopril salts | Arginine 5 mg = erbumine 4 mg. Both forms emitted across sources; must never be flagged |

### 4.3 Combination products (duplication and normalisation traps)

| Combination | AU brand | Duplicates with |
|---|---|---|
| perindopril/indapamide (C09BA04) | Coversyl Plus | perindopril |
| perindopril/amlodipine (C09BB04) | Coveram | amlodipine, perindopril |
| irbesartan/HCT (C09DA04) | Avapro HCT, Karvezide | irbesartan |
| candesartan/HCT (C09DA06) | Atacand Plus | candesartan |
| telmisartan/amlodipine (C09DB04) | Twynsta | amlodipine |
| amlodipine/atorvastatin (C10BX03) | Caduet | Lipitor, Norvasc |
| ezetimibe/rosuvastatin (C10BA06) | Rosuzet | Crestor, Ezetrol |
| ezetimibe/atorvastatin (C10BA05) | Atozet | Lipitor |
| sitagliptin/metformin (A10BD07) | Janumet | Diabex |
| empagliflozin/metformin (A10BD20) | Jardiamet | Jardiance, Diabex |
| aspirin/clopidogrel (B01AC30) | CoPlavix, DuoCover | Cartia, Plavix |
| oxycodone/naloxone (N02AA55) | Targin | Endone |
| alendronate/colecalciferol (M05BB03) | Fosamax Plus | Fosamax |
| dutasteride/tamsulosin (G04CA52) | Duodart | Flomax |
| paracetamol/codeine (N02AJ06) | Panadeine Forte | Panadol Osteo (paracetamol total daily dose) |

---

## 5. Planted discrepancies

### 5.1 Evidence base

| Source | Setting | Numbers used |
|---|---|---|
| Cornish 2005, Arch Intern Med | Canada, 151 patients on 4+ medicines | 53.6% with 1 or more unintended discrepancies; 0.93 per patient; omission 46.4%; 38.6% potential moderate to severe harm\[2\] |
| Tam 2005, CMAJ | Systematic review, 22 studies | 27% to 54% of patients with 1 or more history errors; dose or frequency 30% to 42% of errors; 11% to 59% clinically important\[13\]\[14\] |
| Taylor 2014, Aust Fam Physician | 8 Australian EDs, 414 GP letters | 87% with 1 or more regular-medicine discrepancies; 62% moderate to high significance\[15\] |
| Boyce LE 2013, J Pharm Pract Res | Australian regional (Taree NSW), 48 patients aged 65+ | 75% with 1 or more GP-list discrepancies; "almost half of the discrepancies were related to non-current medications being recorded"; 19% moderate or major |
| Prior SJ, Cheek C, et al. 2019, Healthcare (Basel) | North West Regional Hospital (Burnie, Tasmania) ED, 143 patients | 135 (94%) with 1 or more discrepancies; 67.18 per 100 medicines |
| Elliott 2023, Intern Med J | 2 Australian services, 154 patients | Omission 33.3% of 1,648 current medicines (72.1% OTC); dose-regimen errors 25.1%; commission 16.9%\[8\] |
| Francis 2025, Health Inf Manag | Sydney, 82 patients, My Health Record vs BPMH | 40.8% of 1,207 medicines mismatched; 10.3% of mismatches high-risk\[8\] |
| Ooi 2017, MJA | Melbourne discharge summary RCT | 46.5% absolute reduction in summaries with errors. Cited audit: complete discharge medicine lists in 24%; 44% had none\[16\] |
| BJGP 2018 (UK) | General practice | Discharge medicine changes not made in 17% (124/750). Requests: new 58%, ceased 27%, dose 15%. PRACtICe subset 28%\[17\] |
| Hilditch, HETI NSW (grey) | Rural district hospital | 68% of post-discharge discrepancies unintentional\[18\] |

Calibration: about 100 tune patients x 8.4 medicines = about 840 medication instances. A mean of 2.4 planted findings per patient covers all source pairs. It sits between Cornish's 0.93 per patient (admission chart only) and Elliott's median of 6 per patient (single-source history).\[1\]\[19\]

### 5.2 Planted discrepancy table

Expected tune counts assume 100 patients and 840 medicines.

| Type | Definition | Rate | Tune n (min) | Example | Intent (doc / poss / likely) | Evidence | Oversampled? |
|---|---|---|---|---|---|---|---|
| omission | Current medicine (2 or more community sources) absent from admission_chart | 0.055 per med | 46 (15) | Apixaban in GP and PHM, not charted | 0.30 / 0.15 / 0.55 | Cornish 46.4% of 0.93 = 0.43 per patient | No |
| commission | admission_chart has a medicine not current in truth | 0.20 per patient | 20 (15) | Chart has simvastatin ceased 8 months ago | 0.05 / 0.15 / 0.80 | Elliott commission 16.9% | Mild |
| dose | Total daily dose differs after normalising notation and salts | 0.030 per med | 25 (15) | Chart metoprolol 25 mg bd; truth 50 mg bd | 0.25 / 0.20 / 0.55 | Tam 30% to 42%; Elliott 25.1% | No |
| frequency | Same per-dose amount, different interval | 0.020 per med | 17 (15) | Alendronate charted daily; truth weekly | 0.10 / 0.20 / 0.70 | Tam | Mild |
| formulation | IR vs MR mismatch (metformin, metoprolol, gliclazide, oxycodone, paracetamol, venlafaxine, tamsulosin) | 0.15 per eligible patient | 15 (15) | Chart metformin IR 1 g bd; truth Diabex XR 2 g nocte | 0.10 / 0.20 / 0.70 | Tam lists dosage-form errors, no rate | **[OVERSAMPLED]** |
| route | Route differs (patch vs SL, SC vs PO) | 0.15 per patient | 15 (15) | GP buprenorphine patch; chart buprenorphine SL | 0.15 / 0.25 / 0.60 | Rare in literature | **[OVERSAMPLED]** |
| duplication | Ingredient sets intersect across 2 active entries | 0.18 per patient | 18 (15) | GP lists Caduet and Lipitor | 0.00 / 0.20 / 0.80 | Section 4.3; no Australian rate | **[OVERSAMPLED]** |
| stale_listing | GP active, supply arithmetic says possibly ceased, truth ceased | 0.040 per GP active med | 34 (15) | GP Somac active; last dispense 11 months ago | 0.00 / 0.30 / 0.70 | Boyce; Elliott 16.9% | No |
| dose_unconfirmable | High-risk regimen changed without new script (warfarin phone dose, insulin titration, steroid taper) | 0.85 per eligible patient | 15 (15) | Warfarin changed by phone to 4/5 mg alternating; GP "5 mg daily" | 0.00 / 0.60 / 0.40 | Mechanism; no rate | **[OVERSAMPLED]** (5.4) |
| unpropagated_discharge_change | prior_discharge action not reflected in GP and/or pharmacy | 0.25 per discharge action | 18 (15) | Discharge furosemide 40 to 20 mg; GP and PHM still 40 mg | 0.00 / 0.25 / 0.75 | UK 17%; PRACtICe 28%; NSW 68% unintentional | Mild |
| identity_uncertain | Linkage not resolvable with confidence and affects 1 or more medicines | 0.18 per patient | 18 (15) | PHM "SMITH, Peg", DOB swapped, no IHI | n/a | Section 7 | **[OVERSAMPLED]** |

**Targets and intent rules**

| Item | Value |
|---|---|
| Total | About 2.4 findings per patient (about 241 per split); heldout uses identical rates with fresh draws |
| High-risk share | About 40% of findings involve an APINCHS or extension class; per-med planting on high-risk medicines x1.5. **[ASSUMPTION]** A Spanish ED study (Pharmaceuticals 2024) found 52.5% of discrepancies involved high-alert medicines\[20\] |
| documented_intentional | chart_note or action_reason explains it ("withheld: contrast" for metformin, "withheld: AKI" for ACE inhibitor) |
| possibly_intentional | Plausible but undocumented reason (antihypertensive omitted with low charted BP) |
| likely_unintentional | No plausible reason |
| Overall intent mix | 15% / 25% / 60% **[ASSUMPTION]**. A Brazilian study found 72% intentional, 8% undocumented intentional, 20% unintentional among all admission discrepancies.\[21\] MedTrace plants only reconcilable discrepancies, so the unintentional share is higher |

### 5.3 Never-flag negative controls (about 1.5 per patient; any finding raised counts as a false positive)

| Pattern | Example | Rate |
|---|---|---|
| Brand-only | Lipitor 40 mg vs atorvastatin 40 mg | 0.35 of medicines branded in 1 or more sources |
| Notation-only | "1 tab bd" vs "twice daily" vs `bd` | All GP and patient rows use free-text variants |
| Equivalent daily dose | 2 x 20 mg vs 40 mg daily (same formulation); perindopril arginine 5 mg = erbumine 4 mg. Metoprolol IR 50 mg bd vs MR 100 mg daily is NOT equivalent | 0.10 per patient |
| Correctly propagated discharge cease | "cease: dizziness"; absent everywhere since | 0.40 of cease actions |

### 5.4 High-risk eligibility uplift (both splits) **[OVERSAMPLED]**

| Agent | Natural tune patients | Uplift | Tune patients |
|---|---|---|---|
| warfarin | 0.18 x 0.17 x 100 = 3 | AF warfarin share 0.17 to 0.30 | 5.4 |
| insulin | 3 | +0.20 add-on in non-insulin T2DM | 9 |
| prednisolone taper | 2 | +4 forced cases per split | 6 |
| Total eligible | about 8 | | about 20; x0.85 gives about 17 dose_unconfirmable |

---

## 6. Notices and coverage gaps

Notices are scored separately on patient_key, type and row_id overlap.

| Notice | Trigger | Rate | Evidence | Flag |
|---|---|---|---|---|
| coverage_gap | Patient absent from a source | gp 8%; patient 5% (delirium, no carer); pharmacy 3% | ABS 2024-25: 93.9% of people aged 65 to 74 and 97.3% aged 85+ saw a GP; 67.2% could always see their preferred GP\[6\] | GP **[OVERSAMPLED]** about 2x |
| bpmh_not_confirmable | Fewer than 2 medicine sources (ACSQHC NSQHS Standard 4, Action 4.5) | 4 patients per split | Standard 4.5; WHO High 5s SOP | **[ASSUMPTION]** |
| possible_second_pharmacy | Dispensing split across 2 pharmacies, 1 exposed | 10% of patients; 30% to 50% of their medicines hidden | No Australian rate. Netherlands (Buurma 2008): 10.8% multi-pharmacy "shoppers". US: people aged 65+ less likely to use multiple pharmacies (OR 0.49)\[22\]\[23\] | International proxy |
| patient_only_item | OTC or complementary item only in patient source | 66% of patients; Poisson mean 1.1 items among users (fish oil, glucosamine, vitamin D, magnesium, turmeric, OTC paracetamol) | ASPREE (70+): 66.2% used 1 or more in past month; 12.2% more than 3. Elliott: 72.1% of omissions OTC. Australian adults 49.4% in 12 months\[5\]\[8\]\[24\] | Evidence-based |
| conflict_abstained | 3 sources disagree, no majority or recency winner | 5% of patients | Mechanism | **[ASSUMPTION]** |
| stale_document | GP list_last_updated more than 12 months old, or prior_discharge more than 180 days | 15% of GP records | Boyce; Ooi | **[ASSUMPTION]** |

**Coverage scenarios (recorded in `coverage_truth`)**

| Scenario | Rate | Evidence / flag |
|---|---|---|
| No GP record | 8% | **[OVERSAMPLED]** |
| GP record under near-miss name | 6% | Section 7 |
| Two pharmacies, one exposed | 10% | Buurma 2008 proxy |
| Private (non-PBS) scripts | 4% of dispensed instances; pbs_code null, script_type `private` | No official private-script estimate since 2012 (Australian Statistics on Medicines 2015); under co-payment PBS items captured since April 2012\[25\]\[26\] **[ASSUMPTION]** |
| Prior discharge in last 180 days | 35% of patients; 2 to 4 actions (start 0.58, cease 0.27, change 0.15)\[17\] | Action mix BJGP 2018 **[OVERSAMPLED]** for readmission enrichment |
| Partial propagation | 40% of unpropagated actions reach 1 of 2 community sources | **[ASSUMPTION]** |
| My Health Record | Not a source. Opt-out 9.9% (2,517,921 people; 90.1% participation). Francis 2025: 82/91 screened inpatients had a record\[27\]\[28\]\[29\] | Context only |

---

## 7. Identity corruption operators

Applied after truth generation; recorded in `corruptions` with operator, source, row_ids, before and after.

| Operator | Source(s) and rate | Example | Evidence | Flag |
|---|---|---|---|---|
| missing_ihi | emr 5%, gp 20%, pharmacy 30%, patient 70% | ihi_syn null | Fixed design | Design |
| nickname | gp 15%, patient 25%, pharmacy 3%, emr 1% (where a nickname exists) | Margaret to Peggy | Section 10.2 | **[ASSUMPTION]** |
| maiden_married_surname | 8% of females; gp previous_surname set, 1 non-emr source uses other surname | emr "Jones"; pharmacy "SMITH, Margaret" | No Australian rate | **[ASSUMPTION]** |
| dob_day_month_swap | patient 4%, gp 1%, pharmacy 1% (day 12 or less) | 03/07/1946 vs 07/03/1946 | UK HES-PDS: DOB errors 0.11% of records (Hagger-Johnson 2017)\[30\] | **[OVERSAMPLED]** |
| single_char_typo | Name: patient 8%, gp 3%, pharmacy 3%, emr 1%. DOB digit: patient 2% | "Margret"; 1964 for 1946 | UK: NHS number missing or wrong 30%\[30\] | **[ASSUMPTION]** |
| address_move | 10% of patients; 1 non-emr source has old postcode | 3056 vs 3070 | UK: postcode disagreement 53%\[30\] | **[ASSUMPTION]** conservative |
| same_source_duplicate | emr 3%, gp 2%, pharmacy 2% | 2 MRNs, one without IHI | US: 8% to 12% typical MPI duplication, best practice 2%, target under 5% (AHIMA); 2.9% in one EMPI study\[31\]\[32\] | International |
| lookalike_pair | 3 pairs per split; same name and DOB, different person | 2 "John Smith 01/01/1945" | False-merge target 0 | Design |
| twins | 1 pair per split; same surname, DOB, postcode | "Edna" and "Edith Brown" | Design | Design |
| overlay | 1 per split; one pharmacy cust_no mixes 2 people | 3 dispensings of B under A | Design | Design |

Identity is scored pairwise over all record pairs. Any merge across `identity_traps` counts toward false-merge rate.

---

## 8. Hidden per-source error rates and trust priors

- `hidden_error_rates[source][attribute]` is the probability a source value is wrong; the generator applies it.
- `trust_prior` seeds H-MEM and is deliberately not 1 minus hidden error.
- Feedback deltas: helpful +0.05, not_helpful -0.03, wrong -0.20.
- Trust MAE = mean over cells of |learned_trust - (1 - hidden_error)|.

| Source | Attribute | Hidden error | Prior | Justification |
|---|---|---|---|---|
| emr | existence (omission) | 0.055 | 0.85 | Cornish 0.43 omissions per patient |
| emr | existence (commission) | 0.024 | 0.90 | 0.20 per patient / 8.4 medicines |
| emr | dose | 0.030 | 0.85 | Tam |
| emr | frequency | 0.020 | 0.85 | Tam |
| emr | identity | 0.01 | 0.95 | UK DOB error 0.11%\[30\] |
| gp | existence (non-current) | 0.12 | 0.80 | Elliott 16.9%; Boyce about half non-current |
| gp | existence (omission) | 0.08 | 0.80 | Taylor 87% of letters with discrepancies |
| gp | dose | 0.08 | 0.75 | Prior 2019: 67.18 per 100 medicines; dose and frequency given in 51% of referral letters |
| gp | frequency | 0.06 | 0.75 | as above |
| gp | name | 0.18 | 0.85 | Section 7 |
| gp | DOB | 0.02 | 0.95 | Section 7 |
| pharmacy | existence (Rx omission) | 0.14 | 0.80 | Private 4% + second pharmacy 10% x 40% + OTC invisible; Elliott omission 33.3% |
| pharmacy | existence (commission) | 0.06 | 0.85 | Recent dispense before cessation |
| pharmacy | dose (inferred) | 0.12 | 0.70 | No directions; Elliott 25.1% dose-regimen errors |
| pharmacy | strength / form | 0.01 | 0.95 | Dispensed product |
| pharmacy | name | 0.05 | 0.90 | Section 7 |
| pharmacy | DOB | 0.01 | 0.95 | Section 7 |
| patient | existence (Rx omission) | 0.15 | 0.65 | Patient-GP medicine-level discrepancy 23% (PIL study, BMC Prim Care 2026; 24 GP centres and 17 community pharmacies in the Netherlands) |
| patient | existence (complementary/OTC) | 0.02 | 0.90 | Only source; ASPREE 66.2% |
| patient | dose | 0.18 | 0.55 | Free text without strength |
| patient | frequency | 0.12 | 0.65 | Free text |
| patient | med name | 0.25 | 0.60 | Lay terms (10.3) **[ASSUMPTION]** |
| patient | DOB | 0.06 | 0.80 | Swap 4% + typo 2% |
| patient | still_taking | 0.08 | 0.85 | Best source for actual use (BPMH principle) |

Mean priors: emr 0.88, gp 0.82, pharmacy 0.85, patient 0.72. Target: learned trust cuts MAE by 50% or more over 100 tune patients. **[ASSUMPTION]**

---

## 9. Dispensing and timeline rules

### 9.1 Timeline

| Rule | Value |
|---|---|
| Start / stop | start = as_of minus uniform(60, 3650) days; current stop = null; ceased stop = as_of minus uniform(30, 365) |
| Ceased medicines | Poisson mean 1.5 per patient in last 12 months **[ASSUMPTION]** |
| GP retention of ceased medicine | active 0.30 (stale listing source, consistent with Boyce), ceased 0.60, deleted 0.10 **[ASSUMPTION]** |
| Dose changes | 0.08 per non-high-risk medicine in last 12 months, with new script, changed_by_phone false |
| true_daily_dose_mg | dose x doses/day; weekly agents dose/7; patches microgram/h x 24 / 1000 |

### 9.2 Packs, quantities, repeats

| Rule | Value | Source |
|---|---|---|
| Pack size, max quantity | From PBS API CSV bundle per item; fallback 30 daily, 60 bd, 4 weekly bisphosphonate, 1 denosumab, 1 inhaler | PBS schedule |
| 60-day dispensing | 40% of dispensings of eligible items use 2 packs (e.g. amlodipine 5 mg max 60, 5 repeats; apixaban 5 mg max 120, 5 repeats; allopurinol 300 mg max 120, 2 repeats)\[33\] | PBS 60-day list (almost 300 medicines); 40% uptake **[ASSUMPTION]**\[34\]\[35\] |
| Repeats | 5 default; warfarin and opioids 0 to 2; resets on new script | **[ASSUMPTION]** |
| Script lifetime | 12 months | Department of Health 60-day FAQ\[36\] |
| days_supply | qty / units_per_day; PRN qty / (0.5 x max daily); warfarin qty / mean daily tablets | Derived |
| Lookback | 12 months | **[ASSUMPTION]** |
| Visit realism | 20 to 40 dispensings per patient-year | Quek 2025: median 16 pharmacy visits and 31 PBS dispensings per year for people aged 65+\[37\]\[38\] |

### 9.3 Adherence and jitter

| Rule | Value | Evidence |
|---|---|---|
| PDC per patient-medicine | Beta(6, 1.5): mean 0.80, P(PDC 0.8 or more) about 0.60 | Ofori-Asenso 2019: 55.1% of older new statin users had PDC under 0.80 in year 1. de Oliveira Costa 2023: 40.5% to 53.2% of statin initiators had PDC 0.8 or more; adherence rises with age.\[8\] Prevalent users set higher **[ASSUMPTION]** |
| Refill interval | days_supply / PDC + Normal(0, 3) days, minimum 0.6 x days_supply | **[ASSUMPTION]** |
| Silent patient stop | 3% of current medicines stopped more than 90 days ago (truth ceased, GP active, patient `no`) | de Oliveira Costa: about 50% of initiators discontinue in year 1;\[8\] prevalent users far lower **[ASSUMPTION]** |

### 9.4 Possibly-ceased rule

`possibly_ceased = (as_of - (last_dispensed_on + days_supply)) > 90 days`

- The 90-day grace matches the discontinuation definition (90 or more days without coverage) used by Ofori-Asenso 2019 and de Oliveira Costa 2023.\[8\]\[39\]
- Suppressed for private-script items, possible_second_pharmacy patients, and PRN, 6-monthly or yearly items. These raise a notice instead.

### 9.5 Warfarin, insulin and steroid cases (dose_unconfirmable)

| Rule | Value |
|---|---|
| Warfarin INR-driven change in last 28 days | 0.70 of warfarin patients **[ASSUMPTION]** |
| Mechanism | Phone instruction; changed_by_phone true; no new script; same tablets dispensed |
| GP directions | 50% "as directed per INR"; 50% stale fixed dose |
| Patient | 60% describe current alternating regimen; 40% "unsure" |
| Insulin | Titration only in patient source; GP "as directed" 60% |
| Prednisolone taper | Schedule in prior_discharge; current step only from patient |
| Expected output | dose_unconfirmable with high_risk_class; never auto-resolved to one source |

---

## 10. Reference tables

### 10.1 APINCHS-to-ATC mapping (40 rows; longest prefix wins)

Core: ACSQHC APINCHS. WA Health adds antiarrhythmics and psychotropics. SA Health APINCHEN adds psychotropics (clozapine, lithium, depots), epidural/intrathecal agents and neuromuscular blockers. Extensions (digoxin, oral hypoglycaemics, oral methotrexate) follow facility-policy examples (ezymed, grey literature).\[40\]\[41\]\[42\]\[43\]

| # | Class | ATC prefix | Examples | Source |
|---|---|---|---|---|
| 1 | A aminoglycosides | J01GB | gentamicin, tobramycin, amikacin | ACSQHC |
| 2 | A glycopeptides | J01XA | vancomycin | ACSQHC |
| 3 | A amphotericin | J02AA01 | amphotericin B | ACSQHC |
| 4 | A other antibacterials (flag only) | J01 | all | Extension |
| 5 | P potassium | A12BA | potassium chloride | ACSQHC |
| 6 | P IV electrolyte concentrates | B05XA | KCl, hypertonic NaCl | ACSQHC |
| 7 | P magnesium | A12CC | magnesium sulfate | ACSQHC |
| 8 | P calcium | A12AA | calcium gluconate | ACSQHC |
| 9 | I fast-acting | A10AB | aspart, lispro | ACSQHC |
| 10 | I intermediate | A10AC | isophane | ACSQHC |
| 11 | I premixed | A10AD | aspart/protamine | ACSQHC |
| 12 | I long-acting | A10AE | glargine, degludec | ACSQHC |
| 13 | N opium alkaloids | N02AA | morphine, oxycodone, hydromorphone | ACSQHC |
| 14 | N phenylpiperidines | N02AB | fentanyl | ACSQHC |
| 15 | N oripavines | N02AE | buprenorphine | ACSQHC |
| 16 | N opioid combinations | N02AJ | paracetamol/codeine | ACSQHC |
| 17 | N other opioids | N02AX | tramadol, tapentadol | ACSQHC |
| 18 | N methadone | N07BC02 | methadone | ACSQHC |
| 19 | N benzodiazepine anxiolytics | N05BA | diazepam, oxazepam | ACSQHC |
| 20 | N benzodiazepine hypnotics | N05CD | temazepam, midazolam | ACSQHC |
| 21 | N Z-drugs | N05CF | zolpidem, zopiclone | Extension |
| 22 | N anaesthetics | N01AX10, N01AF | propofol, thiopental | ACSQHC |
| 23 | C antineoplastics | L01 | all | ACSQHC |
| 24 | C vinca alkaloids | L01CA | vincristine | ACSQHC |
| 25 | C etoposide | L01CB | etoposide | ACSQHC |
| 26 | C methotrexate (oncology) | L01BA01 | methotrexate | ACSQHC |
| 27 | C methotrexate (oral weekly) | L04AX03 | methotrexate | ACSQHC + extension |
| 28 | C azathioprine | L04AX01 | azathioprine | ACSQHC |
| 29 | H vitamin K antagonists | B01AA | warfarin | ACSQHC |
| 30 | H heparins | B01AB | heparin, enoxaparin | ACSQHC |
| 31 | H direct thrombin inhibitors | B01AE | dabigatran | ACSQHC |
| 32 | H factor Xa inhibitors | B01AF | apixaban, rivaroxaban | ACSQHC |
| 33 | H thrombolytics | B01AD | alteplase, tenecteplase | ACSQHC |
| 34 | Ext digoxin | C01AA05 | digoxin | Extension |
| 35 | Ext antiarrhythmics III | C01BD | amiodarone | WA APINCHS |
| 36 | Ext sulfonylureas | A10BB | gliclazide, glimepiride | Extension |
| 37 | Ext SU combinations | A10BD02 | metformin/glibenclamide | Extension |
| 38 | Ext clozapine | N05AH02 | clozapine | SA APINCHEN |
| 39 | Ext lithium | N05AN01 | lithium | SA APINCHEN |
| 40 | Ext neuromuscular blockers | M03AC, M03AB | rocuronium, suxamethonium | SA APINCHEN |

Notes:
- Prednisolone (H02AB) is not APINCHS; it carries `high_risk_class = "steroid_taper_ext"` for dose_unconfirmable only.
- Methotrexate is mapped under both L01BA01 and L04AX03, because the PBS primary ATC for low-strength oral tablets usually returns L04AX03.

### 10.2 Nickname table (about 100 pairs)

| Item | Value |
|---|---|
| Public source | carltonnorthern/nicknames (GitHub; PyPI `nicknames`; Apache-2.0): hand-curated `names.csv`, about 1,100 canonical English given names\[44\]\[45\] |
| Caveats | US genealogy origin; repository states it is heavily biased towards traditionally African American names; not census-derived\[44\] |
| Approach | Hand-select about 100 pairs suited to Australians born 1936 to 1966; store as `data/reference/nicknames.csv` with licence attribution |
| Examples | Margaret: Peggy, Peg, Maggie; Elizabeth: Betty, Liz; Patricia: Pat, Trish; Dorothy: Dot; Beverley: Bev; Robert: Bob; William: Bill; Richard: Dick; John: Jack; Edward: Ted; Geoffrey: Geoff; Michael: Mick |

### 10.3 Lay-term mapping (patient source)

| Lay description | Maps to | ATC | Rule |
|---|---|---|---|
| "blood thinner", "clot pill" | anticoagulant or antiplatelet | B01AA, B01AF, B01AE, B01AC | If both anticoagulant and aspirin present, mark ambiguous |
| "water tablet", "fluid pill" | diuretic | C03, or C09BA/C09DA combinations | Prefer C03CA if furosemide present |
| "puffer", "blue puffer" | reliever | R03AC02 | |
| "preventer puffer" | ICS/LABA | R03AK, R03AL | |
| "sugar tablet", "diabetes tablet" | oral glucose-lowering | A10B | |
| "my insulin", "the pen" | insulin or GLP-1 | A10A, A10BJ | Pen ambiguous |
| "cholesterol tablet" | statin or ezetimibe | C10A, C10B | |
| "blood pressure tablet" | antihypertensive | C02, C03, C07, C08, C09 | Low confidence |
| "heart tablet" | ambiguous | C01, C07, C08, B01AC | Low confidence |
| "spray under the tongue" | nitrate | C01DA02 | |
| "thyroid tablet" | levothyroxine | H03AA01 | |
| "stomach / reflux tablet" | PPI or H2 | A02BC, A02BA | |
| "pain killer", "arthritis Panadol" | analgesic | N02BE01, N02A | Osteo implies MR |
| "sleeping tablet" | hypnotic | N05CD, N05CF | |
| "nerve tablet" | antidepressant or anxiolytic | N06A, N05BA | |
| "bone tablet", "bone injection" | bisphosphonate or denosumab | M05BA, M05BB, M05BX04 | Injection implies denosumab |
| "gout tablet" | allopurinol | M04AA01 | |
| "prostate tablet", "waterworks tablet" | alpha-blocker or 5-ARI | G04CA | |
| "patch" | opioid or nitrate patch | N02AB03, N02AE01, C01DA02 | |
| "fish oil", "glucosamine", "turmeric", "vitamin D", "magnesium" | complementary / OTC | none, A11CC05, A12CC | patient_only_item |

Patient medicine row mix: 25% lay term, 45% brand, 20% generic (8% of all rows misspelt), 10% vague ("a little white one"). **[ASSUMPTION]**

---

## 11. Ground truth format and evaluation

### 11.1 Schema (`data/synthetic/ground_truth.json`, never served to agents)

```json
{
  "seed": 20261024,
  "generator_version": "1.0.0",
  "as_of": "2026-10-24",
  "hidden_error_rates": {"gp": {"existence_noncurrent": 0.12, "dose": 0.08}, "pharmacy": {"dose": 0.12}, "patient": {"med_name": 0.25}, "emr": {"existence_omission": 0.055}},
  "split": {"tune": ["P0001"], "heldout": ["P0101"]},
  "patients": [{
    "patient_key": "P0001",
    "true_links": {"emr": ["MRN1000001"], "gp": ["GPP200001"], "pharmacy": ["C300001"], "patient": ["INT40001"]},
    "coverage_truth": {"gp_present": true, "second_pharmacy_hidden": true, "private_script_items": ["atorvastatin"], "prior_discharge": true},
    "corruptions": [{"operator": "nickname", "source": "gp", "row_ids": ["GP-000013"], "field": "first_name", "before": "Margaret", "after": "Peggy"}],
    "identity_traps": [{"kind": "lookalike_pair", "other_patient_key": "P0057"}],
    "timeline": [{"generic": "warfarin", "start": "2019-03-02", "stop": null, "true_daily_dose_mg": 4.57, "changed_by_phone": true}],
    "planted": [{"id": "F0001-01", "type": "dose_unconfirmable", "generic": "warfarin", "sources_involved": ["gp", "pharmacy", "patient"], "row_ids": ["GP-000015", "PHM-000102", "PAT-000044"], "high_risk_class": "H", "intent": "possibly_intentional"}],
    "notices": [{"type": "possible_second_pharmacy", "row_ids": ["PHM-000101"]}],
    "negative_controls": [{"kind": "equivalent_daily_dose", "generic": "perindopril", "row_ids": ["EMR-000021", "GP-000011"]}]
  }]
}
```

The full `hidden_error_rates` object holds every cell in section 8. `negative_controls` is a suggested addition. **[SUGGESTION]**

### 11.2 Matching rule and metrics

| Metric | Definition | Target |
|---|---|---|
| Finding TP | Same patient_key, type and generic (normalised to MP), with row_ids overlap; one-to-one greedy by largest overlap | n/a |
| Per-type P / R / F1 | Wilson 95% CI, z = 1.96 | Report on heldout |
| Notice P / R | Same rule on patient_key and type | Report |
| Identity | Pairwise precision, recall, F1 over all record pairs | F1 0.95 or more **[ASSUMPTION]** |
| False-merge rate | Wrong same-patient pairs / predicted same-patient pairs | 0 |
| False-cessation rate | Active-in-truth medicines labelled ceased / all active medicines | 0 |
| APINCHS recall | Detected high-risk findings / planted high-risk findings | 100% |
| Alerts per patient | (findings + notices) / patients | 4 or fewer |
| Normalisation top-1 | Predicted MP = truth MP | 0.95 structured, 0.85 patient free text **[ASSUMPTION]** |
| Trust MAE | Mean abs(learned_trust - (1 - hidden_error)) | 50% or more below prior MAE |

---

## 12. Clinical choices to review

| # | Judgement call | Chosen value | Evidence | Confidence |
|---|---|---|---|---|
| 1 | Bundle weights | HTN 0.70, lipids 0.65, GORD 0.40, pain 0.30, T2DM 0.28, depression 0.25, IHD 0.25, AF 0.18 | Ordered to PBS ranks (Australian Prescriber 2023-24) and AIHW narrative; not measured prevalence\[11\] | Low to moderate |
| 2 | Anticoagulant mix 2026 | apixaban 0.50, rivaroxaban 0.28, warfarin 0.17, dabigatran 0.05 | June 2016 initiators trend extrapolated | Low |
| 3 | Finding rate | 2.4 per patient; omission 0.055 per medicine | Cornish 0.93 per patient; Elliott median 6 | Moderate |
| 4 | Intent mix | 15 / 25 / 60 | Thin; Brazil 72% intentional; NSW 68% unintentional post-discharge | Low |
| 5 | GP non-current error | 0.12 per medicine | Elliott 16.9%; Boyce | Moderate |
| 6 | Possibly-ceased grace | 90 days | Ofori-Asenso 2019; de Oliveira Costa 2023 | Moderate to high |
| 7 | APINCHS extensions | digoxin, sulfonylureas, oral methotrexate, amiodarone, clozapine, lithium; steroid taper for dose_unconfirmable only | ACSQHC; SA APINCHEN; WA APINCHS | Moderate |
| 8 | Unpropagated discharge rate | 0.25 per action | UK 17%; PRACtICe 28% | Low to moderate |
| 9 | Trust priors | emr 0.88, gp 0.82, pharmacy 0.85, patient 0.72 | Section 8; offset by design | Design |
| 10 | Multi-pharmacy, private scripts | 10% of patients; 4% of items | Dutch 10.8%; no official estimate since 2012 | Low |

---

## 13. Caveats

- No Australian rates were found for multi-pharmacy use in people aged 65+, private-script share, nickname or surname-change prevalence, DOB transposition, or discharge-to-GP propagation failure. International proxies or assumptions are used.
- No AIHW or ABS condition-prevalence figures were retrieved, so bundle weights are ranked by PBS utilisation.
- AIHW polypharmacy figures come from the AIHW web report "Polypharmacy in Australia in 2025" (published 7 Oct 2026). It defines "regular" as dispensed on 4 or more occasions in the year, and its PBS/RPBS data exclude private prescriptions, so it undercounts relative to MedTrace's all-source medicine lists.
- Duplicate-record and identifier-error rates are US (AHIMA) and UK (HES-PDS) data.\[30\]\[31\]

---

## 14. References

1. Cornish PL, et al. Arch Intern Med. 2005;165(4):424-429. doi:10.1001/archinte.165.4.424
2. Tam VC, et al. CMAJ. 2005;173(5):510-515. doi:10.1503/cmaj.045311
3. Taylor S, et al. Aust Fam Physician. 2014;43(10):728. PMID 25286433
4. Boyce LE. Audit of general practitioner medication lists for older patients at a regional hospital. J Pharm Pract Res. 2013. doi:10.1002/j.2055-2335.2013.tb00230.x
5. Prior SJ, Cheek C, et al. Healthcare (Basel). 2019;7(4):152. PMID 31795186. doi:10.3390/healthcare7040152
6. Referral letters to the ED. PMID 25803952
7. Elliott RA, et al. Intern Med J. 2023;53(6):1002-1009. doi:10.1111/imj.15857
8. Francis M, et al. Health Inf Manag. 2025;54(2):150-159. doi:10.1177/18333583241270215
9. Ooi CE, et al. Med J Aust. 2017;206(1)
10. Br J Gen Pract. 2018. PMC6058631
11. Hilditch J. HETI NSW report
12. AIHW. Polypharmacy in Australia in 2025. Published 7 Oct 2026 (aihw.gov.au)
13. Page AT, et al. Med J Aust. 2019;211(2)
14. Quek HW, et al. J Am Med Dir Assoc. 2025;26(11):105827. doi:10.1016/j.jamda.2025.105827
15. Pharmacy. 2018;6(4):134. doi:10.3390/pharmacy6040134
16. Aust Prescr. 2024;47(6):194. doi:10.18773/austprescr.2024.048
17. PLoS One. 2018. doi:10.1371/journal.pone.0208824
18. Heart Lung Circ. 2018 (NOACs in AF)
19. ABS. Patient Experiences, 2023-24 and 2024-25
20. ANAO. My Health Record, 2019; iTnews
21. Fravel MA, et al. J Am Geriatr Soc. 2023. doi:10.1111/jgs.18305
22. Prevalence and characteristics of Australians' complementary medicine product use. Nutrients. 2023;15(2):327. PMID 36678198. doi:10.3390/nu15020327
23. ACSQHC. APINCHS; NSQHS Standard 4
24. SA Health; WA Health; Ezymed
25. WHO High 5s SOP
26. Hagger-Johnson G, et al. BMC Med Res Methodol. 2017. doi:10.1186/s12874-017-0306-8
27. AHIMA; PMC11710899
28. Ofori-Asenso R, et al. Br J Clin Pharmacol. 2019;85(1):227-235. doi:10.1111/bcp.13797
29. de Oliveira Costa J, et al. J Am Heart Assoc. 2023;12(13):e030264. doi:10.1161/JAHA.122.030264
30. Australian Statistics on Medicines 2015
31. Buurma H, et al. J Clin Pharm Ther. 2008. doi:10.1111/j.1365-2710.2008.00878.x
32. PBS 60-day item codes; Department of Health FAQ (2024)
33. Pharmaceuticals. 2024. PMC11054114
34. BMC Prim Care. 2026 (PIL study, Netherlands). PMID 42062934. doi:10.1186/s12875-026-03332-3
35. carltonnorthern/nicknames, Apache-2.0

## Sources

1. [Unintended Medication Discrepancies at the Time of Hospital Admission](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/486421)
2. [Unintended medication discrepancies at the time of hospital admission - PubMed](https://pubmed.ncbi.nlm.nih.gov/15738372/)
3. [1.9 million Australians are taking five or more medicines - Australian Pharmacist](https://www.australianpharmacist.com.au/1-9-million-australians-are-taking-five-or-more-medicines/)
4. [newsGP - Polypharmacy among almost two million Australians](https://www1.racgp.org.au/newsgp/clinical/polypharmacy-among-almost-two-million-australians)
5. [Dietary supplement and complementary and alternative medicine use among older adults in Australia and the United States - Fravel - 2023 - Journal of the American Geriatrics Society - Wiley Online Library](https://agsjournals.onlinelibrary.wiley.com/doi/full/10.1111/jgs.18305)
6. [Patient Experiences, 2024-25 financial year](https://www.abs.gov.au/statistics/health/health-services/patient-experiences/latest-release)
7. [Polypharmacy hits 40% of over-75s - Dermatology Republic](https://www.dermatologyrepublic.com.au/polypharmacy-hits-40-of-over-75s/2876)
8. mcp\_\_PubMed\_\_get\_article\_metadata
9. [Patterns of Medication Dispensation for Multiple Comorbidities among Older Adults in Australia](https://doi.org/10.3390/pharmacy6040134)
10. [Pharmacy (Dec 2018)](https://doaj.org/article/7cadf080ef084d899849cc8809737463)
11. [Top 10 drugs 2023–24 - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11703566/)
12. [Rapid and substantial increases in anticoagulant use and expenditure in Australia following the introduction of new types of oral anticoagulants](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0208824)
13. [Frequency, type and clinical importance of medication history errors at admission to hospital: a systematic review](https://www.cmaj.ca/content/173/5/510)
14. [(PDF) Value of Medication Reconciliation in Reducing Medication Errors on Admission to Hospital](https://www.researchgate.net/publication/43522054_Value_of_Medication_Reconciliation_in_Reducing_Medication_Errors_on_Admission_to_Hospital)
15. [Accuracy of general practitioner medication histories for patients presenting to the emergency department - PubMed](https://pubmed.ncbi.nlm.nih.gov/25286433/)
16. [Reducing medication errors in hospital discharge summaries: a randomised controlled trial](https://www.mja.com.au/journal/2017/206/1/reducing-medication-errors-hospital-discharge-summaries-randomised-controlled)
17. [Processing of discharge summaries in general practice: a retrospective record review - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6058631/)
18. [MEDICATION DISCREPANCIES AFTER DISCHARGE FROM A RURAL DISTRICT HOSPITAL:](https://www.heti.nsw.gov.au/__data/assets/pdf_file/0008/455399/Julie-Hilditch-Final-Report.pdf)
19. [Accuracy of medication histories derived from an Australian cloud‐based repository of prescribed and dispensed medication records - Elliott - 2023 - Internal Medicine Journal - Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1111/imj.15857)
20. [Discrepancies in Electronic Medical Prescriptions Found in a Hospital Emergency Department: A Prospective Observational Study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11054114/)
21. [Suspected medication reconciliation errors at discharge, characterized...](https://www.researchgate.net/figure/Suspected-medication-reconciliation-errors-at-discharge-characterized-by-type_tbl3_320512747)
22. [Prevalence and determinants of pharmacy shopping behaviour - PubMed](https://pubmed.ncbi.nlm.nih.gov/18211612/)
23. [Patient characteristics associated with multiple pharmacy use in the U.S. population: Findings from the Medical Expenditure Panel Survey - PubMed](https://pubmed.ncbi.nlm.nih.gov/25453538/)
24. [Prevalence and Characteristics of Australians Complementary Medicine Product Use, and Concurrent Use with Prescription and Over-the-Counter Medications—A Cross Sectional Study - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9860983/)
25. [Research School of Population Health ANU College of Medicine, Biology &](https://nceph.anu.edu.au/files/Guide_to_Using_PBS_Data_20131125_0.pdf)
26. [Australian Statistics on Medicines 2015 | PBS](https://www.pbs.gov.au/statistics/asm/asm-2015)
27. [Using personal health records for medication continuity during transition of care: An observational study - Martina Francis, Peter Francis, Meredith Makeham, Melissa T Baysari, Asad E Patanwala, Jonathan Penm, 2025](https://doi.org/10.1177/18333583241270215)
28. [Millions opt-out of My Health Record - iTnews](https://www.itnews.com.au/news/millions-opt-out-of-my-health-record-519572)
29. [Improving accessibility of the Australian My Health Records while preserving privacy and security of the system - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7544771/)
30. [Utilising identifier error variation in linkage of large administrative data sources](https://link.springer.com/article/10.1186/s12874-017-0306-8)
31. [Quality Impact of the Master Patient Index Save to myBoK](https://journal.ahima.org/Portals/0/archives/AHIMA%20files/Quality%20Impact%20of%20the%20Master%20Patient%20Index.pdf)
32. [Epidemiology of Patient Record Duplication - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC11710899/)
33. [60-day prescriptions](https://www.pbs.gov.au/browse/60-day-dispensing)
34. [Stage 3 of 60-day medicines begins](https://www.ama.com.au/ama-rounds/6-september-2024/articles/stage-3-60-day-medicines-begins)
35. [60-day prescriptions Information kit for prescribers](https://www.health.gov.au/sites/default/files/2024-11/information-kit-for-prescribers-60-day-prescriptions.pdf)
36. [60-day prescribing](https://nwmphn.org.au/news/60-day-prescribing-what-you-need-to-know/)
37. [Older Australians collect an average of 31 PBS scripts a year](https://www.uwa.edu.au/news/article/2025/september/older-australians-collect-an-average-of-31-pbs-scripts-a-year-new-research)
38. [Dispensing Patterns of Prescription Medicines Among Older Australians From 2013-2023 - PubMed](https://pubmed.ncbi.nlm.nih.gov/40912678/)
39. [Switching, Persistence and Adherence to Statin Therapy: a Retrospective Cohort Study Using the Australian National Pharmacy Data](https://link.springer.com/article/10.1007/s10557-021-07199-7)
40. [High risk medicines](https://www.sahealth.sa.gov.au/wps/wcm/connect/public+content/sa+health+internet/clinical+resources/clinical+programs+and+practice+guidelines/medicines+and+drugs/high+risk+medicines/high+risk+medicines)
41. [High risk medications 'APINCHS'](https://www.health.wa.gov.au/~/media/Files/Corporate/general-documents/safety/PDF/Medication-safety-resources/High-risk-medications-APINCHS.pdf)
42. [High risk medicines and systems](https://www.safetyandquality.gov.au/clinical-topics/medicines-safety-and-quality/high-risk-medicines-and-systems)
43. [High-Risk Medicine](https://ezymed.com.au/high-risk-medicines-apinch/)
44. [GitHub - carltonnorthern/nicknames: A CSV file with US given names (first name) and their associated nicknames or diminutive names. · GitHub](https://github.com/carltonnorthern/nicknames)
45. [nicknames · PyPI](https://pypi.org/project/nicknames/)
