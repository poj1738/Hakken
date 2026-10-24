# Pitch claims: what we may say, and the exact wording

**Written for whoever writes the README, the slides and the video script.**

Every number we say out loud is checkable by a judge in about a minute. These
four claims were put to an outside reviewer on 24 October 2026 (brief 9, in
`docs/research/`). Two were right but loosely phrased, one was **wrong as we had
it**, and the framing of our own output needed changing.

Use the sentence in **Say this**. It is the version that survives being looked up.

---

## 1. More than half of older inpatients have a discrepancy

**Say this:** "In a landmark Canadian study, more than half of older inpatients
had at least one unintended medication discrepancy at admission."

**Don't say:** "53.6% of admitted older patients…" as a general fact. It is one
Toronto hospital, 151 patients, mean age 77, all on four or more medicines.

- Cornish et al. 2005, *Arch Intern Med*, PMID 15738372: 81/151 = 53.6%
  (95% CI 45.7–61.6). Omissions were 46.4% of discrepancies; 38.6% had potential
  for moderate or severe harm.

**Australian figures worth adding** (a judge will want local evidence):

- ACSQHC: "Between 10% and 67% of medication histories have at least one error,
  and up to 33% of these errors have the potential to cause patient harm."
- WHO High 5s Australian implementation, 10 hospitals, 42,003 records of patients
  ≥65 admitted via ED: unintentional discrepancies fell from 15.2% to 11.1% after
  reconciliation (Stark et al., PMID 31176651). **The abstract does not say
  whether the denominator is patients or medicines**, so do not quote it as
  "% of patients".

## 2. ~250,000 medicine-related hospital admissions a year in Australia

**Say this:** "Medication-related problems cause about 250,000 hospital
admissions in Australia each year, at a cost of $1.4 billion — and about half of
that harm is preventable."

**Don't say:** or imply that reconciliation discrepancies cause all 250,000. The
figure counts admissions from medication-related problems of every kind.

- PSA, *Medicine Safety: Take Care* (January 2019). Also 400,000 additional ED
  presentations. No newer national estimate was found; PSA still cited it in 2022.

## 3. The two-source requirement — **this one was wrong**

We had: "Standard 4, Actions 4.5 and 4.6, require at least two independent
sources." The Actions themselves say no such thing, and the numbering is 4.05 /
4.06.

**Say this:** "consistent with NSQHS Actions 4.05 and 4.06, and ACSQHC guidance
that a BPMH needs at least two sources."

- **Action 4.05** — clinicians take a best possible medication history, documented
  on presentation or as early as possible.
- **Action 4.06** — clinicians review current medication orders against the BPMH
  and reconcile discrepancies on presentation and at transitions of care.
- The two-source rule is in ACSQHC's *implementation guidance* for the NSQHS
  Standards (2nd ed.), Standard 4, "Medication reconciliation": "At least two
  sources of information are needed to obtain and then confirm the patient's
  BPMH."  The WHO High 5s SOP says information "should be verified with more than
  one" source.
- Keep the word **independent**; the patient interview counts as one of the two.
- ACSQHC is running a third-edition engagement hub. Whether a third edition is
  published was **not confirmed** — check before submission.

## 4. Call the output a draft, not a BPMH

BPMH is the right Australian term, but a BPMH requires a clinician and active
patient or carer involvement. Software cannot produce one.

**Say this:** "a pre-populated medication history for clinician verification", or
"a draft for BPMH".

**Don't say:** "MedTrace produces a BPMH."

This is not just wording — it is the same claim the human-review gate makes in the
product, so the pitch and the code agree.

---

## Worth citing if there is room

- ACSQHC, *Medication without harm — WHO Global Patient Safety Challenge:
  Australia's response* (January 2020): over four in ten people aged 50+ take five
  or more medicines; over one in ten take ten or more. Status report June 2024.
- Medicine safety as Australia's 10th National Health Priority Area (COAG, 2019).
- *Australian Prescriber* 2024;47:106-8 (doi 10.18773/austprescr.2024.034) on
  discharge-summary inaccuracy, My Health Record and the pharmacist shared
  medicines list.
- AIHW, *Polypharmacy in Australia in 2025*.

## The rule behind all of this

Rule 6 in `CLAUDE.md` is about outputs, but it applies to the pitch too: claim
only what the source shows. A judge who checks one number and finds it overstated
will not check the second one — they will discount the whole entry.
