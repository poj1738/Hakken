# MedTrace Research Brief: Fragmented Medication Data, Patient Harm, and Agent-Implementable Detection

Most medication harm at hospital admission comes from fragmentation, not from bad drugs. In Cornish et al. (Arch Intern Med 2005), 53.6% of admitted older patients had at least one *unintended* discrepancy, and 38.6% of those discrepancies could cause moderate-to-severe harm.\[1\] In Australia, PSA's *Medicine Safety: Take Care* (2019) estimates 250,000 hospital admissions and 400,000 extra ED presentations a year are medicine-related, costing $1.375 billion (nearly 15% of total PBS expenditure), with at least half preventable.

Because MedTrace federates four sources that each fail in different ways, it is well placed to tackle the five failure modes that do the most damage and show best in a demo:
- **Identity linkage with a human-confirmed near-miss queue**
- **Semantic normalisation** of brand, generic and combination products
- **Stale-record detection** using dispensing-supply temporal reasoning
- **Missing source treated as "unknown"**, never as "not taking"
- **Trust-weighted conflict resolution** that learns from pharmacist feedback

## TL;DR

- **The problem is large and well quantified.** Studies find 10–67% of admitted patients have at least one medication-history error (Tam et al., CMAJ 2005 systematic review), and WHO's *Medication Without Harm* reports unintended discrepancies in 86% of people on admission. Omission is the most common error. Australian studies find discrepancies in 75–94% of GP referral or GP medication lists compared with a pharmacist's Best Possible Medication History (BPMH). Even a single electronic prescription-exchange source produced at least one error in 94.8% of patients (Elliott et al., Intern Med J 2023).
- **Each source fails differently, and each failure has a concrete algorithmic fix:**
  - Identity: Fellegi–Sunter probabilistic linkage with Jaro-Winkler and a two-threshold review queue.
  - Semantics: normalise to Australian Medicines Terminology (AMT) ingredient and strength level, with combination-product decomposition.
  - Staleness: days-supply and run-out arithmetic plus recency decay.
  - Missing sources: a tri-state evidence model (present / absent / source-unavailable).
  - Conflicts: per-attribute, trust- and recency-weighted fusion with provenance.
- **For the 3.5-day build, implement five types:** identity/linkage (including lookalike and overlay traps), semantic normalisation, stale records, missing-source-as-unknown, and conflict resolution with trust learning, triaged by intentional vs unintentional status and high-risk (APINCH) class. Evaluate every one against planted ground truth using precision, recall and F1 per discrepancy type, false-merge rate for identity, and alerts-per-patient for alert burden.

## Key Findings: Overall Burden

**Hospital admissions caused by medicines (Australia)**
- PSA's *Medicine Safety: Take Care* (2019, prepared by the University of South Australia's Quality Use of Medicines and Pharmacy Research Centre) estimates:
  - 250,000 hospital admissions a year
  - an additional 400,000 ED presentations
  - $1.375 billion a year, nearly 15% of total PBS expenditure
  - at least half preventable
- An earlier Australian review (Roughead and Semple, 2009) put medication-related admissions at 2–3% of all hospital admissions.\[2\]

**Medication history errors at admission (international)**
- Tam et al. (CMAJ 2005), 22 studies and 3,755 patients:
  - 10–67% of patients had at least one prescription-medication history error.
  - 11–59% of errors were clinically important.
  - Up to 27% of hospital prescribing errors are attributable to incomplete histories at admission.\[3\]
- Cornish et al. (2005):
  - 53.6% had at least one unintended discrepancy.
  - Omission of a regularly used medicine was the most common error (46.4%).
  - 38.6% of discrepancies could cause moderate-to-severe discomfort or clinical deterioration.\[1\]
- WHO *Medication Without Harm*:
  - On admission, unintended discrepancies affect 16–25% of medications and 86% of people.
  - Discharge prescribing error or miscommunication affects 65–83% of patients.
  - 69% of discrepancies remain unresolved 10–14 days after discharge.\[4\]

**Australian source-level evidence (the four MedTrace sources)**

*GP lists*
- Taylor et al. (Aust Fam Physician 2014; 414 GP letters across 8 EDs, 2008–09) found 87% (361/414) of GP referrals had at least one discrepancy in regular medicines, and 62% had a discrepancy of moderate-to-high significance.
- A regional ED study (Healthcare 2019): 94% of 143 GP referrals had at least one discrepancy, at 67.18 discrepancies per 100 medications.\[5\]
- Boyce (2013): 75% of GP lists for older patients had at least one discrepancy. Almost half of the discrepancies were *non-current* medicines still listed.\[6\]

*Dispensing and prescription-exchange records*
- A prescription-exchange-derived history (Elliott et al., Intern Med J 2023; MedView prescription exchange service, two Australian tertiary hospitals) had at least one error in 94.8% of patients when PRN medicines were excluded (99.4% including PRN).
- Dose-regimen errors affected 25.1% of the medicines it did capture.

*My Health Record*
- A NSW study (Francis et al., 2025; 82 patients, 1,207 medications) found mismatches with the pharmacist BPMH were more likely for:
  - regular non-prescription medicines
  - PRN medicines
  - parenterally administered medicines
- It concluded My Health Record is a usable *secondary* source or starting point, not a substitute for a BPMH.\[7\]

**Pharmacists make the difference**
- Physicians in simulated-patient work obtained on average 79% of the prescription history and 45% of the OTC history, versus 100% for pharmacists (Dawson and Gray, cited in Cornish).\[8\]
- In a Sydney hospital, discharge letters had medication errors in 92.2% of patients without a pharmacist admission history, versus 70.6% with one (Francis et al., JACCP 2021).\[9\]

**High-risk classes most involved**
- ACSQHC's APINCH list:
  - Antimicrobials
  - Potassium and other electrolytes
  - Insulin
  - Narcotics/opioids and sedatives
  - Chemotherapy
  - Heparin and other anticoagulants\[10\]
- ISMP's reported-event data places opioids, antithrombotics and insulins at the top. Insulin events cause harm most often: 31% of insulin events vs 11% of opioid events.\[11\]
- Cardiovascular medicines, though not in APINCH, are a large contributor to harm-related admissions.\[12\]
- MedTrace should therefore weight discrepancies in anticoagulants, insulin, opioids, antiepileptics, immunosuppressants and cardiovascular agents above others.

**Regulatory anchor**
- ACSQHC NSQHS Standard 4 (Medication Safety):
  - Action 4.5 requires a BPMH "on presentation or as early as possible" and states "at least two sources of information are needed to obtain and then confirm the patient's BPMH."
  - Action 4.6 requires reconciling current orders against the BPMH at presentation and at transitions of care.\[13\]
- The WHO High 5s Medication Reconciliation SOP defines the same BPMH-then-compare process.\[14\]
- MedTrace's core value claim: it automates the "two or more sources" collection and comparison step and leaves clinical judgement to the pharmacist.

---

## 1. Patient Identity and Linkage Failures

**(1) What it is and why it happens**

The four sources each key patients differently:
- Hospital EMR uses a local MRN (medical record number).
- GP software has its own patient ID.
- Pharmacy dispensing systems hold their own customer record.
- Patient-reported data may carry only a name and DOB.

Australia has the Individual Healthcare Identifier (IHI), a 16-digit number from the Healthcare Identifiers Service,\[15\] but it is not reliably present on every record:
- IHIs have record statuses: verified, unverified and provisional.\[16\]
- Provisional IHIs are created for unconscious or unknown patients and expire after 90 days of inactivity.\[17\]\[18\]
- The HI Service runs explicit processes to resolve *duplicate* IHIs (two IHIs for one person) and *replica* IHIs (one IHI shared by two people).
- Local systems are expected to re-validate the IHI whenever surname, DOB or sex changes.\[19\]

Demographic drift breaks deterministic matching:
- nicknames (Bill/William)
- maiden or married surname changes
- transposed DOB day and month
- typos and hyphenation
- address moves

**(2) Prevalence**

*Duplicates within one organisation*
- ONC's *Patient Identification and Matching Final Report* (2014) cites a mean master-patient-index duplicate rate of 8%; a quarter of indexes exceeded 10%.\[20\]
- Black Book (2018, an industry survey, not peer-reviewed) reported an average of 18% of records within organisations were duplicates.\[21\]

*Matching across organisations*
- ONC's interviews found match rates within one Epic instance above 90%, falling to around 50–60% when sharing across regions or with outside partners, even with the same vendor.\[20\]\[22\]
- This figure is qualitative and comes from interviews, not a measured multi-site study.

*Lookalike patients*
- Harris County's health system (Houston) held 2,488 records named Maria Garcia, 231 of them with the same birth date (Pew, 2016).\[23\]

*Harm signals*
- 20% of surveyed hospital CIOs reported at least one patient harmed in the past year by mismatched records (Pew).\[23\]
- One 2016 report found 4% of confirmed duplicates led to negative clinical care.\[21\]

*Australia*
- No published quantitative IHI match-rate or duplicate/replica statistics could be found.
- That is itself a finding: the Australian scale of the problem is not publicly measured.

**(3) Harm examples**

*Overlays (two people merged into one record)*
- Overlays corrupt the medication list, allergies and history.\[24\]\[25\]
- In July 2026, Werribee Mercy Hospital (Melbourne) apologised after mixing up two women's medical data. Michelle Buckley's record carried another woman's appointments and tests going back months. Police then wrongly told her family she had died. She was still untangling the records with Services Australia two months later (ABC News, 22 July 2026).\[26\]

*Wrong-patient supply*
- An SA coronial inquest (2026) heard that 82-year-old Pelayo Cortes Godoy died after taking another person's medicines, dispensed in a dose administration aid labelled for him.\[27\]
- A Professional Indemnity (PDL) review of 150 pharmacy incidents found "wrong medicine to wrong patient" a recurrent pattern, including dose administration aids handed to a patient with the same surname.\[28\]

*Wrong record open*
- At Macquarie University Hospital (2016), Paul Lau died after fentanyl intended for another patient was ordered in his still-open electronic record.\[29\]
- This was wrong-record *selection*, not linkage, and the account comes from secondary sources. It still shows that once data attaches to the wrong identity, downstream safety checks are defeated.

**(4) How clinicians work around it today**
- Two-identifier checks (name plus DOB) at the point of care.
- Phoning the GP or pharmacy and reading back DOB and address.
- IHI lookup through the HI Service, by software or by phone.
- Pharmacists notice clinical implausibility, for example a dispensing history inconsistent with the patient's age or sex, or two pharmacies in distant cities on the same day.

**(5) MedTrace solutions**

*Blocking*
- Generate candidate pairs on cheap keys to avoid comparing all pairs: DOB year, Soundex or Double Metaphone of surname, postcode, and Medicare number when present.
- Measure blocking quality with pair completeness (blocking recall) and reduction ratio.

*Deterministic tier first*
- An exact IHI match, or Medicare number plus IRN plus DOB, gives an immediate link with confidence 1.0.
- A *conflicting* IHI is a hard non-link.

*Probabilistic tier (Fellegi–Sunter)*
- For each field, estimate m (agreement probability given a true match) and u (agreement probability given a non-match).
- Sum log₂(m/u) weights for agreement and log₂((1−m)/(1−u)) for disagreement.\[30\]
- Estimate m and u by EM on unlabelled pairs, or set them from synthetic ground truth.
- Evidence: Grannis et al. (AMIA 2003) showed unsupervised EM-based Fellegi–Sunter reached 98.99–99.19% sensitivity and 99.42–99.43% specificity on two hospital registries without human review.\[31\] Their earlier deterministic algorithm achieved about 90–92% sensitivity at 100% specificity.\[32\]

*Field comparators*
- **Names:** Jaro-Winkler.
  - Grannis et al. (2004) found Jaro-Winkler at a 0.8 threshold gave the highest sensitivity (97.4% and 97.7%) but lower specificity than other comparators.\[33\]\[34\]
  - Combine it with a nickname dictionary (William↔Bill/Will/Liam, Margaret↔Peggy/Maggie), a previous-surname field for maiden names, and token-sort for hyphenated or reordered names.
- **DOB:** a custom comparator that awards partial agreement for:
  - day/month swap (03/07 vs 07/03)
  - single-digit typo (edit distance 1)
  - year off by one or ten
- **Address:** normalised street plus postcode. Treat a disagreement as weak evidence (low u-penalty), because people move.

*Two thresholds with a human review queue*
- Score above the upper threshold: auto-link.
- Score below the lower threshold: non-link.
- Between the thresholds: a near-miss candidate shown to the pharmacist side by side, with agreeing and disagreeing fields highlighted ("confirm same person?").\[35\]
- This is the "find near-miss candidates, then ask a human" pattern, and every confirmation becomes a labelled pair for re-estimating m and u.

*Lookalike guard*
- If two *different* records in the same source share name and DOB, raise the link threshold for that cluster and require a distinguishing attribute (Medicare number, address or phone) before auto-linking.

*Overlay detector (within-record inconsistency)*
- Flag a single source record that contains internally incompatible facts:
  - two DOBs or sexes across encounters
  - concurrent dispensings at geographically distant pharmacies
  - allergy entries contradicting other sources
  - medicines implausible for the recorded sex or age
  - two simultaneous regular prescribers for the same chronic drug at different doses
- Route flagged records to review and **never** auto-merge them.

*Transitivity check*
- If A↔B and B↔C link but A↔C scores low, the cluster is suspect and goes to review.

**(6) Simulation and metrics**

*Generator*
- Create a "true person" table, then render each source's record through corruption operators, each labelled with its operator:
  - missing IHI (e.g., 30% of pharmacy and patient-reported records)
  - nickname substitution
  - maiden or married surname
  - DOB day/month swap
  - single-character typo
  - address change
  - duplicate record in the same source
- Plant at least one **lookalike pair** (same name and DOB, different person and different medicines).
- Plant one **overlay** (a pharmacy record mixing two people's dispensings).

*Metrics*
- Pairwise precision, recall and F1 of links.
- **False-merge rate**, the safety-critical metric. Target 0 auto-merges of distinct people.
- Review-queue rate (the share of pairs sent to a human) and the share of review items that were true matches.
- Overlay detection recall.
- Blocking pair completeness.

---

## 2. Missing Sources ("Absence of Evidence Is Not Evidence of Absence")

**(1) What it is and why it happens**

A source can be:
- **entirely absent:**
  - the patient has no regular GP
  - the patient opted out of My Health Record (2,517,921 people, 9.9% of eligible Australians, when the opt-out period closed on 31 January 2019, according to ADHA CEO Tim Kelsey at Senate estimates)
  - an after-hours admission when the GP surgery and pharmacy are closed
- **partially scoped:**
  - the patient uses several pharmacies, but MedTrace sees only one
  - My Health Record PBS data excludes private (non-PBS) prescriptions, public-hospital inpatient supply and Section 100 supply (for example, through Aboriginal Health Services), and appears only after Services Australia finalises the claim\[36\]
- **temporally truncated:** the default view covers about the previous two years.\[37\]

A naive comparator that reads "not in the pharmacy list" as "not taking" generates false omissions, and worse, false reassurance.

**(2) Prevalence**
- The My Health Record opt-out figure above sets a floor of roughly one in ten patients with no national record at all.
- Many more will have empty or sparse records.
- An ICU study of delirious or mechanically ventilated patients found that 20 of 23 (87%) histories obtained only from an outpatient pharmacy, and 12 of 16 (75%) obtained only from family, still contained discrepancies (small samples). Every single source is incomplete.

**(3) Harm**
- The most common admission error is *omission* of a regular medicine: 46.4% of unintended discrepancies in Cornish.\[1\]
- A missing source is the classic mechanism. If the only dispensing pharmacy is not queried, a regularly used antiepileptic, anticoagulant or Parkinson's medicine can be silently left off the admission chart.
- An Australian study across three SA tertiary hospitals over three years (Bakker et al., PLoS ONE 2022) found that patients without a pharmacist-led medication history within 24 hours had a higher rate of Parkinson's medication errors (IRR 1.57, p = 0.010).

**(4) Current workaround**
- ACSQHC requires at least two sources.\[13\]
- Pharmacists ask "which pharmacies do you use?", phone each one, and record which sources were consulted in the BPMH.

**(5) MedTrace solutions**

*Source coverage manifest per patient*
- For each source, record one of:
  - `available + complete scope`
  - `available + partial scope` (with scope notes, e.g., "PBS only, excludes private scripts")
  - `queried, no record found`
  - `unavailable` (opt-out, offline, after-hours)

*Tri-state evidence per (medicine, source)*
- `PRESENT`
- `ABSENT_IN_COVERED_SCOPE` (the source should have seen it)
- `UNKNOWN` (source missing, or out of scope for that medicine type)
- Only `ABSENT_IN_COVERED_SCOPE` counts as evidence against a medicine. For example, a private script is out of PBS scope, so it is `UNKNOWN`, not absent.

*BPMH confirmability rule*
- If fewer than two independent sources are `available`, show a banner: "BPMH cannot be confirmed — only N source(s); ACSQHC requires ≥2."
- Generate a task, such as "call pharmacy X" or "ask patient about other pharmacies."

*Multi-pharmacy inference*
- If the patient-reported list contains a chronic medicine with no dispensing in the covered pharmacy for more than a full supply interval, prompt "possible second pharmacy" rather than "not taking."

**(6) Simulation and metrics**

*Generator*
- Drop whole sources per patient:
  - no GP record in 15% of patients
  - My Health Record opt-out in 10%
  - after-hours flag that makes GP and pharmacy unavailable
- Split one patient's dispensings across two pharmacies, with only one exposed.

*Metrics*
- **False-omission/false-cessation rate**: medicines wrongly labelled "not taking" when the true state was unknown. Target 0.
- Correct display of the "insufficient sources" banner, measured as sensitivity.
- Calibration of the completeness score against true list completeness.

---

## 3. Stale and Out-of-Date Records

**(1) What it is and why it happens**
- GP medication lists accumulate medicines that were ceased but never removed. Ceasing a drug is a deletion task nobody is prompted to do.
- Hospital changes do not flow back.
- Dose changes made by phone, notably warfarin adjusted after an INR result, change *how many tablets* a patient takes without generating a new prescription. The dispensing record keeps showing the same strength and the GP list keeps showing the old dose.
- Pharmacy last-fill dates can look current long after therapy stopped, or old while the patient still uses stockpiled supply.

**(2) Prevalence**
- In Boyce (2013), almost half of GP-list discrepancies were *non-current* medicines.
- In an Australian GP-integrated pharmacist study (Int J Pharm Pract 2023), the most common discrepancy was "medicines in patient's EMR not being used by patient": 51% of discrepancies (n = 340). Medicines taken but not recorded made up 21% (n = 140).
- In the prescription-exchange history study, dose-regimen errors affected 25.1% of captured medicines, consistent with dispensing data not reflecting current directions.

**(3) Harm**
- Restarting a ceased medicine (for example, an NSAID stopped after a GI bleed, or a stopped antihypertensive in a patient now hypotensive) is a *commission* error.
- Reinstating an old warfarin dose after an INR-driven reduction risks bleeding.
- Cornish's taxonomy rates wrong-dose and commission errors among those able to cause clinical deterioration.

**(4) Current workaround**
- Pharmacists ask "when did you last take it?", check the date of the GP list, check pharmacy fill dates, and ask about the anticoagulant clinic or INR book.

**(5) MedTrace solutions**

*Supply arithmetic*
- days_supply = (pack quantity × repeats-dispensed-so-far context) ÷ normalised daily dose.
- expected_runout = last_dispense_date + days_supply.
- Flag `POSSIBLY_CEASED` when today − expected_runout exceeds a grace period (for example, 0.5 × days_supply, or 30 days).
- Flag `ACTIVE_BY_SUPPLY` when within supply.

*Proportion of Days Covered (PDC) over 180 days*
- Very low PDC for a "regular" medicine suggests non-adherence or cessation.
- Show it as a pharmacist prompt, not a conclusion.

*Recency decay weighting*
- weight = exp(−Δt/τ), where Δt is document age.
- Set τ per source type: shorter for GP summaries without an update date, longer for dispensing.

*Document-age banner*
- Show "GP summary last updated 14 months ago."

*Phone-dose-change pattern*
- For anticoagulants (warfarin), insulin, and tapering steroids, *always* emit a "confirm current dose directly with patient/INR record" task when sources disagree on dose but agree on drug and strength.
- Raise the flag even when dispensing looks current, because these regimens change without a new prescription.

**(6) Simulation and metrics**

*Generator*
- Give each true medicine a start/stop timeline.
- For ceased medicines, keep them on the GP list with probability 0.5.
- Generate dispensing events with realistic pack sizes and jitter.
- Plant a warfarin case: true dose 3 mg daily after an INR change, GP list says 5 mg, dispensing shows 1 mg and 5 mg tablets.

*Metrics*
- Precision and recall for detecting ceased-but-listed medicines.
- Accuracy of the active/ceased status call against the timeline.
- Planted dose-change detection recall.

---

## 4. Semantic Inconsistency (Names, Brands, Combinations, Units, Frequency, Formulation, Free Text)

**(1) What it is and why it happens**

*Brand proliferation*
- Australia has many brands per molecule: an *MJA* commentary noted 81 brands for only eight ACE inhibitors.\[38\]
- Pharmacists routinely substitute brands under PBS rules.
- Until active-ingredient prescribing became mandatory (from February 2021), doctors used brand names for 80.5% of prescriptions.\[39\]

*How the four sources differ*
- Sources mix trade and generic names, different strength notation (mg vs microgram), and frequency abbreviations (BD/TDS/mane/nocte).
- Release forms differ: CR, MR, XR, SR versus immediate release.
- Combination products (perindopril/indapamide, metformin/sitagliptin) appear as one line in one source and two lines in another.
- Patients describe drugs functionally: "my blood thinner," "the water tablet," "the little white one."

**(2) Prevalence**
- Ortiz et al. (*MJA* 2010) found brand switching within one year in 43% of patients on statins, 40% on calcium-channel blockers, and 37% on SSRIs.
- Multiple switches occurred in 24%, 19% and 21% of patients respectively.\[40\]

**(3) Harm**
- Duplication: the patient takes two brands of the same molecule, or a combination product plus one of its components.
- A published case series (2023) described duplication errors where a carer did not know two differently named products contained the same drug. One involved over-diuresis.\[41\]
- MR↔IR confusion causes dosing-interval errors.
- mcg↔mg errors cause thousand-fold dosing mistakes.

**(4) Current workaround**
- Pharmacists mentally map brand to generic, ask patients to bring medicines in ("brown bag"), and read the packs.

**(5) MedTrace solutions**

*Terminology normalisation to AMT (part of SNOMED CT-AU)*
- Map every line to AMT concepts:
  - TPP/TPUU (trade product pack and unit of use)
  - MPUU (generic ingredient + strength + form)
  - MP (ingredient)
- Compare at **MPUU level** for "same product" and at **MP/ingredient-set level** for "same drug."
- Use the RxNorm IN/SCD/SBD hierarchy as the international analogue.
- For the hackathon, ship a curated synthetic AMT-like lookup table of about 150 products: brand → generic, ingredients, strength and form, ATC class, high-risk flag.

*String-to-concept matching*
- Normalise case, punctuation and salt names (e.g., "atorvastatin calcium" → atorvastatin).
- Use exact dictionary lookup first, then Jaro-Winkler or trigram fuzzy match over brand and generic names.
- Map anything below the confidence threshold to `UNMAPPED` and send it to review. Never silently drop it.

*Combination decomposition*
- Represent each product as a set of (ingredient, strength) pairs.
- Detect **duplication** when the ingredient sets of two concurrent lines intersect.

*Dose and frequency normalisation*
- Parse dose quantity × strength into a total daily dose in canonical units (mg, microgram, units).
- Frequency maps: daily/mane/nocte = 1, BD = 2, TDS = 3, QID = 4, weekly = 1/7, PRN = separate flag.
- Compare total daily dose, not tablet counts. "2 × 5 mg BD" equals "20 mg/day."

*Formulation class*
- Carry a release attribute (IR/MR) and a route.
- Flag an MR↔IR mismatch as a distinct discrepancy type, even when ingredient and daily dose agree.

*Free-text patient reports*
- Use an LLM extraction step constrained to output {candidate ingredient | therapeutic class (ATC), dose, frequency, confidence}.
- "My blood thinner" → class B01 (antithrombotic).
- Resolve against other sources' B01 drugs (warfarin vs apixaban), present it as "patient-reported class matches warfarin (GP) — confirm," and never auto-resolve.

**(6) Simulation and metrics**

*Generator*
- Render the same true medicine differently per source:
  - Australian brand names in pharmacy
  - generic in the GP list
  - combination product in one source and split components in another
  - "BD" vs "twice daily" vs "1 tab 2x/day"
  - mcg vs mg
  - MR in one source and IR in another
  - lay descriptions in the patient source
- Plant one *true* duplication (the patient really takes two brands of the same drug).

*Metrics*
- Normalisation accuracy (top-1 concept match) per source.
- **False-discrepancy rate**: brand-only or notation-only differences wrongly flagged. Target near 0.
- Duplication detection recall.
- Proportion of lines left `UNMAPPED`.

---

## 5. Intentional vs Unintentional Discrepancies, and Alert Fatigue

**(1) What it is and why it happens**

The WHO High 5s and Cornish classification distinguishes:
- **documented intentional** discrepancies (the prescriber changed therapy and wrote why)
- **undocumented intentional** discrepancies (deliberate, reason not recorded)
- **unintentional** discrepancies (errors)

A system that flags every difference treats deliberate withholding (for example, metformin held for contrast, or an antihypertensive held for hypotension) the same as a forgotten anticoagulant.

**(2) Prevalence**
- Tam's review found 19–75% of discrepancies were unintentional.\[42\]
- A pharmacist study found 72.3% unintentional and 27.7% intentional-undocumented.\[43\]
- Alert override rates in clinical decision support run from 46.2% to 96.2% (Poly et al., JMIR Med Inform 2020 systematic review, 23 studies). This is the cost of over-flagging.\[44\]

**(3) Harm**
- Alert fatigue causes real signals to be dismissed.\[45\]
- Undocumented intentional changes cause downstream errors: the GP or the next team "corrects" a deliberate hold, or never learns of it.

**(4) Current workaround**
- Pharmacists discuss each discrepancy with the medical team and document the reason.\[1\]

**(5) MedTrace solutions**

*Discrepancy taxonomy output*
- Each item carries a type:
  - omission
  - commission
  - dose
  - frequency
  - formulation
  - duplication
  - identity-uncertain
  - stale-listing
- Each also carries an intent status: `documented_intentional` (matched to a plan or note entry), `possibly_intentional` (a clinical-context rule fired, e.g., nil-by-mouth, AKI, peri-operative hold list), or `likely_unintentional`.

*Risk-tiered triage*
- priority = class_risk (APINCH or other high-risk list: high) × discrepancy_type_severity (omission or dose of a chronic medicine: high; brand-only: zero) × evidence_strength (number and trust of agreeing sources).
- Show a short "Must review" tier and collapse the rest.

*Suppression rules*
- Never alert on brand-only, notation-only, or same-ingredient differences in equivalent daily dose.

*Feedback learning*
- When the pharmacist marks a flag "intentional – not an error" or "not clinically relevant," update a per-(discrepancy type × drug class) acceptance rate.
- Demote categories with persistently low acceptance. Never fully suppress high-risk classes.

**(6) Simulation and metrics**

*Generator*
- Plant labelled discrepancies in all three intent classes, with admission-plan notes for the documented ones.

*Metrics*
- Alert PPV (the share of flags the "pharmacist" ground truth would act on).
- Recall of planted clinically significant unintentional discrepancies, kept at 100% for APINCH classes.
- Alerts per patient before and after feedback learning.
- Classification accuracy for intent status.

---

## 6. Medicines Outside All Systems

**(1) What it is and why it happens**

Some medicines never appear in any electronic source:
- OTC medicines
- complementary medicines
- samples
- medicines bought overseas or online
- medicines borrowed from family
- hospital-only or clinic-administered medicines (depot injections, infusions, specialist-clinic supply)

Partial visibility affects others:
- Private (non-PBS) prescriptions do not create PBS claims. They reach My Health Record only if the pharmacy uploads a dispense record.\[46\]
- Real-time prescription monitoring helps only for monitored drugs. SafeScript VIC states it monitors "all prescriptions for these medicines regardless of whether they receive a PBS subsidy or are private," covering Schedule 8 medicines, benzodiazepines, Z-drugs, quetiapine, codeine products, pregabalin, gabapentin and tramadol. Its data comes only from software connected to a prescription exchange service.\[47\]

**(2) Prevalence**
- 49.4% of Australians used a complementary medicine product in the previous 12 months (2021–22 national survey). 20.7% used both complementary and prescription or OTC medicines.\[48\]
- 57.2% of complementary-medicine users had not told their doctor (2004 South Australian population survey).\[49\]
- In the Sydney discharge-letter study, error rates fell substantially when OTC and herbal medicines were excluded.\[9\] These items are a major share of omissions.

**(3) Harm**
- Interactions: St John's wort with SSRIs or warfarin; high-dose fish oil or ginkgo with anticoagulants.
- Duplicate paracetamol or NSAID exposure from OTC combination products.
- Omission of clinic-administered antipsychotic depots or immunosuppressant infusions.

**(4) Current workaround**
- Structured BPMH interview prompts, for example: "any eye drops, inhalers, patches, injections, weekly or monthly medicines, vitamins, herbal products, pain relievers bought at a supermarket?"

**(5) MedTrace solutions**

*Patient/carer source as first-class*
- Items present *only* in the patient-reported source are labelled `PATIENT_ONLY` and kept, not discarded.
- Trust them for *existence*; verify them for *dose*.

*Hidden-medicines checklist generator*
- Generate interview prompts from what is *missing*. For example, an inhaler-requiring diagnosis with no inhaler in any source produces "ask about inhalers."
- Always prompt for: weekly medicines (methotrexate, alendronate), depots, eye drops, patches, OTC analgesics, complementary medicines.

*Complementary-medicine interaction screen*
- Run a small rule table (St John's wort, ginkgo, fish oil, turmeric, and similar) against anticoagulants, antiplatelets and serotonergic drugs.

*Scope annotation*
- Tag dispensing records with PBS vs private status.
- When a monitored drug appears in patient report but not in PBS data, note that the absence is explainable by "private/other pharmacy."

**(6) Simulation and metrics**

*Generator*
- Give 50% of synthetic patients at least one complementary or OTC item that exists only in the patient source.
- Mark 10% of dispensings "private," so they are excluded from the My Health Record/PBS view.
- Add one depot injection recorded only in a hospital clinic note.

*Metrics*
- Recall of patient-only items carried into the BPMH draft.
- Interaction-flag precision.
- False "not taking" calls on private-script medicines. Target 0.

---

## 7. Transitions-of-Care Fragmentation (Admission, Discharge, Hospital ↔ GP/Pharmacy)

**(1) What it is and why it happens**
- Medication changes made in hospital must reach the GP and community pharmacy through the discharge summary, which may be late, incomplete or never sent.
- The next admission then starts from a pre-change GP list.

**(2) Prevalence (Australia)**

*Discharge summary content*
- At baseline in an Australian metropolitan hospital (Ooi et al., Int J Clin Pharm 2017), only 45.9% (263/573) of medication changes were documented by doctors in discharge summaries.
- In the same study, a pharmacist-prepared summary captured 72.8% of changes, compared with 31.5% for the doctor-prepared summary.
- 15% of medicines intended to continue were unintentionally omitted from discharge summaries at one teaching hospital.\[50\]

*Timeliness and receipt*
- An RACGP general-practice audit found:
  - 92% of discharge summaries were received
  - only 55% arrived before the first post-discharge GP visit
  - 44% contained no medication details\[51\]
- In an SA survey, 86.7% of GPs rated the rationale for medication changes as important, but only 29.3% said it was always or often provided.\[52\]

**(3) Harm**
- WHO reports discharge errors or miscommunication in 65–83% of patients.
- 69% of discrepancies remain unresolved 10–14 days after discharge.\[4\]
- A typical pathway: a hospital stops a drug, the GP list still holds it, the next admission restarts it.

**(4) Current workaround**
- Pharmacist discharge medication-management summaries, phone handover to the GP and community pharmacy, and the patient carrying their own list.

**(5) MedTrace solutions**

*"Last discharge" as a fifth evidence stream*
- Store the most recent discharge medication list (synthetic) as a time-stamped event, even though it is not one of the four live sources.

*Change propagation check*
- For each change in the last discharge (ceased, started or dose-changed), test whether the GP list and dispensing history reflect it after the discharge date.
- If the GP list predates the change or still shows the old state, flag `UNPROPAGATED_DISCHARGE_CHANGE`, with the discharge as provenance.

*Discharge-side output*
- Generate a GP and pharmacy handover listing each change with its reason. This directly addresses the 29.3% "rationale rarely communicated" gap.

**(6) Simulation and metrics**

*Generator*
- Give 20% of patients a prior admission in which one medicine was ceased and another started.
- Propagate the change to the GP list only with probability 0.4.

*Metrics*
- Recall of unpropagated changes.
- Correct attribution of the newer source as authoritative for those medicines.

---

## 8. Conflicting Sources With No Single Authority

**(1) What it is and why it happens**

Each source is authoritative for something different:
- **Dispensing** for what was *supplied* and when, but not what is taken.
- **GP** for what was *intended*, but often stale.
- **Patient** for what is *actually taken*, including OTC items, but weak on names and doses.
- **Hospital EMR** for the current inpatient plan.

No source is ground truth. The BPMH is a reconstruction.

**(2) Prevalence**
- In a primary-care study of older patients with polypharmacy, patient, GP and pharmacy lists disagreed for 72% of patients and 22% of medicines (BMC Prim Care 2026).\[53\]
- Any single Australian electronic source, used alone, had errors in more than 90% of patients (prescription-exchange history study).\[54\]

**(3) Harm**
- Picking the wrong "winner" reproduces whichever error that source carries.
- Averaging hides the conflict that needs human attention.

**(4) Current workaround**
- The pharmacist triangulates. Agreement across two or more sources is confirmation; disagreement prompts a direct question to the patient.\[55\]

**(5) MedTrace solutions**

*Per-attribute fusion*
- Resolve *existence*, *dose* and *frequency* separately, because sources differ in reliability per attribute:
  - pharmacy is good for strength
  - patient is good for "actually taking"
  - GP is good for indication

*Weighted evidence score per attribute value*
- score(v) = Σ_sources trust[s, attr] × recency(s) × scope_ok(s, med) × [s asserts v]
- The leading value is the suggestion. Margin and entropy give confidence. Below a margin threshold, the system abstains and outputs "CONFLICT — ask patient."

*Per-source trust as Beta(α, β) per (source, attribute)*
- Each pharmacist decision that confirms or rejects a source's value increments α or β.
- Trust = α/(α+β), with an uncertainty band shown in the UI.
- This is the memory engine, and it makes "learning" visible: for example, "GP-list dose trust fell from 0.80 to 0.62 after 5 corrections."
- More advanced options: Dawid–Skene or truth-discovery EM over many patients.

*Provenance on every cell*
- Show source, document date, original string and mapping step.
- The pharmacist can see *why* the system suggests a value, which supports trust and auditability.

**(6) Simulation and metrics**

*Generator*
- Assign each synthetic source a hidden per-attribute error rate. For example:
  - GP dose error 25%
  - pharmacy existence error 10% (multi-pharmacy)
  - patient name error 30%
- Simulate pharmacist feedback from ground truth.

*Metrics*
- Per-attribute resolution accuracy versus planted truth.
- Abstention rate and accuracy when not abstaining (selective accuracy).
- Convergence of learned trust toward the hidden error rates (mean absolute error over feedback rounds), the demo's "learning curve."

---

## Summary Table

| Fragmentation type | Patient harm | MedTrace detection method | Synthetic simulation | Evaluation metric |
|---|---|---|---|---|
| Identity/linkage (missing IHI, nicknames, maiden name, DOB swap, duplicates, overlays, lookalikes) | Wrong patient's medicines or allergies used; missed history; wrong-patient supply deaths | Deterministic IHI tier → Fellegi–Sunter with Jaro-Winkler, nickname and DOB-swap comparators; blocking; two-threshold review queue; lookalike guard; overlay inconsistency detector | Corruption operators per source; planted lookalike pair and overlay | Pairwise P/R/F1; **false-merge rate = 0**; review-queue rate; overlay recall |
| Missing sources | Silent omission of regular medicines; false reassurance | Source coverage manifest; tri-state evidence (present / absent-in-scope / unknown); ≥2-source BPMH banner | Drop sources (no GP, My Health Record opt-out, after-hours); split pharmacies | False-cessation rate = 0; banner sensitivity |
| Stale records | Restarting ceased medicines; old warfarin dose | Days-supply run-out, PDC, recency decay, document-age banner, forced confirmation for warfarin/insulin/steroid doses | Timelines with ceased-but-listed medicines; phone dose change | Ceased-detection P/R; dose-change recall |
| Semantic inconsistency | Duplication (two brands, combination + component); MR/IR and unit errors | AMT MPUU/MP normalisation; combination decomposition; total-daily-dose normalisation; LLM class extraction for free text | Brand/generic/combination/unit/frequency/lay-term rendering; planted true duplication | Mapping accuracy; false-discrepancy rate; duplication recall |
| Intentional vs unintentional | Alert fatigue; deliberate holds reversed | Discrepancy taxonomy + intent status; APINCH-weighted triage; suppression of trivial differences; feedback-based demotion | Planted documented, undocumented and unintentional discrepancies | Alert PPV; APINCH recall = 100%; alerts per patient |
| Outside all systems (OTC, complementary, private, depot) | Interactions; omissions | Patient-only items kept; hidden-medicines prompt generator; complementary-medicine interaction rules; PBS/private scope tags | Patient-only complementary medicines; private dispensings; clinic depot | Patient-only recall; interaction precision |
| Transitions of care | Changes reversed or lost after discharge | Last-discharge stream; unpropagated-change check; handover generator | Prior admission with changes partially propagated | Unpropagated-change recall |
| Conflicting sources | Wrong "winner" chosen | Per-attribute trust × recency × scope fusion; abstain on low margin; Beta trust memory; provenance | Hidden per-source error rates; simulated feedback | Resolution accuracy; selective accuracy; trust-estimate MAE over time |

---

## Recommendations: What to Build in 3.5 Days

Priority order balances clinical impact, demo visibility in one to four minutes, and differentiation:

1. **Identity linkage with a near-miss human-confirmation queue (Day 1).**
   - Differentiator: most entries will assume a clean patient key.
   - Demo: "Margaret Smith 03/07/1948" (EMR) vs "Peggy Smyth-Jones 07/03/1948" (pharmacy) linked with an explained score; a lookalike "Margaret Smith, same DOB" *refused* auto-link and sent to the queue.
   - Effort: about 300 lines of Python, using the `jellyfish` library (Jaro-Winkler, metaphone) plus hand-set m/u weights.
2. **Semantic normalisation with duplication detection (Day 1–2).**
   - Without it every other comparison produces false alarms.
   - Demo: Coversyl Plus (pharmacy) plus perindopril (GP) gives a *true duplication* flag, while Lipitor vs atorvastatin produces *no* flag.
   - Build a 150-row synthetic AMT-style table.
3. **Stale-record temporal reasoning (Day 2).**
   - Demo: "GP list says diclofenac; last dispensed 11 months ago for a 30-day supply → possibly ceased."
   - Plus the warfarin phone-dose-change case, forced to "confirm with patient/INR book."
   - Highly relatable to pharmacist judges.
4. **Missing source as unknown, with the ACSQHC two-source rule (Day 2, small).**
   - Cheap to build and conceptually distinctive.
   - Demo: an after-hours admission with My Health Record opted out shows "BPMH not confirmable" instead of a false "not taking."
5. **Trust-weighted conflict resolution + intentional/unintentional triage + memory engine (Day 3).**
   - This is the Track 1 "learning" story.
   - Demo: the pharmacist rejects GP doses three times, the trust bar visibly drops, and the next patient's conflict resolves differently. An APINCH-weighted "Must review" tier keeps alert counts low.
6. *Stretch (half day, if time):* patient-only OTC and complementary items plus a St John's wort–warfarin interaction flag. Very cheap if the patient source already flows through normalisation.

**Defer:** full discharge-propagation logic. Represent it as one planted scenario rather than a general engine.

**Evaluation harness (build alongside, Day 0.5–1):**
- The generator emits `ground_truth.json`: the true person, the true regimen timeline, and every planted fragmentation with its type label.
- A `pytest`-style scorer reports per-type precision, recall and F1, the false-merge rate, the false-cessation rate, alerts per patient, and the trust-MAE learning curve.
- Show a one-slide scorecard in the demo. Judges reward measured claims.

**Suggested demo arc (about 3 minutes)**

| Time | Scene |
|---|---|
| 0:00–0:30 | Problem stat: 53.6% of admitted patients have an unintended discrepancy; 250,000 medicine-related admissions a year in Australia |
| 0:30–1:15 | Identity: match across 4 sources, lookalike refused, one review click |
| 1:15–2:15 | Reconciliation view: duplication, stale NSAID, warfarin dose conflict, after-hours missing-source banner; provenance on hover |
| 2:15–2:50 | Pharmacist feedback → trust update → re-run |
| 2:50–3:00 | Scorecard against planted truth |

## Caveats

- **Statistics vary by method and setting.** The 10–67% range in Tam reflects heterogeneous definitions, so quote ranges and name the study. WHO's "86%" and "up to 97%" figures come from secondary summaries of mixed studies.\[56\]
- **Patient-matching figures are mostly US and partly non-peer-reviewed.** The ONC 50–60% cross-organisation match rate comes from interviews;\[22\] the 18% duplicate figure is an industry survey.\[21\] No public quantitative data on Australian IHI match or duplicate rates was found, so do not claim one.
- **Some harm cases are news reports or secondary accounts.** These include Werribee Mercy (2026), the SA inquest (2026, ongoing at the time of reporting) and the Macquarie University Hospital case. Present them as illustrative, not as findings of a coroner unless the final findings are cited.
- **The warfarin phone-dose-change mechanism is clinically well recognised, but no Australian prevalence figure was located.** Present it as a known pattern.
- **SafeScript scope differs by state.** Victoria includes gabapentin; NSW does not.\[47\]\[57\] Neither replaces a full dispensing history.
- **All MedTrace data is synthetic.** Results show detection logic against planted truth, not clinical effectiveness. The system should be positioned as decision support that prepares a draft BPMH for pharmacist confirmation, consistent with ACSQHC's requirement that clinicians, not software, reconcile.\[58\]

## Sources

1. [Unintended medication discrepancies at the time of hospital admission - PubMed](https://pubmed.ncbi.nlm.nih.gov/15738372/)
2. [Medication safety in acute care in Australia: where are we now? Part 1: a review of the extent and causes of medication problems 2002–2008](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2733897/)
3. [Frequency, type and clinical importance of medication history errors at admission to hospital: a systematic review](https://www.cmaj.ca/content/173/5/510)
4. [Medication Without Harm - IPU](https://ipu.ie/ipu-review-article/medication-without-harm/)
5. [Medication error rate in transition of care: General Practitioner (GP) referrals to a regional emergency department - Macquarie University](https://researchers.mq.edu.au/en/publications/medication-error-rate-in-transition-of-care-general-practitioner-/)
6. [Audit of General Practitioner Medication Lists for Older Patients at a Regional Hospital - Boyce - 2013 - Journal of Pharmacy Practice and Research - Wiley Online Library](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.2055-2335.2013.tb00230.x)
7. [Using personal health records for medication continuity during transition of care: An observational study - PubMed](https://pubmed.ncbi.nlm.nih.gov/39183671)
8. [Unintended Medication Discrepancies at the Time of Hospital Admission](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/486421)
9. [Association between admission medication reconciliation by pharmacists on the accuracy of hospital discharge medication lists - Francis - 2021 - JACCP: JOURNAL OF THE AMERICAN COLLEGE OF CLINICAL PHARMACY - Wiley Online Library](https://accpjournals.onlinelibrary.wiley.com/doi/abs/10.1002/jac5.1420)
10. [Draft report eHealth High Risk Medicine Safety](https://www.health.vic.gov.au/sites/default/files/2025-06/ehealth-high-risk-medicine-safety-lit-review-and-enviro-scan.pdf)
11. [Which Medications Carry the Greatest Safety Risks?](https://www.pharmacytimes.com/view/which-medications-carry-the-greatest-safety-risks)
12. [Patient harm from cardiovascular medications](https://journals.sagepub.com/doi/pdf/10.1177/20420986211027451)
13. [Medication reconciliation](https://www.nationalstandards.safetyandquality.gov.au/4.-medication-safety/documenting-patient-information/medication-reconciliation)
14. [Standard Operating Protocol for Medication Reconciliation](https://cdn.who.int/media/docs/default-source/patient-safety/high5s/h5s-sop.pdf?sfvrsn=594d8e49_4)
15. [My Health Record](https://en.wikipedia.org/wiki/My_Health_Record)
16. [Identifier—record status, Individual Healthcare Identifier record status code N](https://meteor.aihw.gov.au/content/index.phtml/itemId/743464)
17. [IHI](https://knowledge.helix.medicaldirector.com/topics/patient_ihi.html)
18. [PAGE 1 OF 5 Individual Healthcare Provider User Guide AUDIENCE](https://www.countrysaphn.com.au/wp-content/uploads/2020/11/his-individual-healthcare-provider-user-guide.pdf)
19. [Healthcare Identifiers - Setup - Specialist Complete](https://specialistcomplete.com/setup-healthcare-identifiers/)
20. [PATIENT IDENTIFICATION AND MATCHING FINAL REPORT February 7, 2014](https://healthit.gov/sites/default/files/patient_identification_matching_final_report.pdf)
21. [Enhanced Patient Matching Is Critical to Achieving Full Promise of Digital Health Records](https://www.pew.org/en/research-and-analysis/reports/2018/10/02/enhanced-patient-matching-critical-to-achieving-full-promise-of-digital-health-records)
22. [PATIENT IDENTIFICATION AND MATCHING FINAL REPORT February 7, 2014](https://healthit.gov/wp-content/uploads/2017/09/patient_identification_matching_final_report.pdf)
23. [Electronic Health Records: Patient Matching and Data Standardization Remain Top Challenges](https://www.pew.org/en/research-and-analysis/fact-sheets/2016/11/electronic-health-records-patient-matching-and-data-standardization-remain-top-challenges)
24. [Duplicate Medical Records vs Overlays: Key Differences](https://www.managedoutsource.com/blog/how-duplicate-medical-records-different-from-overlays/)
25. [Keys to Help Solve Patient Data Matching Save to myBoK](https://journal.ahima.org/Portals/0/archives/AHIMA%20files/Keys%20to%20Help%20Solve%20Patient%20Data%20Matching.pdf)
26. [Woman's family wrongly told she was dead in hospital identity error - ABC News](https://www.abc.net.au/news/2026-07-22/mistaken-identity-data-hospital-error-death-notice-police/106936454)
27. [Inquest hears elderly man who died was given another person's prescription medication - ABC News](https://www.abc.net.au/news/2026-05-19/man-died-after-prescription-medication-bungle-inquest-told/106695682)
28. [What happens when patient identification goes wrong? - Australian Pharmacist](https://www.australianpharmacist.com.au/what-happens-when-patient-identification-goes-wrong/)
29. [Patient Identification Errors](https://zaggocare.org/patient-identification-errors/)
30. [Probabilistic record linkage](https://academic.oup.com/ije/article/45/3/954/2572621)
31. [lhncbc.nlm.nih.gov](https://lhncbc.nlm.nih.gov/LHC-publications/pubs/Analysisofaprobabilisticrecordlinkagetechniquewithouthumanreview.html)
32. [lhncbc.nlm.nih.gov](https://lhncbc.nlm.nih.gov/LHC-publications/pubs/Analysisofidentifierperformanceusingadeterministiclinkagealgorithm.html)
33. [Real world performance of approximate string comparators for use in patient matching - PubMed](https://pubmed.ncbi.nlm.nih.gov/15360771/)
34. [(PDF) Real World Performance of Approximate String Comparators for use in Patient Matching](https://www.researchgate.net/publication/8353095_Real_world_performance_of_approximate_string_comparators_for_use_in_patient_matching)
35. [Identity matching of patient records](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10657613)
36. [Medicare information](https://www.digitalhealth.gov.au/initiatives-and-programs/my-health-record/whats-inside/medicare-information)
37. [Medication Safety and the My Health Record Webinar Handout](https://www.countrysaphn.com.au/wp-content/uploads/2020/11/Webinar-Handout-Medication-Safety-and-the-My-Health-Record.pdf)
38. [Multiple drug brands confusing](https://insightplus.mja.com.au/2012/1/multiple-drug-brands-confusing)
39. [Doctors must now prescribe drugs using their chemical name, not brand names. That’s good news for patients](https://theconversation.com/doctors-must-now-prescribe-drugs-using-their-chemical-name-not-brand-names-thats-good-news-for-patients-153796)
40. [Generic substitution of commonly used medications: Australia-wide experience, 2007–2008](https://www.mja.com.au/journal/2010/192/7/generic-substitution-commonly-used-medications-australia-wide-experience-2007)
41. [(PDF) Duplication errors due to brand name confusion; It is not always the name—Short case series](https://www.researchgate.net/publication/373949414_Duplication_errors_due_to_brand_name_confusion_It_is_not_always_the_name-Short_case_series)
42. [Google Scholar](https://scholar.google.com/scholar_lookup?title=Frequency%2C+type+and+clinical+importance+of+medication+history+errors+at+admission+to+hospital%3A+a+systematic+review&amp=&author=VC+Tam&amp=&author=SR+Knowles&amp=&author=PL+Cornish&amp=&author=N+Fine&amp=&author=R+Marchesano&amp=&author=EE+Etchells&amp=&publication_year=2005&amp=&journal=CMAJ&amp=&pages=510-515&amp=&doi=10.1503%2Fcmaj.045311&amp=&pmid=16129874)
43. [The Role of the Clinical Pharmacist in Hospital Admission Medication Reconciliation in Low-Resource Settings](https://doi.org/10.3390/pharmacy13040107)
44. [Appropriateness of Overridden Alerts in Computerized Physician Order Entry: Systematic Review](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7400042/)
45. [Alert Fatigue in Healthcare: Why 90% of CDS Alerts Get Ignor](https://www.mindbowser.com/alert-fatigue-healthcare/)
46. [Understanding Active Script List and My Health Record Uploads](https://help.parchment.health/en/articles/12947862-understanding-active-script-list-and-my-health-record-uploads)
47. [SafeScript for prescribers and pharmacists](https://www.health.vic.gov.au/safescript/safescript-for-prescribers-and-pharmacists)
48. [Prevalence and Characteristics of Australians Complementary Medicine Product Use, and Concurrent Use with Prescription and Over-the-Counter Medications—A Cross Sectional Study - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9860983/)
49. [Factors influencing the use of complementary and alternative medicine and whether patients inform their primary care physician](https://www.researchgate.net/publication/221805852_Factors_influencing_the_use_of_complementary_and_alternative_medicine_and_whether_patients_inform_their_primary_care_physician)
50. [An audit of medication information in electronic discharge ...](https://onlinelibrary.wiley.com/doi/am-pdf/10.1002/jppr.1340)
51. [RACGP - Communication at the interface between hospitals and primary care - a general practice audit of hospital discharge summaries](https://www.racgp.org.au/afp/2013/december/hospital-discharge-summaries)
52. [General practitioners' perspectives on discharge summaries from a health network of three hospitals in South Australia - PubMed](https://pubmed.ncbi.nlm.nih.gov/37356916/)
53. [Discrepancies in prescribed medications as reported by patients, general practitioners, and community pharmacists in older patients with polypharmacy in primary care](https://link.springer.com/article/10.1186/s12875-026-03332-3)
54. [Accuracy of medication histories derived from an Australian cloud-based repository of prescribed and dispensed medication records - PubMed](https://pubmed.ncbi.nlm.nih.gov/35719101/)
55. [The Ultimate Guide to Medication Reconciliation: A 5-Step Process for Patient Safety - Simbie AI](https://www.simbie.ai/medication-reconciliation/)
56. [Accuracy of best possible medication histories by pharmacy students: an observational study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9749631/)
57. [SafeScript NSW - List of monitored medicines](https://www.health.nsw.gov.au/pharmaceutical/safescript/Pages/monitored-medicines.aspx)
58. [Medication Safety Standard](https://www.safetyandquality.gov.au/national-standards/nsqhs-standards/medication-safety-standard)
