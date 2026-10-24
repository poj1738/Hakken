# Medication reconciliation prototype: answers to briefs 6 to 10 (24 October 2026)

The synthetic patients will not get past a pharmacist yet. The biggest problems are in the pharmacy dispensing layer. Several fill counts are impossible under PBS pack and repeat rules or for a PRN medicine. Some generated discrepancies are missing from ground truth. Two "withheld" reasons have no clinical basis. Each of these can be fixed in code, and each is cited below.

## TL;DR

- **Data realism (brief 6):** the medication lists are mostly believable. The dispensing layer is not. Nitrolingual has 21 fills in 12 months, Panadol Osteo has 29 fills (above what PBS quantities allow at full adherence), and several fills fall on the admission date. "Withheld: contrast" is applied to a beta blocker and a CCB, which is not supported. Escitalopram 20 mg at age 71 is above the Australian PI maximum of 10 mg/day for people over 65.
- **High-risk list and pitch (briefs 7 and 9):** "APINCHS" may only be used for the ACSQHC core list.
  - Keep clozapine, lithium and neuromuscular blockers, citing current WA Country Health, SA Health and NSW CEC documents.
  - Keep digoxin and sulfonylureas with a weaker claim, citing the Australian aged-care OZ-ABCD list.
  - Drop class III antiarrhythmics.
  - Pitch: the Cornish figure is right but Canadian. The PSA 250,000 figure counts medication-related admissions, not discrepancies. The "two sources" rule comes from ACSQHC implementation guidance, not from the wording of Action 4.05.
- **Suppression rules and age data (briefs 8 and 10):**
  - Never flag: perindopril arginine 5 mg versus erbumine 4 mg, brand versus generic, or a combination product versus its components at the same doses.
  - Always flag: two products that share an ingredient, warfarin brand switches, and IR versus MR switches.
  - Age-stratified agent-level PBS data was not found. AIHW reports polypharmacy (5 or more regular PBS medicines) in 40% of people aged 75+ and 20% of people aged 65 to 74, so the generator's 34% on 10 or more medicines needs justifying or lowering.

## Top 5 fixes across all briefs (ranked)

1. **Make dispensing obey PBS quantities and PRN reality.**
   - Nitrolingual Pumpspray is PBS item 8171C: 1 unit of 200 actuations with 5 repeats.\[1\] Twenty-one canisters a year for a PRN spray is not credible.
   - Panadol Osteo-type paracetamol 665 mg MR is PBS item 8814X: pack of 96, maximum 192 tablets, 5 repeats.\[2\]\[3\] At 2 tablets three times a day, full adherence needs about 23 packs of 96, or about 11 dispensings of 192. Twenty-nine fills is oversupply.
2. **Label every generated discrepancy in ground truth, and stop dispensing on the admission date.** The P0001 pharmacy record has single fills of Atacand 8 mg (2026-05-28) and Lipitor 80 mg (2026-10-24). These match P0003's last-dispensed dates exactly, so they are the overlay identity trap leaking in unlabelled.
3. **Remove "withheld: contrast" from metoprolol and amlodipine, and cap escitalopram at 10 mg for patients aged 65 and over (or plant it deliberately as a dose finding).**
4. **Rephrase all three pitch claims** (exact wording in brief 9).
5. **Drop the class III antiarrhythmic row, and report "APINCHS (ACSQHC core) recall" separately from "extended high-risk recall".** Each extended row must name its own current source.

---

## Brief 6: Does this synthetic data look real to a pharmacist?

**Overall framing:** the drug choices are plausible for Australian older adults. The tells are in quantities, dates, unlabelled side effects of the generator, and a few clinically odd annotations. This research cannot replace a practising pharmacist's read. Every item below is marked either **sourced** or **judgement**.

### Ranked "this is wrong because X" list

**1. Dispensing counts break PBS pack and repeat rules (sourced; highest priority)**
- **Nitrolingual Pumpspray, 21 fills in 12 months (P0002).**
  - PBS item 8171C is 1 canister of 200 actuations with 5 repeats. The 60-day item 13549D allows a maximum of 2 units with 5 repeats and requires the condition to be stable.\[1\]\[4\]
  - The dose is 1 to 2 sprays per episode, up to 3 doses in 15 minutes (Nitrolingual product information, UK HPRA and US label; extrapolated from non-Australian labels, same product).\[5\]\[6\]
  - Twenty-one canisters is about 4,200 doses a year. A PRN user who has stopped (GP "ceased", patient "not taking") should show 0 to 2 fills, with the last one well in the past.
  - Fix: cap PRN items at 0 to 2 fills a year. This is a judgement; no published Australian PRN refill rate was found.
- **Panadol Osteo, 29 fills (P0003).**
  - PBS 8814X / 10598T: paracetamol 665 mg MR, pack of 96, maximum 2 packs (192 tablets), 5 repeats, restricted to "persistent pain".\[3\]\[7\]
  - 2 tablets three times a day is 2,190 tablets a year: about 23 packs of 96 or about 11.4 dispensings of 192. Twenty-nine is impossible at Beta(6, 1.5) adherence (mean about 0.8).
  - The PBS brands listed for 8814X are APOHEALTH Osteo Relief, Chemists' Own Osteo Relief, Osteomol 665, Parapane OSTEO and Pharmacy Action Paracetamol Osteo. **Panadol Osteo itself did not appear in the PBS brand list retrieved.**\[3\]\[7\] A "PBS" script type on Panadol Osteo may therefore be wrong. Verify on pbs.gov.au. If it is confirmed absent, show Panadol Osteo as OTC/private or switch to a listed brand.
- **Diabex XR, 14 fills (P0002).** With 30-day supply, more than 12 fills a year needs oversupply or a dose of 2 nocte on a smaller pack. The Diabex XR pack size and PBS quantity were **not found** in this pass. Check that fills ≤ 365 × daily dose ÷ dispensed quantity, multiplied by adherence.
- **60-day dispensing is plausible.**
  - Amlodipine 5 mg is a 60-day item: PBS 13532F, 60 tablets, 5 repeats.\[8\]
  - Rosuvastatin was in stage one of 60-day prescribing (Grattan Institute, "Measuring uptake of 60-day prescribing", March 2025).\[9\]
  - Norvasc 7 fills next to Crestor 12 is realistic, provided the generator decides 60-day status per script rather than per drug.
- **Dispensing on the admission date.** Norvasc and Lipitor were last dispensed on 2026-10-24 in both P0001 and P0003, the same day as admission. One such fill is possible. Two patients in three is a pattern. Fix: block dispensing dates at or after admission unless deliberately planted (judgement).

**2. Unlabelled discrepancies in ground truth (sourced from your own output; critical for scoring)**
- **Double perindopril on the P0001 admission chart.** The chart has perindopril/indapamide (Coversyl Plus) and perindopril/amlodipine (Coveram), so it contains two perindopril sources and two amlodipine sources (with Norvasc 5 mg).
  - Ground truth labels the duplication only on the GP source. The EMR duplication is a real, harmful commission or duplication on the hospital side and must be labelled.
  - The "one RAS blocker per patient" rule is clearly checked against product, not ingredient. Enforce it on the ingredient list.
- **Atacand 8 mg and Lipitor 80 mg in P0001 pharmacy** (one fill each) match P0003's records to the day. This makes an ACE inhibitor plus ARB and two statins in one record. That is a realistic shape for a wrong-patient dispensing record, but it must be labelled as identity/overlay ground truth. Otherwise the tool is penalised for correctly finding it.
- **Generator bug:** "single_char_typo on patient (Tom → Tom)" produced an identical string. Assert that output differs from input.

**3. "Withheld: contrast" on metoprolol (P0002) and amlodipine (P0003) is not realistic (sourced)**
- RANZCR Iodinated Contrast Media Guideline V2.3: "Patients receiving intravenous iodinated contrast media with an eGFR above 30 ml/min/1.73 m2 should continue taking metformin". Intra-arterial procedures use a higher eGFR threshold.\[10\]
- NSW TAG, "Minimising medication-related complications in patients receiving iodinated contrast" (2017), advises withholding **nephrotoxic** medicines where clinically appropriate. It names the decision to withhold diuretic therapy as an example and states that "Metformin is not considered a nephrotoxic medication".\[11\]
- No Australian source found recommends withholding a beta blocker or a dihydropyridine CCB for contrast.
- Fix: use withheld reasons a clinician would actually write, such as "hypotension", "bradycardia" (beta blocker), "AKI" (ACE inhibitor, diuretic, metformin, NSAID), "nil by mouth" or "fasting". Apply contrast-related withholding only to metformin with low eGFR, or to nephrotoxic medicines. The specific withheld reasons are judgement; the contrast rules are sourced.

**4. Escitalopram 20 mg daily at age 71 (P0003) is above the Australian PI maximum (sourced)**
- Australian PIs (Lexapro, Escitalopram Sandoz and APO-Escitalopram, via ACSQHC Medicine Finder and medsinfo): "10 mg… is the recommended maximum maintenance dose in the elderly" (over 65 years).\[12\]\[13\]\[14\]
- A pharmacist would query 20 mg at 71. Either cap it at 10 mg for patients aged 65 and over, or keep it only as a deliberately planted "dose outside PI" finding.
- Citalopram has a parallel TGA limit of 20 mg/day for people over 65, if citalopram is ever added.\[15\]

**5. Clinically questionable combinations (mixed: sourced and judgement)**
- **P0002 (84): celecoxib + perindopril + aspirin + esomeprazole.** There is no diuretic, so this is not a "triple whammy". It is an ACE inhibitor plus NSAID combination in an 84-year-old with IHD (GTN, metoprolol).
  - Judgement: a pharmacist would flag it for review but would believe it.
  - The PPI co-prescription is appropriate and makes the list more believable.
  - A private script for Celebrex is plausible only if the PBS restriction is not met. Celecoxib PBS restriction details were **not verified** in this pass. Make "private" rare, at most about 5% of scripts (judgement).
- **Gliclazide MR 60 mg + metformin XR at 84.** Believable in Australia. The Australian residential aged-care high-risk list OZ-ABCD (PMC12945874) names "sulfonylureas with high risk of hypoglycaemia" as high-risk, so a reviewer would expect it to be highlighted, not removed.\[16\]
- **P0001 aspirin 100 mg without IHD.** Primary-prevention aspirin in a 75-year-old with diabetes is a common legacy prescription (judgement). It is believable, and a candidate for deprescribing rather than for removal.
- **P0001 Pepcidine 20 mg twice daily.** An H2 antagonist instead of a PPI is believable but uncommon in older Australians (judgement). It works well as a stale listing.
- **Missing expected items (judgement):** analgesia is present (pregabalin, Panadol Osteo, OTC paracetamol). There is no laxative alongside opioids, because none of the three patients is on an opioid. Add a co-occurrence rule so that regular opioids bring a laxative.

**6. Reference-table errors that leak into patients (sourced where stated)**
- **Coversyl strengths "5 mg;10 mg;4 mg;8 mg" mix salts in one row.** The TGA AusPAR for Coveram states the equivalences "4mg perindopril erbumine and 5mg perindopril arginine" and "8mg perindopril erbumine and 10mg perindopril arginine".\[17\] Split the row into perindopril arginine (Coversyl) and perindopril erbumine (generics). Otherwise "Coversyl 4 mg" will be generated, and whether that product is currently marketed was **not verified**.
- **Ostelin 1000 IU with script type "PBS".** No standalone colecalciferol 1000 IU PBS item was found. Colecalciferol on the PBS appeared only in combination with alendronate (Fosamax Plus, items 9183H, 13835E, 14003B), and healthdirect lists calcium + colecalciferol separately.\[8\]\[18\]\[19\]\[20\] Treat this as **not found on the PBS**, render Ostelin as OTC, and verify on pbs.gov.au.
- **Tamsulosin (Flomaxtra) has a 0.55 share** but is RPBS-only (brief 4). Either render it as an RPBS script for a DVA subgroup or reduce the share. PBS status of Duodart and Betmiga was **not verified** in this pass.
- **Remaining brand/strength checks** (Sotacor 80 mg, Lanoxin PG, Avanza, Desfax, Duride, Cartia, Methoblastin 10 mg, Solone, Kinson, Megafol, Rocaltrol, Urex, Toujeo/Optisulin, Asmol, Twynsta, Rosuzet, Atacand Plus, Actonel, Aclasta, Zocor): **not verified in this research pass**. Run them against the PBS A-Z brand listing (pbs.gov.au/browse/medicine-listing-with-brand) before submission.
- **Confirmed:** Fosamax Plus 70 mg/140 microgram (5,600 units) is PBS-listed (9183H, Authority Required STREAMLINED, 4 tablets, 5 repeats).\[8\]\[20\]\[21\]

### Q3: Are the planted errors the errors that actually happen?

- **Omission:** realistic and the most common. Cornish et al. 2005 (PMID 15738372) found omission of a regularly used medicine in 46.4% of discrepancies (Canadian; extrapolated).
  - However, "omission, pregabalin, documented_intentional" is not an error. The WHO High 5s Australian implementation (Stark et al., Res Social Adm Pharm 2020, PMID 31176651) measured **unintentional** and **undocumented intentional** discrepancies separately.\[22\] A documented intentional change is neither.
  - Score documented-intentional omissions as "should not flag", or at most as an informational note.
- **Stale GP listing:** realistic shape. In an Australian regional audit (Boyce and Knight, J Pharm Pract Res 2013), 75% of 48 patients aged 65+ had at least one GP-list discrepancy, and "almost half of the discrepancies were related to non-current medications being recorded".\[23\] A ceased medicine still showing as active is the common shape.
  - The 11-month lag is plausible. The precise distribution of stale durations was **not found**.
  - Also generate the reverse case: a new medicine started by a specialist that is missing from the GP list (judgement).
- **Commission (GTN charted on admission):** a pharmacist would probably not act on charted PRN GTN in a patient with IHD on metoprolol. It is defensible to chart (judgement). This is the leading candidate to drop or downgrade (see Q4).
- **Duplication:** realistic, especially with combination products, as the P0001 data accidentally shows. Keep it, and label both sides.
- **dose_unconfirmable:** warfarin, insulin and tapering prednisolone are the right core. Other medicines whose dose changes without a new script (judgement, mechanism sourced where noted):
  - Methotrexate weekly: the day of the week is not in dispensing data. NSW CEC has a dedicated high-risk standard for oral methotrexate.\[24\]
  - Levothyroxine alternate-day regimens.
  - Furosemide flexible or weight-based dosing.
  - Metformin XR "1 to 2 nocte" (already in your regimens).
  - PRN opioids and Panadol Osteo used PRN.
  - Specific Australian frequency data for these was **not found**.

### Q4: What would a pharmacist not care about? (drop candidates)

- Commission of PRN GTN in a patient with known IHD (judgement).
- Documented intentional omissions (Stark et al. scope, above).
- Frequency notation differences with the same meaning, e.g. "mane" versus "in the morning". ACSQHC "Recommendations for safe use of medicines terminology" (November 2024) lists "morning, mane" and "night, nocte" as acceptable.\[25\]\[26\]

### Q5: What is missing that matters most? (ranked, evidence-weighted)

1. **Timing of weekly and long-interval medicines.** P0001 denosumab was last given 2026-04-30, so the next dose is due around 2026-10-30, during the admission. This is a realistic, high-value catch: plant "due during admission" and "methotrexate day" errors (judgement on ranking).
2. **OTC and complementary omissions.** Your interviews already surface glucosamine and paracetamol. The Queensland Primary Clinical Care Manual BPMH checklist explicitly lists over-the-counter, complementary, "inhalers, puffers, sprays, subling tablets" and "inserted medicines eg nose, ear, eyes".\[27\] Plant omissions of eye drops, inhalers and patches.
3. **Allergy and ADR documentation.** In an Australian and New Zealand audit of general medical admissions (PMC4954094), inadequate allergy documentation was 29.4% in patients not reviewed by a pharmacist versus 13.5% in those reviewed.\[28\]
4. **PRN versus regular confusion** (judgement).
5. **Withheld on admission and not restarted at discharge.** This is a discharge-side error, relevant if you model discharge (judgement).
6. **Dose administration aid (Webster-pak) labels as a source.** An Australian study (PMC10474138) found DAA summary labels missing for 4.0% of patients, and prescribers often treat DAAs as a trusted source.\[29\]

### Q6: Interview language

- Published Australian data on how patients name medicines is thin. A 1993 Australian study found that of 64 older patients able to name their medications, only 64% described the same list as the admitting doctor and 43% the same as the GP (PubMed 8369595).\[30\] That is dated, but it supports a substantial share of non-name descriptions.
- "Puffer" is used in Queensland Health clinical material ("Inhalers, puffers").\[27\] Add it for inhalers.
- "Water tablet", "blood thinner", "cholesterol tablet" and "a little white one": no published Australian lexicon was found. They are **judgement**, but consistent with common usage.
- The 25/45/20/10 mix: **no source found** for proportions. Report it as an assumption.

---

## Brief 7: Current citable basis for high-risk extensions

**Overall answer:** no Australian state or national list maps by ATC code. "APINCHS" refers only to the ACSQHC core list. Three of your seven extensions have current state-policy support, two have weaker current Australian support, one should be dropped, and one has no Australian source as a combination.

### Q1: Current Australian lists (as of October 2026)

| Publisher | Document | Version/date | Type |
|---|---|---|---|
| ACSQHC | APINCHS classification of high risk medicines | Date of last update not confirmed (site blocks automated access) | National reference, not a standard in itself |
| NSW Health / CEC | High-Risk Medicines Management Policy PD2024_006 (replaces PD2020_045); CEC High-Risk Medicine Standards v1.0 | Standards October 2025;\[31\]\[32\] CEC page modified 5 June 2026 | State policy (mandatory for NSW Health) |
| SA Health | High Risk Medicines Management Policy ("APINCHEN": "SA Health has updated its APINCH list to include some psychotropic medicines, epidural and intrathecal medicines and neuromuscular blockers") | Version 2.0, approved 8 May 2024 | State policy (mandatory) |
| WA Country Health Service | High Risk Medications Procedure v6.05 | 7 October 2026 | Facility/service policy |
| Queensland Health | Primary Clinical Care Manual, 12th ed, appendices ("APINCH") | Edition date not confirmed | State clinical manual; a dedicated statewide HRM policy was **not found** |
| Safer Care Victoria | **Not found.** Victoria's nearest lists are SafeScript monitored medicines (S8, benzodiazepines, z-drugs, quetiapine, codeine, pregabalin, gabapentin, tramadol) and the VicTAG "Framework for Medicines with Potential for Harm or Unsafe Use" (November 2025)\[33\]\[34\] | n/a | Monitoring/framework, not an HRM list |
| Peer-reviewed | OZ-ABCD high-risk medication list for Australian residential aged care: Cross AJ, Chaudhry M, Goordeen D et al., "Development of a High-Risk Medication List for Australian Residential Aged Care: A Modified Delphi Study", Australas J Ageing 2026;45(1):e70141, doi:10.1111/ajag.70141 (PMC12945874) | 2026 | Research list, aged care |

- The NSW CEC standards cover: anticancer medicines, anticoagulants, HYDROmorphone, insulin, oral methotrexate, neuromuscular blocking agents, opioid analgesics, paracetamol, intravenous potassium and vinca alkaloids.\[24\]
- The CEC defines high-risk characteristics as including "a narrow therapeutic index" and "complex or unusual dosing or monitoring requirements".\[24\]

### Q2: Row-by-row verdict on the seven extensions

- **Digoxin: keep with weaker claim.**
  - Cite OZ-ABCD, which lists "digoxin" among other high-risk medications for Australian residential aged care.\[16\]
  - Not in WACHS v6.05 or the NSW CEC standards.
  - Supporting argument: Paradissis C, Cottrell N, Coombes I, Scott I, Wang W, Barras M, "Patient harm from cardiovascular medications", Ther Adv Drug Saf 2021;12 (doi 10.1177/20420986211027451), a review of 75 studies, found "Cardiovascular medications contribute to significant medication harm (~20–50%)" and that "the majority of studies investigating older adults [73% (n = 8/11)] found CV medications to be the leading cause of harm".
  - Label it "aged-care high-risk list", not APINCHS.
- **Class III antiarrhythmics (amiodarone, sotalol): drop.**
  - Their only Australian list source is the superseded WA Health 2015 poster. WACHS v6.05, NSW CEC and SA APINCHEN do not include them.
  - ISMP's acute-care list is understood to cover IV antiarrhythmics only. It was **not re-verified** in this pass and would be a non-Australian extrapolation in any case.
  - Keeping sotalol unflagged is then consistent.
- **Sulfonylureas (gliclazide, glimepiride): keep with weaker claim.** Cite OZ-ABCD "sulfonylureas with high risk of hypoglycaemia" (aged care).\[16\]
- **Metformin/glibenclamide: keep with weaker claim (same basis as sulfonylureas)**, provided the product is still marketed. Current ARTG/PBS status was **not verified**. If it is not marketed, drop the row.
- **Clozapine: keep.** Cite WACHS v6.05 Appendix A (psychotropic medications: clozapine, lithium, and others). SA Health APINCHEN adds "some psychotropic medicines".\[35\]
- **Lithium: keep.** Cite WACHS v6.05 and OZ-ABCD ("antipsychotics and lithium").\[16\]
- **Neuromuscular blockers: keep** (irrelevant to a community medication list, but harmless). Cite the NSW CEC NMBA standard under PD2024_006, SA Health APINCHEN, and WACHS v6.05.\[24\]\[35\]

### Q3: ATC-based published mapping

- **Not found.** Every list found maps by drug or class name. The prefix table is your construction, and the submission should say so.

### Q4: "High-risk for this purpose only" (prednisolone)

- No Australian list was found that flags a medicine as high-risk for reconciliation only.
- The closest citable concept is the NSW CEC characteristic "complex or unusual dosing or monitoring requirements".\[24\]
- Recommendation: take prednisolone (and warfarin dose and insulin dose) out of the high-risk flag. Model them as a separate attribute, "dose not confirmable from dispensing". The distinction is legitimate but it is yours; say so.

### Q5: What "APINCHS" may and may not claim

- **May:** "APINCHS recall" means recall against the ACSQHC APINCHS classification only (core rows 1 to 33).
- **May not:** describe digoxin, sulfonylureas, clozapine, lithium or NMBAs as "APINCHS". Use "extended high-risk (state policy / aged-care list)" with a per-row citation.
- Reporting core and extended recall separately is appropriate. No published convention was found either way.

---

## Brief 8: Which differences must never be flagged?

**Overall rule:** compare by ingredient, molar-equivalent dose, total daily dose and release type. Brand, salt, notation and combination-versus-components differences are suppressed unless the release type, unit concentration or brand non-interchangeability changes the therapy.

### Section 1: Salt and ester equivalences

- **Coversyl (perindopril arginine) 5 mg versus perindopril erbumine 4 mg: never flag.** Likewise 10 mg arginine = 8 mg erbumine and 2.5 mg = 2 mg. Source: TGA AusPAR for Coveram.\[17\]
- **Coveram 5/5 versus perindopril arginine 5 mg + amlodipine 5 mg: never flag.** Coveram contains perindopril arginine (TGA AusPAR).\[17\]
  - Coveram 5/5 versus perindopril **erbumine** 4 mg + amlodipine 5 mg: never flag (same equivalence).
- **Metoprolol tartrate (Betaloc/Minax) versus metoprolol succinate (Toprol-XL/Metrol-XL): always flag.** It is a release-type change, and the succinate form is PBS-restricted to heart failure (brief 4). A 1:1 dose-equivalence source was **not retrieved** in this pass, so do not assert a conversion factor.
- **Amlodipine besylate/maleate, bisoprolol fumarate, quetiapine fumarate, venlafaxine HCl, desvenlafaxine succinate:** Australian products are labelled by base-equivalent strength (judgement; per-PI verification **not done** in this pass). Treat same labelled mg as never flag.

### Section 2: Splitting and combining doses

- **Never flag:** same ingredient, same release type, same total daily dose, e.g. 2 × 20 mg versus 1 × 40 mg rosuvastatin, atorvastatin or escitalopram.
- **Depends:** MR tablets and capsules (Efexor-XR, Cardizem CD, Cymbalta, OxyContin, Targin, Palexia SR, Diabex XR, Panadol Osteo). Combining whole units to reach the same daily dose is never a flag. A halved MR unit is always a flag unless the PI permits halving. Per-product halving rules (e.g. Diamicron MR scored) were **not verified** in this pass.
- **Always flag:** IR versus MR of the same ingredient at the same mg (Endone versus OxyContin; gliclazide 80 mg IR versus Diamicron MR). Gliclazide IR and MR are not mg-equivalent; the conversion source was **not retrieved**.

### Section 3: Frequency notation

- **Never flag:** "mane" = "in the morning" = "one in the morning"; "nocte" = "at night". Source: ACSQHC Recommendations for safe use of medicines terminology (November 2024).\[25\]\[26\]
- **Never flag (judgement):** "bd" = "twice daily" = "morning and night".
- **Depends:** "daily" versus "mane". Never flag, except for medicines where timing matters, e.g. simvastatin nocte or levothyroxine before breakfast (judgement).
- **Always flag:** "weekly" versus "daily" for methotrexate, alendronate and risedronate.

### Section 4: Combination versus components

- **Never flag:** a combination versus its separate components at identical doses, e.g. Coversyl Plus versus perindopril 5 mg + indapamide 1.25 mg; Caduet versus amlodipine + atorvastatin; Atozet versus ezetimibe + atorvastatin; CoPlavix/DuoCover versus aspirin 100 mg + clopidogrel 75 mg; Twynsta versus telmisartan + amlodipine; Jardiamet 12.5/1000 twice daily versus empagliflozin 25 mg daily + metformin 1000 mg twice daily.
- **Always flag:** a combination plus a separate product with a shared ingredient. Examples: Coveram + Norvasc (P0001), Coversyl Plus + Coveram, Rosuzet + Crestor, CoPlavix + Astrix, Panadeine Forte + Panadol Osteo (paracetamol).
- **Depends:** Fosamax Plus (colecalciferol 5,600 units weekly, PBS 9183H)\[21\] plus daily Ostelin is not a duplication error. It is a supplementation choice: flag only if it is undocumented.
- **Depends:** Duodart versus Flomaxtra + dutasteride. Both MR tamsulosin, but the formulations differ (judgement). Treat as never flag at the same doses.

### Section 5: Brands that are not interchangeable

- **Always flag:** Marevan versus Coumadin (warfarin). Cited by WA Country Health (brief 1).
- **Always flag:** Optisulin (100 units/mL) versus Toujeo (300 units/mL). Different concentrations; a unit-equivalence source was **not retrieved** in this pass.
- **Depends:** Eutroxsig versus Oroxine (levothyroxine); Lanoxin versus Lanoxin PG (different strengths). Compare micrograms. The brand switch itself is a "consider" item.
- **The national mechanism is the List of Medicines for Brand Consideration (LMBC)** under active ingredient prescribing. The Australian Digital Health Agency publishes it as a SNOMED reference set (ID 1495581000168106, version 20241231).\[36\] The LMBC contents were **not retrieved**; load the reference set and suppress brand differences only for items not on it.
- **Never flag:** brands marked as substitutable on the PBS, e.g. paracetamol 665 mg MR brands carrying the "a" marker on PBS 10598T.\[2\]

---

## Brief 9: Are the pitch statistics correct?

**Claim 1: "53.6% of admitted older patients have at least one unintended medication discrepancy" (Cornish et al. 2005, Arch Intern Med, PMID 15738372)**
- **Correct but better phrased.** 81 of 151 patients (53.6%; 95% CI 45.7% to 61.6%), mean age 77, taking ≥4 medicines, single Canadian (Toronto) hospital. Omission was 46.4% of discrepancies, and 38.6% had potential for moderate to severe harm.\[37\]
- Say: "In a landmark Canadian study, more than half of older inpatients had at least one unintended medication discrepancy at admission."
- **Australian figures to add:**
  - ACSQHC: "Between 10% and 67% of medication histories have at least one error, and up to 33% of these errors have the potential to cause patient harm" (ACSQHC Medication charts page).\[38\]
  - WHO High 5s Australian implementation (10 hospitals, patients ≥65 admitted via ED, 42,003 records): unintentional discrepancies fell from 15.2% to 11.1% after reconciliation (Stark et al., PMID 31176651).\[22\] The abstract does not state whether the denominator is patients or medicines, so do not quote it as "% of patients" without the full text.

**Claim 2: "About 250,000 medicine-related hospital admissions a year in Australia" (PSA 2019)**
- **Correct but better phrased.** PSA "Medicine Safety: Take Care" (January 2019): "250,000 hospital admissions annually are a result of medication-related problems", annual cost $1.4 billion (total costs of $1.375 billion), plus 400,000 additional ED presentations, and "50% of this harm is preventable".\[39\]
- The figure counts admissions caused by medication-related problems, not reconciliation discrepancies. Say so, so you do not imply that discrepancies cause all 250,000.
- No newer national estimate was found. PSA still cited the figure in 2022.\[40\]

**Claim 3: "Standard 4, Actions 4.5 and 4.6, require at least two independent sources"**
- **Partly wrong as phrased.**
- Exact wording:
  - **Action 4.05:** "Clinicians take a best possible medication history, which is documented in the healthcare record on presentation or as early as possible in the episode of care".\[41\]
  - **Action 4.06:** "Clinicians review a patient's current medication orders against their best possible medication history and the documented treatment plan, and reconcile any discrepancies on presentation and at transitions of care".\[41\]
- The two-source requirement is in ACSQHC's implementation guidance for the NSQHS Standards (2nd ed.) online guide, Standard 4 "Medication reconciliation": "At least two sources of information are needed to obtain and then confirm the patient's BPMH", for example the patient plus the GP or community pharmacist.\[42\]
- The WHO High 5s SOP says information "should be verified with more than one" source.\[43\]
- Say: "consistent with NSQHS Actions 4.05 and 4.06 and ACSQHC guidance that a BPMH needs at least two sources". Do not drop "independent"; the patient interview counts as one of the two.
- ACSQHC is running a "Third edition engagement hub" for the NSQHS Standards.\[41\] Whether a third edition has been published was **not confirmed**, so check before submission.

**Is "draft BPMH" the right framing?**
- BPMH is the correct Australian term (Action 4.05; SHPA Standards of Practice chapter on medication reconciliation).\[41\]\[44\]
- A BPMH requires a clinician and active patient/carer involvement (ACSQHC Action 4.05 guidance).\[41\] Software cannot produce one.
- Call the output a "pre-populated medication history for clinician verification" or "draft for BPMH". Avoid "BPMH" without a qualifier.

**What a judge will expect to see cited**
- ACSQHC "Medication without harm – WHO Global Patient Safety Challenge. Australia's response" (January 2020): "Over four in ten people aged 50 years and older take five or more medicines" and "Over one in ten people aged 50 years and older take ten or more medicines"; it aims to reduce severe avoidable medication-related harm by 50%, and ACSQHC published a status report on the response in June 2024.
- Medicine safety as Australia's 10th National Health Priority Area (COAG, 2019; PSA).\[45\]\[46\]
- Australian Prescriber 2024;47:106-8 (doi 10.18773/austprescr.2024.034) on discharge-summary inaccuracy, My Health Record and the "pharmacist shared medicines list".\[47\]
- AIHW "Polypharmacy in Australia in 2025".

---

## Brief 10: Age-stratified utilisation

**Overall answer:** no age-restricted, agent-level PBS dispensing data was found in this pass. Say so in the submission. Age-banded polypharmacy data now exists and should anchor the medicine-count distribution.

- **Agent-level by age: not found.** The Australian Prescriber top-10 series (e.g. 2022-23: rosuvastatin 16,742,825 scripts; atorvastatin 12,337,802; pantoprazole 10,389,022) is all ages.\[48\]
- **Class-level by age (share of 65+ on a statin, PPI, antidepressant or anticoagulant): not found.** AIHW reports that the medicines driving polypharmacy "changed substantially by age" and that antidepressants are "a common feature" in most age groups.\[49\]\[50\] Specific shares were not retrieved.
- **Condition prevalence by age band: not found in this pass.** The ABS National Health Survey was not retrieved. Keep the bundle weights labelled as an assumption.
- **Polypharmacy (AIHW, Polypharmacy in Australia in 2025, released 7 October 2026):**
  - 1.9 million people (7.0%) regularly dispensed 5 or more PBS/RPBS medicines in 2025.\[50\]
  - By age: 75+: about 910,000 (40%); 65 to 74: 20%; 55 to 64: 9.5%.\[51\]
  - About 219,000 people (11% of people with polypharmacy, 1% of the population) had 10 or more medicines. One-third of people with polypharmacy were on exactly 5.\[52\]
  - "Regular" means 4 or more dispensings. Private scripts are excluded, so these figures are a lower bound.\[49\]\[51\]
- **Is mean 8.4 with 34% on 10+ defensible?** Not on AIHW community figures.
  - It may be defensible for admitted patients (hospitalised older people carry more medicines), but no Australian admitted-patient distribution was found.
  - Recommendation: calibrate to the AIHW shape (a mode at 5, with a long right tail) and state the admitted-population uplift as an assumption.
- **Sex differences:** AIHW found polypharmacy almost the same by sex (75+: 42% of males, 39% of females).\[49\]\[52\] Your current sex variation (osteoporosis, BPH, hypothyroidism) is reasonable. Venlafaxine/desvenlafaxine over-weighting and mirtazapine under-weighting (brief 4) remain unquantified.

---

## Caveats

- The web-search budget ran out before every product, PI and PBS item could be checked. Items marked "not verified" or "not found" must be checked before submission, not assumed.
- Clinical-plausibility judgements in brief 6 are a researcher's reading, grounded in the cited sources. They are not a substitute for a practising pharmacist's review.
- The OZ-ABCD list is aged-care, not acute-care, so citing it for a hospital admission tool is an extrapolation in setting.

## Sources

1. [GLYCERYL TRINITRATE](https://www.pbs.gov.au/medicine/item/3475X-8171C)
2. [paracetamol 665 mg modified release tablet, 96](https://www.pbs.gov.au/medicine/item/8814X-5343F-10598T)
3. [PARACETAMOL - 8814x](https://www.pbs.gov.au/medicine/item/8814X-8814X-8814X)
4. [GLYCERYL TRINITRATE - 13549d](https://www.pbs.gov.au/medicine/item/13549D)
5. [Nitrolingual Pumpspray 400 micrograms per metered dose, ...](https://assets.hpra.ie/products/Human/31905/2169721.PPA0465_300_001.bff8dfc3-daf7-4071-b1e6-6b1ae3fbcb28.000001NitrolingualPIL.151123.pdf)
6. [3691410 This label may not be the latest approved by FDA ...](https://www.accessdata.fda.gov/drugsatfda_docs/label/2015/018705s019lbl.pdf)
7. [PARACETAMOL - 10598t](https://www.pbs.gov.au/medicine/item/10598t)
8. [60-day prescriptions](https://www.pbs.gov.au/browse/60-day-dispensing)
9. [Measuring uptake of 60-day prescribing March 2025 Peter Breadon and Wendy Hu](https://grattan.edu.au/wp-content/uploads/2025/03/Measuring-uptake-of-60-day-prescribing.pdf)
10. [Iodinated Contrast Media Guideline](https://www.ranzcr.com/wp-content/uploads/edocman/professional-documents/guidelines/Iodinated%20Contrast%20Media%20Guideline%20V2.3.pdf)
11. [Minimising Medication-Related Complications in Patients Receiving](https://www.nswtag.org.au/wp-content/uploads/2017/08/Minimising-medication-related-complications-with-iodinated-contrast_V1.1.pdf)
12. [Escitalopram Sandoz](https://www.safetyandquality.gov.au/medicine-finder/escitalopram-sandoz)
13. [APO-Escitalopram](https://www.safetyandquality.gov.au/medicine-finder/apo-escitalopram-tablets)
14. [LEXAPRO (ESCITALOPRAM OXALATE) FILM-COATED ...](https://rss.medsinfo.com.au/lu/pi.cfm?product=luplexap)
15. [Citalopram and heart problems - changes to recommended doses](https://www.tga.gov.au/safety/safety-monitoring-and-information/safety-alerts/citalopram-and-heart-problems-changes-recommended-doses)
16. [Development of a High‐Risk Medication List for Australian Residential Aged Care: A Modified Delphi Study - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12945874/)
17. [Australian Public Assessment Report for Perindopril arginine/amlodipine](https://www.tga.gov.au/sites/default/files/auspar-coveram.pdf)
18. [Pharmaceutical Benefits Scheme (PBS) |](https://www.pbs.gov.au/medicine/item/13835E-14003B-2194L-2224C-9012H-9183H)
19. [Calcium + colecalciferol](https://www.healthdirect.gov.au/medicines/medicinal-product/aht,23697/calcium-+-colecalciferol)
20. [Repatriation Schedule of Pharmaceutical Benefits (RPBS)](https://www.pbs.gov.au/browse/rpbs)
21. [ALENDRONATE + COLECALCIFEROL - 9183h](https://www.pbs.gov.au/medicine/item/9183h)
22. mcp\_\_PubMed\_\_get\_article\_metadata
23. [Audit of General Practitioner Medication Lists for Older Patients at a Regional Hospital - Boyce - 2013 - Journal of Pharmacy Practice and Research - Wiley Online Library](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.2055-2335.2013.tb00230.x)
24. [High-risk medicines](https://cec.health.nsw.gov.au/therapeutics-safety/high-risk)
25. [Recommendations for safe use of medicines terminology November 2024](https://www.safetyandquality.gov.au/sites/default/files/2024-12/recommendations-for-safe-use-of-medicines-terminology.pdf)
26. [FACT SHEET for health service organisations and clinicians](https://www.safetyandquality.gov.au/sites/default/files/2024-12/fact-sheet-recommendations-for-safe-use-of-medicines-terminology.pdf)
27. [10 Appendices](https://www.health.qld.gov.au/__data/assets/pdf_file/0017/1215035/10.Appendices.pdf)
28. [Simple prescribing errors and allergy documentation in medical hospital admissions in Australia and New Zealand - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4954094/)
29. [Accuracy of medication labels on community pharmacy-prepared dose administration aids: An observational study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10474138/)
30. [A critical review of admission and discharge medications in an elderly Australian population - PubMed](https://pubmed.ncbi.nlm.nih.gov/8369595/)
31. [High-Risk Medicine Standards Printable Standard Version 1.0, October 2025](https://www.cec.health.nsw.gov.au/__data/assets/pdf_file/0004/1024735/All-High-Risk-Medicines-Standards-Printable-version.pdf)
32. [PD2024 006](https://www1.health.nsw.gov.au/pds/ActivePDSDocuments/PD2024_006.pdf)
33. [Victorian Framework for Medicines with Potential for Harm or Unsafe Use 1](https://www.victag.org.au/1._FINAL_VicTAG_Framework_for_Medicines_with_Potential_for_Harm_or_Unsafe_Use_2025_Nov.pdf)
34. [SafeScript for prescribers and pharmacists](https://www.health.vic.gov.au/safescript/safescript-for-prescribers-and-pharmacists)
35. [High risk medicines](https://www.sahealth.sa.gov.au/wps/wcm/connect/public+content/sa+health+internet/clinical+resources/clinical+programs+and+practice+guidelines/medicines+and+drugs/high+risk+medicines/high+risk+medicines)
36. [List of Medicines for Brand Consideration reference set](https://developer.digitalhealth.gov.au/standards/list-of-medicines-for-brand-consideration-reference-set)
37. [Unintended Medication Discrepancies at the Time of Hospital Admission](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/486421)
38. [Medication charts](https://www.safetyandquality.gov.au/clinical-topics/medicines-safety-and-quality/medication-charts)
39. [MEDICINE SAFETY: TAKE CARE JANUARY 2019](https://www.psa.org.au/wp-content/uploads/2019/01/PSA-Medicine-Safety-Report.pdf)
40. [2022 World Patient Safety Day](https://www.psa.org.au/2022-world-patient-safety-day-pharmacists-key-to-reducing-medicine-harm/)
41. [Medication Safety Standard](https://www.safetyandquality.gov.au/national-standards/nsqhs-standards/medication-safety-standard)
42. [Medication reconciliation](https://www.nationalstandards.safetyandquality.gov.au/4.-medication-safety/documenting-patient-information/medication-reconciliation)
43. [Standard Operating Protocol for Medication Reconciliation](https://cdn.who.int/media/docs/default-source/patient-safety/high5s/h5s-sop.pdf?sfvrsn=594d8e49_4)
44. [S6 Journal of Pharmacy Practice and Research Volume 43, No. 2 (suppl), 2013.](https://www.adpha.au/publicassets/4adc0a0d-eb77-ec11-80de-005056be03d0/Chapter%201%20-%20Medication%20Reconciliation.pdf)
45. [Medicine safety to be the 10th National Health Priority Area - Pharmaceutical Society of Australia](https://www.psa.org.au/medicine-safety-to-be-the-10th-national-health-priority-area/)
46. [Medicine safety forum: Informing Australia’s 10th](https://www.psa.org.au/wp-content/uploads/2021/06/Medicine-safety-forum.pdf)
47. [Achieving safe medication management during transitions of care from hospital: time for a stewardship approach - Australian Prescriber](https://australianprescriber.tg.org.au/articles/achieving-safe-medication-management-during-transitions-of-care-from-hospital-time-for-a-stewardship-approach.html)
48. [Top 10 drugs 2022–23 - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC10751076/)
49. [newsGP - Polypharmacy among almost two million Australians](https://www1.racgp.org.au/newsgp/clinical/polypharmacy-among-almost-two-million-australians)
50. [Polypharmacy in Australia in 2025](https://www.aihw.gov.au/getmedia/4dfca4f1-e8e6-4500-aef1-dcb5e856e834/polypharmacy-in-australia-in-2025.pdf?v=20261007002614&inline=true)
51. [Polypharmacy hits 40% of over-75s - Oncology Republic](https://www.oncologyrepublic.com.au/polypharmacy-hits-40-of-over-75s/6313)
52. [Polypharmacy hits 40% of over-75s - Dermatology Republic](https://www.dermatologyrepublic.com.au/polypharmacy-hits-40-of-over-75s/2876)
