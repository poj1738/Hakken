# MedTrace `detect.py`: consultant pharmacist review of judgement calls 11 to 14

Three of your four rules would stand up with a practising Australian hospital pharmacist, but each one needs a specific change:

- **(11)** The dose versus frequency label is fine. Severity must follow the change in daily dose and the drug's risk. The rule that an equal daily dose is never flagged is too absolute.
- **(12)** Confirming the dose of warfarin, insulin and tapering steroids should be a separate verification task, not a ranked finding.
- **(13)** The patient's own account and a corroborated supply lapse should outweigh an active GP listing. A lapse on its own should never produce a commission finding.
- **(14)** Leaving the admission chart out of the BPMH vote is correct and matches every definition. A disagreement between the chart and a single GP list should still be shown as a finding, flagged as resting on an unverified BPMH, rather than as a "conflict".

## TL;DR
- No Australian body (ACSQHC, SHPA, NSW TAG, or the WHO High 5s protocol as used by Stark et al.) publishes a discrepancy taxonomy that splits dose from frequency, so that label is your call. Internationally, Pippins 2008 codes 100 mg bd vs 200 mg daily as a dose and frequency discrepancy even though the daily dose is the same. Severity should therefore come from the daily-dose ratio and the drug's risk, not the label.
- Confirming the current dose of warfarin, insulin and tapering steroids is universal practice. It rests on SHPA's rule that high-risk medicines need confirmation from a further source. No Australian document says "always confirm the warfarin dose at admission" in those words. Show it as a per-patient verification task, not a finding.
- Every definition makes the BPMH what the patient actually took before admission, independent of the admission orders (High 5s SOP: "Retain BPMH separate from MAR"). The 16.9% figure behind your GP-list prior is not a GP-list figure: it is Elliott 2023's commission-error rate for medication histories built from prescription-exchange records (MedView). Re-label your 0.60 GP prior as an assumption.

## Key sources used (and what each covers)
- **ACSQHC, NSQHS Standards 2nd ed. (updated May 2021), Medication Safety Standard.** https://www.safetyandquality.gov.au/national-standards/nsqhs-standards/medication-safety-standard
  - Action 4.05: "Clinicians take a best possible medication history, which is documented in the healthcare record on presentation or as early as possible in the episode of care."\[1\]
  - Action 4.06: "Clinicians review a patient's current medication orders against their best possible medication history and the documented treatment plan, and reconcile any discrepancies on presentation and at transitions of care."\[1\]
- **SHPA, Standards of Practice for Clinical Pharmacy Services, Chapter 1: Medication Reconciliation.** J Pharm Pract Res 2013;43(2 suppl):S6 to S10 (copy at adpha.au).
  - Defines the medication history as "a record of all the medicines actually taken by the patient in the period before admission or presentation" (p. S7).\[2\]
  - Requires confirmation from a further source when "the medication history includes high-risk medicines" (p. S10).\[2\]\[3\]
- **WHO High 5s, Standard Operating Protocol: Assuring Medication Accuracy at Transitions in Care: Medication Reconciliation, Version 3, September 2014.** https://cdn.who.int/media/docs/default-source/patient-safety/high5s/h5s-sop.pdf. ACSQHC was the Australian Lead Technical Agency.\[4\]
- **Stark HE, Graudins LV, McGuire TM, Lee CY, Duguid MJ.** Implementing a sustainable medication reconciliation process in Australian hospitals: the WHO High 5s project. Res Social Adm Pharm 2020;16(3):290 to 298. doi:10.1016/j.sapharm.2019.05.011.\[5\]
- **Elliott RA, Taylor SE, Koo SMK, Nguyen AD, Liu E, Loh G.** Accuracy of medication histories derived from an Australian cloud-based repository of prescribed and dispensed medication records. Intern Med J 2023;53(6):1002 to 1009. doi:10.1111/imj.15857 (PubMed 35719101).\[6\]
- **Boyce 2013.** Audit of General Practitioner Medication Lists for Older Patients at a Regional Hospital. J Pharm Pract Res 2013. doi:10.1002/j.2055-2335.2013.tb00230.x.\[7\]
- **Chen HH, Taylor SE, Harding AM, Taylor DMcD.** Accuracy of medication information sources compared to the BPMH for patients presenting to the ED. Emerg Med Australas 2018;30(5):654 to 661. doi:10.1111/1742-6723.12965 (PubMed 29609221).\[6\]
- **International studies:**
  - Tam VC et al. Frequency, type and clinical importance of medication history errors at admission to hospital: a systematic review. CMAJ 2005;173:510 to 515.
  - Cornish PL et al. Arch Intern Med 2005;165:424 to 429.\[8\]
  - Pippins JR et al. Classifying and predicting errors of inpatient medication reconciliation. J Gen Intern Med 2008;23(9):1414 to 1422. doi:10.1007/s11606-008-0687-9.\[9\]
- **State documents:**
  - Queensland Health: Anticoagulant Guideline for Hospitalised Adult Patients (Feb 2022, minor update June 2026), and Guideline for Warfarin Management in the Community.
  - NSW Health: PD2020_045 High-Risk Medicines Management.
  - NSW CEC: High-Risk Medicine Standards (Version 1.0, October 2025).\[10\]
  - WACHS South West: Medication Reconciliation: Completing the Medication History and Management Plan Procedure (2023).\[11\]

---

## 11. Frequency error that changes the daily dose: dose or frequency discrepancy?

**Verdict: partially agree.**
- Keep "same strength per dose, different doses per day → frequency" as the label.
- Change two things:
  - Compute severity from the daily-dose ratio and the drug, independently of the label.
  - Change "equal total daily dose, different split → never flagged" to "not flagged, except for a curated list of drugs where the split matters".
- Fix the docstring. "Frequency = same daily dose, different split" is wrong under your own rule and under the literature.

### 11.1 Is there a published Australian convention?
**Cited evidence: no Australian convention classifies discrepancies by attribute.**
- **WHO High 5s SOP (2014, Step 3, p. 12):** classifies discrepancies only by intent, as "undocumented intentional" or "unintentional", where the prescriber "unintentionally changed, added or omitted a medication the patient was taking prior to admission".\[4\] It does not separate dose from frequency.
- **Stark et al. 2020 (the Australian High 5s implementation):** reported against the High 5s measures (unintentional and undocumented intentional discrepancies), with no dose versus frequency rule. The ACSQHC status report on Medication Without Harm summarises it as:
  - 42,003 patient records across 10 health services;\[12\]
  - 49.5% of patients reconciled within 24 hours;\[12\]
  - unintentional discrepancies falling from 15.2% to 11.1%.\[12\]
- **SHPA Chapter 1 (2013) and NSQHS Actions 4.05 and 4.06:** describe the process (obtain, confirm, compare, supply) and require recording "name (active ingredient and brand), dose, frequency and duration" (SHPA Table 1.2, p. S8).\[2\] They do not classify discrepancies by attribute.
- **NSW TAG:** I found only its high-risk medicines repository (APINCH resources supporting PD2020_045).\[13\] I found no NSW TAG discrepancy classification. Treat "NSW TAG classification" as unverified unless you have a specific document.

**Cited evidence: international taxonomies diverge.**
- Tam 2005 and Cornish 2005 use separate "incorrect dose" and "incorrect frequency" categories alongside omission and commission.\[14\] Neither defines the edge case.
- Pippins 2008 (the study that preceded MARQUIS) gives a coding instruction: "100 mg bid vs. 200 mg qd would be a discrepancy in dose and frequency even though the total daily dose is the same".\[9\] I saw this in the article's coding appendix as indexed by Springer; the full text is paywalled.
- MedTax puts these into a single category:
  - MedTax is Almanasreh E, Moles R, Chen TF (University of Sydney), Res Social Adm Pharm 2020;16(2):142 to 148, doi:10.1016/j.sapharm.2019.04.005. It "comprises 12 main types and 28 sub-types of discrepancies".\[6\]
  - Its single category covers discrepancies "related to strength and/or frequency and/or number of units of dosage form and/or the total daily dose".\[6\]\[15\]
  - Imfeld-Isenegger et al., Pharmacy (Basel) 2020;8(1):36, applied MedTax and found this the most frequent type among 317 discrepancies.\[6\]
  - Elliott 2023 likewise reports a single "dose-regimen error" category.\[6\]

**Inference:** the most common convention is one "dose regimen" category with descriptive subtypes. Your two-label split is defensible but not standard.

### 11.2 If the convention is "classify by what the prescriber got wrong", is your rule right?
**Opinion (practice norm): yes.** For clopidogrel 75 mg bd versus 75 mg daily, the prescriber chose the right tablet and the wrong schedule. A pharmacist would write "frequency error, results in double the daily dose". Your rule reads it the same way.

Edge cases to code explicitly:
- **Different strength and different frequency** (e.g. 50 mg tds vs 75 mg bd): label it "dose and frequency", not one or the other. This matches Pippins.\[9\]
- **Same strength but a different number of units** (2 tablets daily vs 1 tablet daily): this is a dose error, not a frequency error, because the dose per administration changed. Make sure your "strength per unit" test uses dose per administration, not tablet strength.
- **Weekly versus daily** (methotrexate, alendronate): treat as frequency, with a "catastrophic class" severity override (see 11.4).

**Recommendation:**
- Store subtype fields: per-dose ratio, administrations-per-day ratio, and daily-dose ratio.
- Derive the label from those fields.
- Show the pharmacist a plain-English statement, e.g. "charted 150 mg/day vs 75 mg/day at home".

### 11.3 Same total daily dose, different split, immediate-release: should it ever be flagged?
**Cited evidence:** none of the Australian sources address this. Pippins 2008 counts it as a discrepancy.\[9\] The High 5s definition ("unintentionally changed") would also capture it in principle.

**Opinion: yes, for a short curated list; otherwise suppress.** A practising pharmacist would query a change in split for:
- **Levodopa preparations:** timing and fractionation drive motor control, so bd vs qid at the same daily dose is clinically significant.
- **Antimicrobials:** time-dependent beta-lactams; and, the other way round, aminoglycosides, where once-daily versus divided dosing changes toxicity.
- **Corticosteroids:** hydrocortisone replacement given as split physiological doses; prednisolone moved from morning to divided dosing (more HPA suppression, insomnia).
- **Glucose-lowering drugs:** insulin (the basal and bolus split); sulfonylureas taken with meals.
- **Lithium and narrow-therapeutic-index antiepileptics** (carbamazepine IR, valproate): once-daily versus divided dosing changes peaks, troughs and how levels are interpreted.
- **Immediate-release opioids for chronic pain:** where the regular schedule is replaced by a different interval.
- **Furosemide timing** (e.g. 80 mg mane vs 40 mg bd): usually intentional. Low severity; flag only if your over-flag budget allows.

**Recommendation:**
- Add a `split_sensitive` field to the drug knowledge table.
- Emit a low-severity "regimen split differs" finding only for those drugs.

### 11.4 Does the classification matter for severity?
**Opinion: no.** A frequency error that doubles the daily dose should rank the same as a dose error that doubles it. Harm follows exposure and drug risk, not which field was wrong.

**Cited support:**
- Tam 2005 recommends that all error types, "including those of omission, commission and dose or frequency, should be evaluated" for clinical importance.\[14\]
- Cornish 2005 rated severity by the potential for discomfort or deterioration, not by type.\[8\]

**Recommendation:**
- Severity = f(daily-dose ratio, drug risk class (APINCH), direction (over vs under), narrow therapeutic index).
- Worked example: clopidogrel at 2x the daily dose is a moderate bleeding-risk error for an antiplatelet. It should rank above a statin dose discrepancy but below a doubled warfarin or insulin dose.

---

## 12. Should every current warfarin, insulin glargine and prednisolone generate "dose cannot be confirmed"?

**Verdict: agree with the reasoning, disagree with the presentation.**
- Agreement between sources that cannot see the dose change is not confirmation. That is exactly how a pharmacist thinks.
- Emit it as a verification task in a separate lane: one per patient, pinned above the ranked findings.
- Promote it to a finding only when confirmation fails, or when the confirmed dose differs from the chart.

### 12.1 Is "always confirm the current warfarin dose at admission" standard and citable?
**Cited evidence (indirect, strong):**
- **SHPA Chapter 1, p. S10:** "Confirmation from a further source is required if: ... the medication history includes high-risk medicines."\[2\]\[3\]
- **APINCH:** warfarin and insulin are core APINCH medicines. SA Health's APINCH list includes "I - Insulin: All insulins" and "H - Heparin and other anticoagulants: ... all anticoagulants, including the New Oral Anticoagulants".\[16\]
- **NSW:**
  - Health PD2020_045 High-Risk Medicines Management requires facility protocols for anticoagulants and insulin.\[17\]\[18\]
  - The NSW CEC High-Risk Medicine Standards (Version 1.0, October 2025) include, for warfarin, a "prompt to ascertain and continue brand of warfarin being taken by patients on existing therapy".\[10\]
- **Queensland Health Anticoagulant Guideline for Hospitalised Adult Patients, p. 21:**
  - "If the patient is admitted on warfarin, an INR must be performed within 24 hours of admission to guide further dosing decisions".\[19\]
  - The Marevan and Coumadin brands "are not interchangeable".\[19\]
- **Queensland Health Guideline for Warfarin Management in the Community:** patients use a warfarin booklet to record INR results and recommended doses. Clinical handover should include "Recent warfarin doses and INR results".\[20\]
- **WACHS South West procedure (2023):**
  - Every history uses "a minimum of TWO reliable sources".\[11\]
  - "Where there is dose ambiguity, document in the comments column 'dose as per patient'".\[11\]
  - Record the brand for "warfarin, insulins".\[11\]

**Not found:** no ACSQHC, SHPA, state policy or Australian anticoagulant guideline I could access says, in those terms, "confirm the current warfarin dose at admission". I could not retrieve the ACSQHC National Medication Management Plan user guide (2021) or the MATCH UP guide. **Present this as a practice norm supported by the SHPA high-risk rule, not as a quoted requirement.**

**Opinion (practice norm):** confirming warfarin at admission is near-universal. Every Australian hospital pharmacist confirms:
- the current dose, from the patient or carer plus the INR booklet, anticoagulation clinic, GP or pathology dosing service;
- the last dose taken;
- the most recent INR;
- the target range;
- the brand;
- the indication.

### 12.2 Finding in the ranked list, or separate task?
**Opinion: a separate task.** Reasons:
- It carries no discrepancy. Ranking it among discrepancies mixes "something is wrong" with "something must be checked", which is exactly the alarm-fatigue pattern you are trying to avoid.
- It is predictable (every warfarin patient), so pharmacists will learn to skip it if it sits in the findings list. A checklist item they tick off is how they already work (the NMMP "medication history checklist", the warfarin sections on the NIMC).

**Recommended behaviour:**
- Task text: "Confirm current warfarin dose, last dose date, last INR, brand." Automatically attach the rows showing the dispensed strength and the GP directions.
- Closing the task requires the pharmacist to enter the confirmed dose and its source. The detector then compares the chart against that confirmed dose and raises a normal dose finding if they differ.
- If the sources visibly disagree before confirmation, raise both the task and a "conflict: confirm" finding.
- Never auto-resolve to one source. This keeps DATA_SPEC §9.5 intact.

### 12.3 Scope: all insulins, and other titrated or tapered regimens
- **Insulin: include all insulins in the detector**, not just glargine.
  - APINCH covers "all insulins".\[16\]
  - Basal, bolus (aspart, lispro, glulisine) and premixed doses are all titrated without new scripts, and pens are dispensed by the pack, not by the unit.
  - Use one task per patient listing each insulin, with units per dose and timing.
- **DOACs: exclude from dose-unconfirmable.**
  - They are fixed-dose: a new strength needs a new script, so dispensing records do see the change.
  - Handle DOAC errors (wrong dose for renal function; bd vs daily for apixaban or dabigatran) through the normal dose and frequency rules, with high severity.
- **Methotrexate: include, as a weekly-day task.**
  - The same 2.5 mg or 10 mg tablets are dispensed while the number taken per week changes, and the catastrophic error is weekly versus daily.
  - Task: "confirm weekly dose and day of week".
- **Levothyroxine: include only when the directions are non-standard** (alternating doses, "1.5 tablets", "as directed"). Otherwise a strength change usually means a new script.
- **Opioid tapers: include when a taper is documented** (prior discharge summary, GP letter, patient report) or when the directions are "as directed" or "reducing".
- **Others worth flagging:**
  - hydrocortisone and other corticosteroids on sick-day or reducing regimens;
  - furosemide with weight-based self-adjustment;
  - any medicine where the GP directions read "as directed" or the dispensing directions are missing.
- **Rule of thumb (opinion):** trigger on "dose can change without a new strength being dispensed" plus a high-risk class, rather than on a fixed drug list.

### 12.4 Prednisolone: "confirm which step of the taper"?
**Opinion: yes, but the task should ask for four things:**
1. the current daily dose;
2. the date the current step started;
3. the planned schedule (next step and end date);
4. whether it is long-term maintenance.

**Where the taper started matters for where you look, not for whether you ask:**
- **Hospital-initiated taper (prior discharge):** the discharge summary holds the schedule. Compute the expected step for today's date and show it as the hypothesis to confirm. Caveat: Elliott et al. (Pharmacy 2019;8(1):2) found that before a pharmacist intervention, 43% of patients had one or more clinically significant discrepancies in their discharge medication list, so treat the schedule only as a hypothesis.\[21\]
- **GP- or specialist-initiated taper:** the schedule usually lives only in the patient's memory or a GP letter, so the patient interview is the primary source.

**Other points:**
- **Severity cue (opinion):** a course longer than about three weeks implies possible HPA suppression. Leaving prednisolone off the chart is then high severity, whatever the step.
- Long-term fixed low-dose prednisolone (e.g. 5 mg daily) with consistent dispensing directions can carry a lower-priority version of the task.

---

## 13. GP lists it as active, everything else says stopped: is charting it a commission?

**Verdict: partially agree.**
- The weighted vote with a "conflict: ask patient" fallback is sound.
- Change the weights so the patient's "I stopped it" outranks an active GP listing.
- Make supply-lapse evidence asymmetric.
- Never raise commission on a lapse alone.
- Correct the citation behind the GP prior.

### 13.1 Which source does a pharmacist believe, and is there published evidence on relative reliability?
**Cited evidence (definitional):** the BPMH is about actual use, not the prescriber's record.
- WHO High 5s SOP, Step 2, p. 11: the BPMH "is a 'snapshot' of the patient's actual medication use, even though it may be different from what was prescribed".\[4\]
- SHPA Chapter 1, p. S7: the history records medicines "actually taken by the patient in the period before admission ... and recently ceased or changed medicines".\[2\]\[3\]

**Cited evidence (source reliability, Australian):**
- **Boyce 2013:** of 48 older patients admitted via a regional ED, 75% had one or more discrepancies in their GP medication list, and "almost half of the discrepancies were related to non-current medications being recorded".\[7\]
- **Chen 2018** (455 ED patients, Melbourne): median discrepancies per patient for regular medicines were:

  | Source | Median discrepancies per patient |
  |---|---|
  | Residential care facility chart | 0 |
  | DAA contents | 2.0 |
  | Patient's medication list | 2.5 |
  | DAA label | 3.0 |
  | Community pharmacy history | 3.0 |
  | GP letter | 3.0 |
  | Patient's own medicines | 4.0 |

  Omissions made up 55.6% of discrepancies.\[6\]\[22\]
- **Gonski PN, Slathers GM, Freiman JS, Smith T** (Sutherland Hospital), "A Critical Review of Admission and Discharge Medications in an Elderly Australian Population", Drugs Aging 1993;3:358 to 362.\[23\] Hospital doctor and GP lists were the same in only 37% of cases.\[24\]

**Gap:** no Australian study reports source reliability separately for "existence" (is the medicine current) versus dose attributes. Your per-attribute weights are therefore model assumptions.

**Opinion (practice norm):**
- With the GP list "active", no dispensing for months and the patient saying "I stopped", a pharmacist records the medicine as not current, notes "patient reports ceased [when, why]", and checks whether the GP stopped it or the patient self-ceased.
- Charting it is a commission. If the team wants it restarted, it is instead an undocumented intentional discrepancy under High 5s.
- Add a subtype, "patient-ceased, prescriber may be unaware", because the action differs from "GP list out of date": tell the team, and decide whether to restart.

### 13.2 Are ~0.60 (GP list) and ~0.85 (dispensing) defensible?
**Important correction (cited):** Elliott 2023's 16.9% is not a GP-list figure.
- It is the commission-error rate in medication histories built from a cloud-based prescription exchange (MedView) repository: "Commission errors (medications in PES-derived histories that were not current) affected 224 (16.9%) of 1323 medications" in 154 patients (median age 76).\[6\]
- The same study found omissions of 33.3% of current medicines and dose-regimen errors in 25.1%.\[6\]
- Re-anchor or re-label the prior.

**For GP lists:**
- The best Australian anchors I found are Boyce 2013 (non-current medicines are the largest single type of GP-list discrepancy) and Chen 2018 (GP letter, median 3 discrepancies per patient).\[6\]
- A further Australian multisite study (2008 to 2009), cited in the 2019 regional ED study of GP referrals (PMC6956283), reported that "87% of GP referrals had one or more discrepancies in the patients' regular medications and 62% had one or more regular medication discrepancies of moderate to high significance"\[25\] (secondary citation, not verified against the original).
- None of these gives a positive predictive value for "listed active = currently taken". 0.60 is a plausible assumption, not a sourced figure; say so in the code.

**For dispensing (0.85), the evidence argues for asymmetry:**
- Recent dispensing is good evidence that the medicine exists in the patient's regimen.
- Absence of dispensing is weaker evidence:
  - Elliott 2023 attributes omissions in prescription-exchange histories to medicines "obtained from alternative source" and to prescribers or pharmacies not using eRx Script Exchange.\[26\]
  - Patients also use multiple pharmacies, hospital or specialist supply, private scripts, samples and stockpiles.
  - DAA patients may be packed by another pharmacy.
- **Recommendation:**
  - Weight "recent supply present" at about 0.85.
  - Weight "supply lapsed" lower (opinion: 0.6 to 0.7).
  - Count a lapse only if it exceeds the days' supply implied by quantity and directions, plus a grace period.
  - Count a lapse only when the record covers the patient's usual pharmacy.

**Patient "no, I stopped" (0.65) looks too low** compared with an active GP listing, given that the BPMH is by definition about actual use. Opinion:
- Raise it to rank above the GP list (around 0.8).
- Discount it for cognitive impairment, or when the patient does not manage their own medicines (the SHPA p. S10 triggers).

### 13.3 Is a lapsed supply alone enough to flag commission?
**Opinion: no. A lapse alone should only ever produce "conflict: confirm".** Reasons:
- The asymmetry described in 13.2.
- SHPA requires confirmation from a further source when a reliable history cannot be obtained from the patient.\[2\]\[3\]
- A false commission flag invites the team to cease a medicine the patient is actually taking. That creates an omission error, the most common and often harmful type (Chen 2018 and the High 5s SOP).\[4\]

**Exception (opinion):** if the GP list itself is older than the lapse and the drug is a short course (antibiotic, short steroid course), a low-severity "probably completed course" note is reasonable.

### 13.4 Is "unsure" no evidence, or does it mean "still taking"?
**Cited evidence: none found.** I found no Australian or international study measuring what an "unsure" answer predicts in older patients.

**Opinion:**
- Treat "unsure" as no evidence about whether the medicine is current.
- Do not treat it as neutral for the process: it should trigger a task to check the patient's own medicines, DAA contents or carer. Chen 2018 shows DAA contents (median 2.0 discrepancies) are more accurate than patient lists or GP letters, and residential care charts are the most accurate (median 0).\[6\]
- In practice, "unsure" from an older patient more often means "I don't know it by that name" than "I stopped". Prompt for brand, tablet appearance and indication before scoring.

---

## 14. Should the admission chart count as evidence in the BPMH?

**Verdict: agree with excluding it from the vote; partially disagree with the chart-versus-GP default.**
- Keep the chart visible but without a vote.
- When only the chart and one GP list exist, show a finding marked "BPMH single-source, unverified", not a "conflict".

### 14.1 Is the BPMH independent of the admission orders? Definitions
- **WHO High 5s SOP (2014):**
  - Step 1, p. 10: "A Best Possible Medication History (BPMH) is a medication history obtained by a clinician which includes a thorough history of all regular medication use (prescribed and non-prescribed), using a number of different sources of information."\[4\]
  - Step 3, p. 11: "In both models, reconciliation takes place between the BPMH and the admission orders, discrepancies are identified and resolved." In the retroactive model, "the BPMH is created and compared against the admission medication orders retroactively."\[4\]
  - Appendix B (p. 30), retroactive flow chart: "Retain BPMH separate from MAR".\[4\]
- **SHPA Chapter 1 (2013), p. S6:** medication reconciliation is "the standardised process of obtaining a patient's best possible medication history and comparing it to presentation, transfer or discharge medication orders".\[2\]\[3\]
- **NSQHS Action 4.06** (quoted above) frames the orders as the thing reviewed "against" the BPMH.\[1\]
- **NSW CEC** describes the same four steps ("Collect", "Confirm", "Compare the BPMH against prescribed medicines").\[27\]

**Conclusion (cited):** all of these define the BPMH as a pre-admission account that is compared against the orders. Letting the chart vote makes the comparison circular. Your 2.5 mg vs 5 mg example is exactly the failure this design prevents.

### 14.2 When are admission orders legitimately a BPMH source?
**Cited nuance:** SHPA Table 1.1 (p. S7) lists "current medication chart/administration records" among the sources for compiling the history, alongside "transfer information from another health service organisation, e.g. nursing home, hospital, hostel".\[2\] In context this means charts from the previous setting (e.g. an inter-hospital transfer, or the ED chart for a ward transfer), not the orders being reconciled.

**Opinion:** the admission chart itself should never vote. Instead, model the documents the chart was written from:
- **A medication list the patient brought in, or the patient's own medicines:** add these as their own source rows ("patient list", "POMs"), each with its own weight.
- **Residential aged care facility medication chart:** a pre-admission source, and the most accurate one in Chen 2018 (median 0 discrepancies). Give it a high weight for both existence and dose. The High 5s SOP Appendix A lists the "referring health care facility" as a BPMH input.\[4\]\[6\]
- **Transfer from another hospital:** that hospital's current chart is a legitimate source for the receiving hospital's reconciliation.

### 14.3 Prior discharge summary as a source, and how to weight it against a later GP list
**Cited:**
- High 5s Step 2 lists "previous patient health records" as verification sources.\[4\]
- SHPA Table 1.1 lists "previous prescriptions (community pharmacy, discharge/outpatient)" and "electronic records, e.g. pharmacy dispensing system, discharge medication records".\[2\]

**Cited caution: discharge summaries are error-prone.**
- Elliott et al. 2019 (Pharmacy 8(1):2, Austin Health) found that before ward pharmacists became involved, 43% of patients had one or more clinically significant discrepancies in their discharge medication list.\[21\]
- Elliott RA, Angley M, Criddle DT, Emadi F, Liu S, Penm J, "Achieving safe medication management during transitions of care from hospital: time for a stewardship approach" (Aust Prescr 2024;47:106 to 8, doi:10.18773/austprescr.2024.034), notes that discharge summaries "continue to have inaccurate medication lists and inadequate explanation of medication changes".\[28\]

**Opinion (weighting):**
- Treat a discharge summary mainly as a dated record of events (started, stopped, changed, taper schedule), not as a standing list.
- A GP list dated after the discharge should win on currency for the medicines it explicitly addresses.
- If a later GP list still shows a medicine the discharge summary ceased, raise "conflict: ask patient". GP lists retain ceased medicines (Boyce 2013), so do not let recency alone resolve it.\[7\]
- Decay the discharge summary's weight with time since discharge (over months, not weeks), and faster for tapers and short courses.

### 14.4 Only the chart and GP list are available and they disagree: conflict or finding?
**Opinion: show a finding, not a conflict, with an explicit "unverified BPMH" flag.**
- A "conflict" means BPMH sources disagree. Here there is only one BPMH source, so calling it a conflict quietly gives the chart a vote, which contradicts 14.1.
- The comparison is exactly what NSQHS Action 4.06 asks for. The uncertainty lies in the BPMH, which SHPA (p. S10) and WACHS ("minimum of TWO reliable sources") say must be confirmed.\[1\]\[2\]\[3\]\[11\]
- Rank it with a confidence discount based on the GP list's age, and attach a task: "obtain a second source (patient, dispensing, MHR) before acting".
- This keeps the error visible (the case where suppressing too much causes harm) while signalling that it may be an artefact of the GP list (the case where flagging too much causes fatigue).

---

## Caveats
- I could not retrieve the full text of the ACSQHC National Medication Management Plan user guide (2021), the MATCH UP medicines guide, or the NSW CEC anticoagulant standard. Wording from those comes from search snippets or was not used.
- The Pippins 2008 coding wording comes from the publisher's indexed appendix text; the full article is paywalled.
- All numeric weights (0.60, 0.65, 0.85 and my suggested revisions) are model assumptions. No Australian study reports source reliability by attribute. Calibrate against a local audit of pharmacist-confirmed BPMHs.
- "Expert opinion" here is my judgement as a consultant hospital pharmacist describing common Australian practice. Local policies vary by state and health service.

## Summary of recommended rule changes

| Q | Current rule | Recommended change | Basis |
|---|---|---|---|
| 11 | Same strength, different frequency → frequency; equal daily dose never flagged | Keep label; add "dose and frequency" combined label; compute severity from daily-dose ratio plus drug risk; flag equal-daily-dose split changes only for `split_sensitive` drugs; fix docstring | Pippins 2008; Tam 2005; no Australian convention (opinion) |
| 12 | `dose_unconfirmable` finding for every warfarin, glargine, prednisolone patient | Emit as a verification task in a separate lane; promote to finding only if confirmation fails or differs from chart; include all insulins, methotrexate (weekly day), documented opioid tapers, non-standard levothyroxine; exclude DOACs | SHPA 2013 p. S10; APINCH; Qld anticoagulant guideline; NSW CEC HRM Standards (practice norm) |
| 12 | Prednisolone task | Ask current dose, step start date, schedule, long-term status; use discharge summary schedule as hypothesis if hospital-initiated | Elliott 2019 discharge summary accuracy (opinion) |
| 13 | Weights: pharmacy 0.85, patient 0.65, GP 0.60 | Patient "stopped" above GP (~0.8); supply asymmetric (present ~0.85, lapsed ~0.6 to 0.7, days'-supply aware); re-label GP prior as assumption (Elliott 16.9% is PES, not GP) | Elliott 2023; Boyce 2013; Chen 2018; High 5s "actual use" definition |
| 13 | Lapse alone can resolve to commission | Lapse alone → "conflict: confirm" only | Elliott 2023 omission causes; SHPA p. S10 (opinion) |
| 13 | "Unsure" = no evidence | Keep as no evidence, but trigger POMs/DAA/carer check task | No published evidence; Chen 2018 DAA accuracy (opinion) |
| 14 | Chart excluded from vote | Keep; add patient list, POMs and RACF chart as separate source rows (RACF chart high weight) | High 5s SOP pp. 10 to 12, Appendix B; SHPA p. S6 to S7; Chen 2018 |
| 14 | Discharge summary as source | Treat as dated events; later GP list wins on currency except where it retains a medicine ceased at discharge (→ conflict) | High 5s Step 2; SHPA Table 1.1; Elliott 2019 (opinion) |
| 14 | Chart vs GP only → conflict | Show as finding flagged "BPMH single-source, unverified", age-discounted, with second-source task | NSQHS 4.06; SHPA p. S10; WACHS two-source rule (opinion) |

## Sources

1. [Medication Safety Standard](https://www.safetyandquality.gov.au/national-standards/nsqhs-standards/medication-safety-standard)
2. <https://healthcarefunding.specialcommission.nsw.gov.au/assets/Uploads/publications/Exhibits-134/EXHIBIT-L_TAB-L.013.001_SCI.0011.0449.0001.PDF>
3. [S6 Journal of Pharmacy Practice and Research Volume 43, No. 2 (suppl), 2013.](https://www.adpha.au/publicassets/4adc0a0d-eb77-ec11-80de-005056be03d0/Chapter%201%20-%20Medication%20Reconciliation.pdf)
4. [Standard Operating Protocol for Medication Reconciliation](https://cdn.who.int/media/docs/default-source/patient-safety/high5s/h5s-sop.pdf?sfvrsn=594d8e49_4)
5. [Amazonaws](https://sdiopr.s3.ap-south-1.amazonaws.com/doc/Revised-ms_AJMAH_86728_v1.pdf)
6. mcp\_\_PubMed\_\_get\_article\_metadata
7. [Audit of General Practitioner Medication Lists for Older Patients at a Regional Hospital - Boyce - 2013 - Journal of Pharmacy Practice and Research - Wiley Online Library](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.2055-2335.2013.tb00230.x)
8. [unintended medication discrepancies time hospital admission](https://psnet.ahrq.gov/issue/unintended-medication-discrepancies-time-hospital-admission)
9. [Classifying and Predicting Errors of Inpatient Medication Reconciliation - Journal of General Internal Medicine](https://link.springer.com/article/10.1007/s11606-008-0687-9)
10. [High-Risk Medicine Standards Printable Standard Version 1.0, October 2025](https://www.cec.health.nsw.gov.au/__data/assets/pdf_file/0004/1024735/All-High-Risk-Medicines-Standards-Printable-version.pdf)
11. <https://www.wacountry.health.wa.gov.au/~/media/WACHS/Documents/About-us/Policies/Medication-Reconciliation---Completing-the-Medication-History-Management-Plan-Procedure---South-West.pdf?thn=0>
12. [Status Report Medication without harm WHO Global Patient Safety Challenge](https://www.safetyandquality.gov.au/sites/default/files/resources/attachments/status_report_-_medication_without_harm_who_global_patient_safety_challenge_-_australias_response.pdf)
13. [High Risk Medicines - NSW Therapeutic Advisory Group - NSW Therapeutic Advisory Group](https://www.nswtag.org.au/high-risk-medicines/)
14. [510 JAMC • 30 AOÛT 2005; 173 (5) © 2005 CMA Media Inc. or its licensors Review](https://www.cmaj.ca/content/cmaj/173/5/510.full.pdf)
15. [Can nonclinicians classify medication discrepancies as accurately as clinical pharmacists? A validation study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9508616/)
16. [High risk medicines](https://www.sahealth.sa.gov.au/wps/wcm/connect/public+content/sa+health+internet/clinical+resources/clinical+programs+and+practice+guidelines/medicines+and+drugs/high+risk+medicines/high+risk+medicines)
17. [Page 1 of 3 Safety Notice 005/23 Issue date 6 March 2023 Distributed to:](https://www.health.nsw.gov.au/sabs/Documents/2023-sn-005.pdf)
18. [Medication Handling - NSW Health](https://www1.health.nsw.gov.au/pds/ActivePDSDocuments/PD2022_032.pdf)
19. [Anticoagulant Guideline for Hospitalised Adult Patients](https://www.health.qld.gov.au/__data/assets/pdf_file/0015/1152213/statewide-anticoagulant-guideline.pdf)
20. [Guideline for Warfarin Management in the Community - Last minor update](https://www.health.qld.gov.au/__data/assets/pdf_file/0025/443806/warfarin-guideline.pdf)
21. [Pharmacy (Dec 2019)](https://doaj.org/article/51c5ffff5fa74217a12edf0ce1d55b81)
22. [Accuracy of medication information sources compared to the best possible medication history for patients presenting to the emergency department - Chen - 2018 - Emergency Medicine Australasia - Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1111/1742-6723.12965)
23. [Associate Professor Peter Gonski](https://www.unsw.edu.au/staff/peter-gonski)
24. [A Critical Review of Admission and Discharge Medications in an Elderly Australian Population](https://link.springer.com/article/10.2165/00002512-199303040-00006)
25. [Medication Error Rate in Transition of Care: General Practitioner (GP) Referrals to a Regional Emergency Department](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6956283/)
26. [Accuracy of medication histories derived from an Australian cloud‐based repository of prescribed and dispensed medication records - Elliott - 2023 - Internal Medicine Journal - Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1111/imj.15857)
27. [Medication reconciliation](https://cec.health.nsw.gov.au/therapeutics-safety/medicines-improvement/continuity/reconciliation)
28. [Achieving safe medication management during transitions of care from hospital: time for a stewardship approach - Australian Prescriber](https://australianprescriber.tg.org.au/articles/achieving-safe-medication-management-during-transitions-of-care-from-hospital-time-for-a-stewardship-approach.html)
