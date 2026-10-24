# MedTrace Data Plan: Open Australian Reference Data for a Synthetic GP Medication-Reconciliation Demo

**Bottom line:** Use the **PBS Schedule API v3 / monthly PBS API CSV bundle** as the backbone. Use the **PBS item code** as the product-level join key, the **AMT concept IDs from the PBS `/amt-items` table** as the terminology bridge, and the **ATC code from PBS `/item-atc-relationships`** as the class key. Add **PBS Date of Supply statistics** for realistic frequencies, the **TGA Medicine Shortage Reports CSV** for a supply-risk overlay, and **CSIRO's public Ontoserver** as a live FHIR terminology silo. Everything else is optional or should be avoided for a 3-day build.

## TL;DR
- **Must-use core (all Australian, free, joinable on PBS item code / AMT / ATC):**
  - PBS API v3 or its monthly CSV ZIP (about 5 MB).
  - PBS Date of Supply CSVs, for prescribing frequencies.
  - TGA Medicine Shortage Reports CSV export.
  - A hand-curated APINCHS→ATC table.
  - tx.ontoserver.csiro.au, as a live FHIR/JSON AMT lookup silo.
  - Optionally, the HL7 AU/Sparked synthetic FHIR server as a fifth "silo".
- **Join spine:** PBS item code → AMT MPP/TPP/MP (PBS `/amt-items`) → ATC (PBS `/item-atc-relationships`, pick the highest `ATC_PRIORITY_PCT`) → ingredient name. This is enough to detect all six ACSQHC-aligned discrepancy types, including brand/generic confusion (same MP, different TPP) and duplicate therapy (same ATC level 4/5). You need no licensed bulk terminology in the repo.
- **Biggest risks:**
  - The Department of Health, Disability and Ageing's PBS API page says: "The public API is rate-limited to one request per twenty seconds - this limit is shared amongst all concurrent users of the PBS public API." Cache to MinIO and never depend on it live.
  - pbs.gov.au's copyright page is restrictive, and the CC BY status of the API output is unconfirmed. Commit a regenerate script plus a tiny attributed subset, not full dumps.
  - Never commit AMT/SNOMED CT-AU releases, DDInter (CC BY-NC-SA) or the WHO ATC/DDD index (no commercial copying or modification).

## Key Findings

### Ranked shortlist for this build

| Rank | Source | Owner | Access for Zetaris | Join keys | Verdict |
|---|---|---|---|---|---|
| 1 | PBS Schedule API v3 + monthly "PBS API CSV files" | Dept of Health, Disability and Ageing | REST/JSON (`Accept: application/json`) or CSV (`Accept: text/csv`); monthly CSV ZIP (~5 MB) into MinIO | PBS item code, AMT (MP/MPP/TPP), ATC, brand, manufacturer | **Must-use** |
| 2 | PBS & RPBS Date of Supply data + item-to-drug map | Dept of Health (pbs.gov.au statistics) | CSV (monthly report; supplementary FY report CSV 16.5 MB; item map CSV 836 KB) into MinIO | PBS item code, ATC5, drug name | **Must-use** (realistic frequencies) |
| 3 | CSIRO public Ontoserver (tx.ontoserver.csiro.au/fhir) | CSIRO AEHRC | Live FHIR R4 REST/JSON, anonymous | SNOMED CT-AU / AMT concept IDs | **Must-use** as live silo (lookup only, no bulk copy) |
| 4 | TGA Medicine Shortage Reports database | TGA | CSV export (active + archived) into MinIO; HTML search UI | Active ingredient, trade name, ARTG name/ID text | **Must-use** (demo "wow" overlay) |
| 5 | APINCHS high-risk medicine classes | ACSQHC (plus state lists) | HTML/PDF only; hand-curate ~40-row CSV keyed by ATC prefix | ATC prefix, ingredient | **Must-use** (tiny, hand-built) |
| 6 | HL7 AU FHIR Test Data + Sparked AU Core FHIR server | HL7 Australia / Sparked | GitHub JSON bundles; live read-only FHIR server | AMT/PBS codes in Medication resources | **Nice-to-have** (credible live "discharge summary" silo) |
| 7 | DDInter 2.0 | Xiangya School of Pharmaceutical Sciences (CSU) | CSV downloads | Drug name (map via ingredient/ATC) | **Nice-to-have**, fetch-at-build only (NC-SA) |
| 8 | CSIRO Australianised Synthea (117,258 QLD patients) | CSIRO | Bulk CSV/FHIR download; Synthea generator | US codes (RxNorm) for meds; remap needed | **Nice-to-have** for demographics/conditions only |

### What to avoid
- **AMT/SNOMED CT-AU bulk releases (RF2/CSV) in the repo.** These are free, but only to registered NCTS licensees under the SNOMED CT Affiliate Licence and the Australian National Terminology Licence Agreement.\[1\]
- **WHO ATC/DDD index files.** These cost €200, and the terms say "Copying and distribution for commercial purposes is not allowed. Changing or manipulating the material is not allowed".\[2\]\[3\] Use the PBS ATC table instead.
- **NLM RxNav interaction API.** NLM's RxNav FAQ states: "RxNav's drug/drug interaction features were discontinued on January 2, 2024."
- **The WHO ATC scraping repos.** They are CC BY-NC-SA and of uncertain legality.\[4\]
- **MIMIC, real My Health Record, and real eRx/pharmacy data.** These are all prohibited.
- **UK dm+d.** It requires TRUD registration and is UK-coded.
- **SIDER.** It is non-commercial and stale.
- **openFDA/DailyMed.** They are US-coded and low value for a 3-day AU build.

## Details

### 1. Australian medicines reference data

**PBS Schedule API v3 and PBS API CSV files (Must-use, rank 1)**
- **URL:** base `https://data-api.health.gov.au/pbs/api/v3/`. Docs are at data-api-portal.health.gov.au, which no longer needs myGovID to view.\[5\]\[6\] Developer info is at data.pbs.gov.au.
- **Contents useful for med rec:**
  - Tables include `/schedules`, `/items`, `/item-overview`, `/amt-items`, `/atc-codes`, `/item-atc-relationships`, `/restrictions`, `/criteria`, `/indications`, `/prescribers`, `/containers`, `/dispensing-rules`, `/organisations`, `/fees`, `/copayments` and `/summary-of-changes`.\[7\]\[8\]
  - Items give drug name, form, strength, brand, manner of administration, pack size, maximum quantity and number of repeats, which covers pack sizes and repeats.\[7\]
  - Restrictions and authority requirements are available as HTML text and as "restriction fragments". A `WRITTEN_AUTHORITY_REQUIRED` column was added to `/restrictions`.\[6\]\[9\]
  - Prescriber types are available, for prescriber-bag and nurse-practitioner logic.
  - Brand data is per-brand row, which supports a-flag/brand-substitution logic.\[10\] Confirm the exact substitution-group field names in the Data Dictionary v3.6.x before coding.
- **AMT mapping:**
  - `/amt-items` (table ITEM_AMT_T) maps each item (`li_item_id`, built from Item Code + PIG ID, MP, MPP, TPP) to `amt_code` and `preferred_term`.\[11\]
  - Unmapped listings carry `non_amt_code` and `PBS_PREFERRED_TERM` (added June 2025, v3.3.11).\[6\]
  - AMT goes down to TPP level only. There is no CTPP, and TPUU is present only for EFC (chemotherapy) listings.\[6\]\[9\]
  - The department notes that `drug_name` on `/items` is *not* a 1:1 match for the AMT MP preferred term (data fix March 2025).\[6\]\[12\] Join on codes, not names.
- **ATC mapping:**
  - Item↔ATC is many:many via ITEM_ATC_RLTD_T.\[9\]
  - The department advises picking the ATC with the largest `ATC_PRIORITY_PCT` for a primary class. The percentages sum to 100 per item.\[9\]
- **Auth, rate limits and coverage:**
  - The public API needs no identity checks, but requests carry a `subscription-key` header.\[7\] A shared public key is published via the department's portal/Postman collection; third-party code hard-codes one, but get it from the portal.\[5\]\[9\]\[13\]
  - **Rate limit:** the official FAQ states "The Public API is rate-limited to one request per twenty seconds. This limit is shared amongst all concurrent users".\[7\] The February 2024 v3 announcement said 5 requests per minute instead.\[9\]\[14\] Treat the stricter figure as current.
  - The embargo API (future schedules, 1 req/s) needs a Health Products Portal application with myID + RAM and an ABN.\[9\] That is not feasible in 3 days and not needed.
  - The public API holds only the current schedule plus the previous 12 months.\[6\]
- **Format change (flag):**
  - The legacy XML and Text files were discontinued from 1 May 2026.\[7\]\[15\]
  - The "PBS API CSV files" ZIP (~5 MB, published monthly; the October 2026 bundle is on the Publications page) is now the bulk alternative.\[15\]\[16\]
  - The latest API release noted by our checks is v3.7.8 (20 May 2026).\[6\]
- **Freshness:** updated on the 1st of every month.\[17\]
- **Size:** about 5 MB zipped for all tables.\[18\]
- **Licence (uncertain, flag):**
  - A copyright block was added to every endpoint's `_meta` response in v3.1.12 (February 2025).\[6\] Read it on your first call; it is the authoritative statement.
  - The pbs.gov.au website copyright page is restrictive: material "may be reproduced in part for personal use as general reference material only… all rights reserved".\[19\]
  - The data.gov.au PBS statistics datasets are CC BY 3.0 AU, but those are different products.\[7\]\[20\]
  - Until `_meta` says CC BY, commit only a fetch script plus a small (≤200-row) attributed sample.
- **Integration effort:** low. Download the CSV ZIP once, convert it to Parquet, and push it to MinIO. Optionally define one `CREATE LIGHTNING REST TABLE` on `/schedules` to show a live government call. One request is fine; a loop is not.

**PBS Date of Supply statistics (Must-use, rank 2)**
- **What it is:** monthly counts of prescriptions, cost, and government and patient contributions by PBS item code, ATC5, drug name, patient category, script type and month of supply.\[21\]
- **Files:**
  - The Quarterly Supplementary Report for July 2025–June 2026 (CSV 16.5 MB, updated October 2026) excludes s100.\[21\]
  - The "PBS item drug map" CSV (836 KB, updated September 2026).\[21\]
  - Historical FY files run back to 2020–21.\[21\]
- **Why it matters:** these are real population-level dispensing frequencies. Use them as sampling weights so that atorvastatin, metformin and perindopril dominate the synthetic lists, as they do in real Australian general practice.
- **Join keys:** PBS item code and ATC5.
- **Licence:** published by the department on pbs.gov.au. Treat it like the schedule: attribute it and commit only derived weights (e.g. top-300 items by volume), not the raw file.
- **Alternatives:**
  - data.gov.au "PBS Item Report" CSVs are explicitly CC BY 3.0 AU but stale (to July 2016).\[20\]
  - The AIHW "PBS prescriptions: monthly data" dashboard (by LGA, updated quarterly; date of supply since 2015) is good for narrative slides, not joins.\[22\]
  - The Services Australia Medicare Statistics PBS item reports are HTML query forms only (poor).\[23\]

**AMT / SNOMED CT-AU via NCTS (licensed; live lookup only)**
- **Licence:**
  - AMT is a subset of SNOMED CT-AU, released monthly.\[1\]\[24\]
  - Downloads (RF2, plus an AMT CSV that "may be withdrawn with only 90 days notice") require NCTS registration and acceptance of the SNOMED CT Affiliate Licence and the Australian National Terminology Licence Agreement.\[1\]\[25\]
  - It is free to Australian licence holders but **not redistributable in a public repo**.\[26\]
  - The ARTG-ID reference set (AMT→ARTG) also requires licensing.\[27\]
- **National Terminology Server:**
  - The endpoint is `https://api.healthterminologies.gov.au/integration/R4/fhir`. \[28\]
  - It uses OAuth2 client_credentials, with the Client ID/Secret generated in the NCTS Portal after registration.\[29\]
  - No published turnaround exists. Register today if you want it, but do not depend on it.
- **CSIRO public Ontoserver (Must-use, rank 3):**
  - `https://tx.ontoserver.csiro.au/fhir` is anonymously queryable.\[30\]
  - A credential-free fetch on 24 October 2026 returned the SNOMED CT-AU CodeSystem (version `http://snomed.info/sct/32506021000036107/version/20260531`, publisher Australian Digital Health Agency). It supports ECL filters, `$lookup` and `$expand`.\[31\]
  - HL7 AU's comparison page lists it as "the read-only ontoserver" and shows SCT-AU `$lookup` and ECL `$expand` passing.\[30\]
  - No published SLA, rate limit or terms of use were found. The 2018 paper (Metke-Jimenez et al., "Ontoserver: a syndicated terminology server", J Biomed Semantics 2018;9:24) states "A public Ontoserver instance is available worldwide for free for research purposes", but it names the older stu3-latest instance, not tx.ontoserver.csiro.au.
  - Use it for live display-name/hierarchy lookups in the demo. Cache responses for a fallback, and do not bulk-harvest it.
- **Other FHIR terminology servers:** HL7 AU/Sparked runs `https://tx.dev.hl7.org.au/fhir` with AU Base/Core value sets.\[32\]\[33\]

**TGA (rank 4 for shortages; ARTG optional)**
- **Medicine Shortage Reports database** (`apps.tga.gov.au/prod/MSI/search/`):
  - It has "Export active shortage reports" and "Export archived shortage reports" CSV buttons. The TGA introduced this CSV export as part of its 2024 improvements.\[34\]\[35\]
  - There is no documented API.
  - Records are at ARTG-product level and include active ingredient, strength, form, status (current, anticipated, resolved, discontinued), dates and a critical-impact rating.\[34\]\[36\]
  - Join by active ingredient and/or trade name to PBS drug/brand.
  - Australian Prescriber notes almost 400 product shortages listed, and that a 2022 survey found 29% of shortages pharmacists experienced were not in the database.\[37\]\[38\] Present the overlay as "known shortages", not ground truth.
  - Discontinuation records are ideal for the "ceased-but-still-dispensed" and brand-switch stories.
  - Licence: TGA website content. Commit a small extract with attribution, or fetch at build time.
- **ARTG:**
  - The ARTG search visualisation tool can export CSV/Excel.\[39\]
  - An undocumented WCF JSON service (`https://www.tga.gov.au/ARTGSearch/ARTGWebService.svc/JSON/ARTGValueSearch/?pagestart=1&pageend=1000`) is used by third-party tools and by CSIRO AEHRC's `tga-feed-client`, which targets a `data.tga.gov.au` base.\[40\]\[41\]
  - It is unofficial, so treat it as fragile.
  - Nice-to-have only. ARTG IDs add little to a GP med-rec demo when PBS + AMT already identify the product.
- **Safety alerts and recalls:** these are HTML listings (poor). Hand-pick one or two for the narrative only.

**MBS Online XML:** low relevance. Medication reconciliation does not need MBS items; a GP medication-review item number could only be a cosmetic touch. Skip.

**High-risk medicines, med-rec guidance and LASA (rank 5)**
- **APINCHS:**
  - ACSQHC hosts the APINCHS classification (Antimicrobials, Potassium & electrolytes, Insulin, Narcotics/opioids & sedatives, Chemotherapeutic agents, Heparin & anticoagulants, Systems) on an HTML page.\[42\]\[43\]
  - It is **not machine-readable**, and categorisation "may vary between states, territories and healthcare settings". SA Health uses an extended APINCHEN.\[42\]\[44\]
  - Build a ~40-row CSV mapping ATC prefixes to APINCHS letters, then commit it as your own work, with attribution of the concept to ACSQHC. Example rows:
    - J01 → A
    - A10A → I
    - N02A, N05BA, N05CD → N
    - L01 and L04AX03 (oral methotrexate) → C
    - B01A → H
  - Add GP-relevant extras that state lists name: oral methotrexate, digoxin, clozapine, and sulfonylureas.\[45\]\[46\]\[47\]
- **Med-rec classification:**
  - ACSQHC's National Medication Management Plan and MATCH UP Medicines are referenced by the WHO High 5s SOP.\[48\] These are PDF/forms, not data.
  - The discrepancy taxonomy (omission, commission, different dose/route/frequency, different medication in the same class) matches AHRQ's MATCH toolkit, which you can cite for definitions.\[49\]
- **LASA / brand guidance:** ACSQHC links a "List of Medicines for Brand Consideration" (which medicines to prescribe by brand).\[42\] It is PDF, so hand-extract a few rows if you want a brand-confusion rule.

### 2. Interactions, duplicate therapy and dose ranges
- **DDInter 2.0:**
  - It has 302,516 DDI records across 2,310 drugs, plus 8,359 drug-disease interactions, 857 drug-food interactions and **6,033 therapeutic duplications**.\[50\] The duplication data maps directly to "duplicate therapy".
  - It is downloadable as CSV.\[51\]
  - **Licence: CC BY-NC-SA 4.0.**\[52\]\[53\] A hackathon with prizes is arguably commercial, so do not commit it. Provide `scripts/fetch_ddinter.py` and load it to MinIO locally.
  - Join by ingredient name after lowercasing/normalising, or by ATC.
  - Verdict: Nice-to-have.
- **ONC high-priority DDI list:**
  - This is Phansalkar S et al., "High-priority drug-drug interactions for use in electronic health records", J Am Med Inform Assoc 2012;19(5):735–743 (doi:10.1136/amiajnl-2011-000612), which powered the retired RxNav "ONCHigh" source. AHRQ PSNet describes it as "a consensus list of 15 high-severity, clinically significant drug–drug interactions."
  - The pairs are few and well known (e.g. warfarin+NSAIDs, methotrexate+trimethoprim). Hand-encode all 15 pairs by ingredient/ATC as your own table.
  - Verdict: Nice-to-have, very cheap.
- **NLM RxNorm/RxClass:**
  - Still live with no licence (except the proprietary endpoint), but US-coded.\[54\]
  - NLM's RxNav FAQ states: "RxNav's drug/drug interaction features were discontinued on January 2, 2024." Its sources were the Phansalkar high-priority list, "supplemented using CredibleMeds' list of drugs that have a known risk of Torsades de Pointes (TdP)", plus DrugBank's DDI dataset.
  - Separately, the vendor RxLabelGuard states "DrugBank's Interaction Checker retires March 25, 2026". DrugBank has not confirmed this.
  - Verdict: Avoid for this build.
- **WHO ATC/DDD:** Avoid, for the licence reasons above. ATC codes come free inside PBS. DDD-based dose-range checks would need the paid index, so use PBS maximum quantity and strength instead as a crude "dose plausibility" bound.
- **Beers/STOPP-START:** these are copyrighted journal publications with no open machine-readable licence (not verified in this research). Cite one or two criteria in prose only.

### 3. Synthetic patient sources
- **CSIRO "Australian synthetic healthcare data with Synthea":**
  - 117,258 synthetic Queensland patients, July 2024, DOI 10.25919/efcw-bm49, on the CSIRO Data Access Portal.\[55\]
  - A separate community "Synthea_AU" on Zenodo (CSV ~6.2 GB, FHIR ~46 GB) builds on CSIRO configs.\[56\]
  - Both inherit Synthea's **RxNorm-coded** medications.\[57\] Use them only for demographics and conditions, then assign AU medicines yourself. They are too large for a 5–10-minute CPU demo, so sample 50–200 patients.
- **Synthea itself (v4.0.0):** supports international configurations with defaults for missing data.\[58\] It is still US-module-centric, so it is not worth a custom AU medication module in 3 days.
- **HL7 AU FHIR Test Data (rank 6):**
  - The `github.com/hl7au/au-fhir-test-data` repository provides "synthetic, realistic data conforming to HL7 AU FHIR IGs".\[59\]
  - The Sparked AU Core FHIR server (`https://fhir.hl7.org.au/aucore/fhir/DEFAULT/`) offers read-only anonymous access.\[59\]
  - AU Core IG examples include MedicationStatement (e.g. "active use of Bisoprolol 2.5mg") and MedicationRequest (paracetamol + codeine).\[60\]
  - A Beda Aidbox server (`aucore.aidbox.beda.software/fhir`) is also loaded with AU Core test data.\[32\]
  - These are good as an AU-coded "hospital discharge" silo or for shape-copying. Reliability is connectathon-grade, so cache a snapshot.
- **No public Australian synthetic GP or dispensing datasets** were found beyond these. Generate your own.

### 4. Recommended join spine
1. **Product key: PBS item code** (e.g. `2430Y`-style codes) on every synthetic dispensing and claim row. It is what real pharmacy and PBS claim data carry.
2. **Terminology key: AMT concept IDs** from PBS `/amt-items`:
   - MP (ingredient level) is the reconciliation key. It makes brand/generic differences collapse.
   - MPP is the generic pack.
   - TPP is the branded pack.
   - GP and discharge silos record the AMT MPP/TPP or MP code as clinical systems do.
   - Patient-reported entries are free text (brand names, misspellings) that the agent must resolve via Ontoserver `$expand` with a text filter.
3. **Class key: primary ATC** (max `ATC_PRIORITY_PCT`) from PBS `/item-atc-relationships`. ATC level 4/5 drives duplicate-therapy and APINCHS rules.
4. **Name key: normalised active ingredient** (from AMT MP preferred term) for joins to TGA shortages, DDInter and the ONC pairs.

Mapping tables come entirely from the PBS CSV bundle (`amt-items`, `item-atc-relationships`, `atc-codes`, `items`). No NCTS download is required. Ontoserver adds live display names and is-a checks. Typical join: `gp_meds.amt_mp = pbs_amt.mp → pbs_items.pbs_code = pharmacy.pbs_code → atc → apinchs/shortages`.

### 5. Synthetic silo generator design
- **Population:** 30–60 patients aged 60–90, with 5–12 medicines each.
- **Medicine sampling:**
  - Weight medicines by Date of Supply volume within ATC classes.
  - Constrain them to clinically coherent bundles by condition (e.g. T2DM: metformin ± gliclazide/empagliflozin; AF: apixaban/warfarin; HF: bisoprolol, perindopril, frusemide/furosemide).
  - Pull the actual PBS item, brand, strength, pack size and repeats from the current schedule.
- **Five silos, chosen to show federation:**
  - **GP clinical software:** Postgres via JDBC. Holds AMT MPP + dose/frequency text.
  - **Community pharmacy dispensing:** CSV/Parquet in MinIO. Keyed by PBS item code + brand + dispense date + quantity.
  - **Hospital discharge summary:** FHIR MedicationStatement JSON served from a tiny local REST mock, or a HAPI FHIR container, via a REST table.
  - **MHR-style PBS claims history:** Parquet in MinIO. Item code + date of supply.
  - **Patient-reported list:** JSON REST mock with free-text names.
- **Planted discrepancies, with a ground-truth manifest table:**
  - **Omission:** dispensed and on discharge, but missing in GP.
  - **Commission:** in GP, never dispensed for more than 6 months.
  - **Dose/frequency/route mismatch:** discharge 2.5 mg vs GP 5 mg bisoprolol.
  - **Duplicate therapy:** two PPIs, or two brands of the same MP from different pharmacies.
  - **Ceased-but-still-dispensed:** discharge "cease warfarin, start apixaban" while the pharmacy still dispenses warfarin.
  - **Brand/generic confusion:** patient reports "Lipitor" and "atorvastatin" as two drugs (same MP, different TPP).
  - **Shortage overlay:** one item currently on the TGA shortage list.
- **Per-source noise profiles** (e.g. patient list 20% error, pharmacy 2%) give H-MEM something to learn source trust from.
- Bias planted errors toward APINCHS classes (anticoagulants, insulin, opioids, methotrexate) so the sign-off gate triggers visibly.
- Seed the RNG and ship `make data` so judges can regenerate everything from source in under 2 minutes.

### 6. Quick-start for the top 3
1. **PBS API**
   - Request: `curl -H "subscription-key: <public key from data-api-portal.health.gov.au>" -H "Accept: application/json" "https://data-api.health.gov.au/pbs/api/v3/schedules"`
   - Then call `.../items?schedule_code=<latest>&pbs_code=<code>` and `.../amt-items?schedule_code=<latest>`.
   - Use `Accept: text/csv` for flat output; some complex endpoints such as summary-of-changes are JSON-only.\[9\]
   - The JSON envelope carries `_meta` (including copyright) plus a data array of rows with snake_case columns per the Data Dictionary.
   - Do one call every 20 s or more, and prefer the monthly CSV ZIP.
2. **Ontoserver**
   - Lookup: `GET https://tx.ontoserver.csiro.au/fhir/CodeSystem/$lookup?system=http://snomed.info/sct&version=http://snomed.info/sct/32506021000036107&code=<AMT id>` returns a FHIR `Parameters` resource (name, display, designations, properties such as parents).
   - Search: `GET https://tx.ontoserver.csiro.au/fhir/ValueSet/$expand?url=http://snomed.info/sct?fhir_vs=ecl/<ECL>&filter=lipitor&count=10` returns a `ValueSet` whose `expansion.contains[]` holds `{system, code, display}`. Point the Zetaris REST table JSON path at `expansion.contains`.
3. **Sparked AU Core FHIR server**
   - Request: `GET https://fhir.hl7.org.au/aucore/fhir/DEFAULT/MedicationStatement?_count=50` returns a FHIR searchset `Bundle` with `entry[].resource` MedicationStatements.
   - Alternatively, load bundles from the hl7au/au-fhir-test-data repo into your own HAPI container for reliability.

## Recommendations
1. **Today:**
   - Download the October 2026 PBS API CSV ZIP and the Date of Supply supplementary CSV + item map.
   - Export TGA shortages (active + archived).
   - Read the PBS `_meta` copyright block once.
2. **Build the spine** in MinIO as Parquet: pbs_items, pbs_amt, pbs_item_atc, pbs_atc, dos_weights, tga_shortages, apinchs_atc.
3. **Live REST tables in the demo:**
   - Ontoserver for the "resolve 'Lipitor' → AMT MP" moment.
   - Optionally one PBS `/schedules` call.
   - Keep cached fallbacks for both.
4. **Demo JOIN across ~4 sources:** GP (Postgres) ⋈ pharmacy (MinIO) ⋈ PBS/AMT/ATC (MinIO) ⋈ TGA shortages, with Ontoserver as a live enrichment.
5. **Repo hygiene:** `/scripts/fetch_*.py`, a small attributed sample, and a `DATA_LICENCES.md`. Keep DDInter and NCTS content out of git.

## Caveats
- **PBS licence ambiguity:** the website states "all rights reserved, personal use"; the statistics on data.gov.au are CC BY 3.0 AU; the API carries its own `_meta` copyright.\[19\]\[20\] Resolve this before committing any PBS rows.
- **PBS rate-limit figures conflict** (one per 20 s vs 5 per minute), and the API was mid-transition (XML/Text retired May 2026).\[9\]\[14\]\[15\] Verify field names against the current Data Dictionary.
- **Ontoserver public endpoint** has no published SLA or terms. Use it as a research/dev aid and cache responses.
- **Sources for some details are secondary or third-party:** the ARTG JSON service, the DrugBank retirement, the PBS default key and the CC BY claims on community sites. Treat them as unverified.
- **Never use real personal data:** no MIMIC, no real My Health Record, no real eRx tokens, no real pharmacy records. Even "de-identified" Australian data breaches the event rules.

## Sources

1. [Australian Medicines Terminology A national, standards-based approach to the](https://www.healthterminologies.gov.au/library/amt-australian-medicines-terminology-fact-sheet.pdf)
2. [Guidelines for ATC classification and DDD assignment 2026](https://atcddd.fhi.no/filearchive/publications/2026_guidelines_for_atc_classification_and_ddd_assignment.pdf)
3. [Orders ATC/DDD](https://orders.atcddd.fhi.no/)
4. [GitHub - fabkury/atcd: Scrape Anatomical-Therapeutic-Chemical (ATC) classes from its official website run by the WHO Collaborating Centre for Drug Statistics Methodology · GitHub](https://github.com/fabkury/atcd)
5. [pbs-explorer/api-summary.md at main · DJCallyman/pbs-explorer · GitHub](https://github.com/DJCallyman/pbs-explorer/blob/main/api-summary.md)
6. [API - Release Notes](https://data.pbs.gov.au/api/api-release-notes.html)
7. [Eval 0003 · External reference-data sourcing — medicines & terminologies - Cairn](https://docs.cairn-ehr.org/ecosystem/0003-reference-data-sourcing-medicines-and-terminologies/)
8. [PBS Public Data API](https://www.postman.com/hpps/workspace/pbs-public-data-api/collection/33098837-829fc4a1-741d-4807-b524-a492afe522bb)
9. [API - FAQ | PBS Data](https://data.pbs.gov.au/document/91333.html)
10. [1 PBS API V3 Data Dictionary PBS Schedule - Data Mart.](https://data.pbs.gov.au/download/api/files/2025-PBS-API-V3-Data-Dictionary-v3.5.7.pdf)
11. [1 OFFICIAL OFFICIAL PBS API V3 Data Dictionary PBS Schedule - Data Mart.](https://data.pbs.gov.au/download/api/files/2025-PBS-API-V3-Data-Dictionary-v3.6.5.pdf)
12. [API - Known issues](https://data.pbs.gov.au/api/api-known-issues.html)
13. [#!/usr/bin/env node](https://glama.ai/mcp/servers/@matthewdcage/pbs-mcp-server)
14. [PBS data API](https://data.pbs.gov.au/document/90834.html)
15. [PBS XML and Text files](https://www.pbs.gov.au/news/2025/12/pbs-xml-and-text-files-discontinued-from-may-2026)
16. [PBS Publications & Downloads](https://www.pbs.gov.au/browse/publications)
17. [New PBS Schedule Data API and API CSV files](https://www.pbs.gov.au/news/2024/12/new-pbs-schedule-data-api-and-api-csv-files)
18. [Pharmaceutical Benefits Scheme (PBS)](https://www.pbs.gov.au/info/browse/download)
19. [Copyright](https://www.pbs.gov.au/general/copyright)
20. [Pharmaceutical Benefits Scheme (PBS) - Item Report - Dataset - Data.gov.au](https://data.gov.au/data/dataset/pharmaceutical-benefits-scheme-pbs-item-report)
21. [PBS and RPBS Date of Supply Data](https://www.pbs.gov.au/statistics/dos-and-dop/dos-and-dop)
22. [Pharmaceutical Benefits Scheme prescriptions: monthly data, Technical notes - Australian Institute of Health and Welfare](https://www.aihw.gov.au/reports/medicines/pbs-monthly-data/contents/technical-notes)
23. [Services Australia - Statistics - Pharmaceutical Benefits Schedule Item Statistics](http://medicarestatistics.humanservices.gov.au/statistics/pbs_item.jsp)
24. [National Clinical Terminology Service (NCTS)](https://implementer.digitalhealth.gov.au/resources/resource-services/national-clinical-terminology-service-ncts)
25. [30 September 2021 Approved for external information 1 of 12 DH-3522:2021](https://www.healthterminologies.gov.au/library/DH_3522_2021_ClinicalTerminology_SNOMEDCT-AU_ReleaseNote_v20210930.pdf)
26. [SNOMED CT-AU Australian Technical Implementation Guide 3 July 2020 v2.5](https://www.healthterminologies.gov.au/library/DH_3243_2020_SNOMED-CT-AU_Australian-Technical-Implementation-Guide_v2.5.pdf?_filename=DH_3243_2020_SNOMED-CT-AU_Australian-Technical-Implementation-Guide_v2.5.pdf)
27. [TGA ARTG- AMT (inc in SNOMED CT-AU)](https://implementer.digitalhealth.gov.au/standards/tga-artg-amt-inc-in-snomed-ct-au)
28. [Guide for Implementers - National Clinical Terminology Service](https://www.healthterminologies.gov.au/library/DH_3405_2021_NCTS-Guide-for-Implementers_v1.2.pdf?_filename=DH_3405_2021_NCTS-Guide-for-Implementers_v1.2.pdf)
29. [Guide for Implementers - National Clinical Terminology Service](https://www.healthterminologies.gov.au/library/DH_3247_2020_NCTS-Guide-for-Implementers_v1.1.pdf?_filename=DH_3247_2020_NCTS-Guide-for-Implementers_v1.1.pdf)
30. [Terminology Server Comparison - HL7 Australia — FHIR Work Group - Confluence](https://confluence.hl7.org/display/HAFWG/Terminology+Server+Comparison)
31. <https://tx.ontoserver.csiro.au/fhir/CodeSystem/32506021000036107-20260531/_history/>
32. [AU Core and AU Patient Summary Track - 2025-03 - HL7 Australia - Confluence](https://confluence.hl7.org/spaces/HA/pages/308978864/AU+Core+and+AU+Patient+Summary+Track+-+2025-03)
33. [Sparked AU Core Track - 2024-12 - HL7 Australia - Confluence](https://confluence.hl7.org/display/HA/Sparked+AU+Core+Track+-+2024-12)
34. [Medicine Shortages Information Initiative](https://apps.tga.gov.au/prod/MSI/search/)
35. [Medicine Shortages Report 2024 Version 1.0, July 2024](https://www.tga.gov.au/sites/default/files/2024-07/medicine-shortages-report-2024.pdf)
36. [Reporting a shortage or discontinuation of a medicine you supply](https://www.tga.gov.au/resources/guidance/reporting-shortage-or-discontinuation-medicine-you-supply)
37. [Managing medicine shortages - Australian Prescriber](https://australianprescriber.tg.org.au/articles/managing-medicine-shortages.html)
38. [pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11540915)
39. [About the ARTG Search Visualisation Tool](https://www.tga.gov.au/products/regulations-all-products/about-australian-register-therapeutic-goods-artg/about-artg-search-visualisation-tool)
40. [extract storage information from AUS API · Issue #92 · zdavatz/cpp2sqlite · GitHub](https://github.com/zdavatz/cpp2sqlite/issues/92)
41. [tga-feed-client/README.md at main · aehrc/tga-feed-client · GitHub](https://github.com/aehrc/tga-feed-client/blob/main/README.md)
42. [High risk medicines and systems](https://www.safetyandquality.gov.au/clinical-topics/medicines-safety-and-quality/high-risk-medicines-and-systems)
43. [Evaluation of nursing administration records of high‐risk medications at a hospital network: a retrospective audit - Rashed - 2025 - Journal of Pharmacy Practice and Research - Wiley Online Library](https://onlinelibrary.wiley.com/doi/full/10.1002/jppr.1960)
44. [High risk medicines](https://www.sahealth.sa.gov.au/wps/wcm/connect/public+content/sa+health+internet/clinical+resources/clinical+programs+and+practice+guidelines/medicines+and+drugs/high+risk+medicines/high+risk+medicines)
45. [Draft report eHealth High Risk Medicine Safety](https://www.health.vic.gov.au/sites/default/files/2025-06/ehealth-high-risk-medicine-safety-lit-review-and-enviro-scan.pdf)
46. [High-risk medicines](https://cec.health.nsw.gov.au/keep-patients-safe/medication-safety/high-risk-medicines)
47. [High-Risk Medicine](https://ezymed.com.au/high-risk-medicines-apinch/)
48. [Standard Operating Protocol for Medication Reconciliation](https://cdn.who.int/media/docs/default-source/patient-safety/high5s/h5s-sop.pdf?sfvrsn=594d8e49_4)
49. [Chapter 5. Education and Training](https://www.ahrq.gov/patient-safety/settings/hospital/match/chapter-5.html)
50. [DDInter - Database Commons](https://ngdc.cncb.ac.cn/databasecommons/database/id/7473)
51. [GitHub - mnarayan1/DDInter · GitHub](https://github.com/mnarayan1/DDInter)
52. [Replace unprovenanced DDI dataset with DDInter 2.0 · Issue #3 · hoangtrung1801/ddi-detect-agent · GitHub](https://github.com/hoangtrung1801/ddi-detect-agent/issues/3)
53. [Bioregistry - Curated Drug-Drug Interactions Database - Drug](https://bioregistry.io/ddinter.drug)
54. [FAQs - RxNav More Information](https://lhncbc.nlm.nih.gov/RxNav/information/FAQs.html)
55. [CSIRO Data Access Portal - Australian synthetic healthcare data with Synthea](https://data.csiro.au/collection/csiro:61499)
56. [Australian Version of Synthea](https://zenodo.org/records/17149993)
57. [Serialisation Strategy Matters: How FHIR Data Format Affects LLM Medication Reconciliation](https://arxiv.org/pdf/2604.21076)
58. [Releases · synthetichealth/synthea · GitHub](https://github.com/synthetichealth/synthea/releases)
59. [Sydney - Sparked AU Core R1 Testing Event - HL7 Australia — AU Core Work Group - Confluence](https://confluence.hl7.org/spaces/HAAUCOREWG/pages/288074684/Sydney+-+Sparked+AU+Core+R1+Testing+Event)
60. [Examples - AU Core Implementation Guide v2.0.1-ci-build](https://build.fhir.org/ig/hl7au/au-fhir-core/examples.html)
