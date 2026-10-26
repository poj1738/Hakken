# Demo script: 3 minutes

The video walkthrough, following PLAN §8. **External facts come only from
`docs/PITCH_CLAIMS.md`, word for word.** Product statements describe only what is on
screen, and every screen below was produced by `web/scripts/rehearse-demo.cjs`
against the API in `SAMPLE_MODE` on 26 Oct 2026.

**Patients** (`input_examples/README.md`):

| Patient | Input | Role in the demo |
|---|---|---|
| MRN0000015 (Nichoolas Walker) | `example_1` | Identity review, then a high-alert dose discrepancy |
| MRN0000089 (Dorothy Nguyen) | `example_2` | Discrepancies and the medication history |
| MRN0000003 → MRN0000007 | `example_4` → `example_5` | The learning demo |

## Before recording

1. **Use a fresh API.** The server remembers identity decisions and feedback. A
   second take on a used server skips the identity review, and confidence starts
   already lowered.
   ```bash
   SAMPLE_MODE=true STATE_DIR=$(mktemp -d) python3 run.py serve                  # repo root
   VITE_API_MODE=live VITE_API_URL=http://localhost:8000 npx vite --port 5174    # in web/
   ```
   For a live take, drop `SAMPLE_MODE` and use your own `.env` (see the next section).
2. **Rehearse the click path:** `node scripts/rehearse-demo.cjs <out-dir>` in `web/`
   (usage is at the top of the file). It prints what each scene showed and fails on
   any page or HTTP error.
3. **Scorecard:** `make lexicon && make synth` once (gitignored data), then
   `python3 scripts/eval.py --split heldout`. Re-run it on the day: the numbers move
   with the code, so read them off the screen, not from this file.
4. Browser at 1440 × 900, zoom 100%. Close the cell panel between scenes.

## Sample mode or live

Scenes 1, 3 and 4 look the same in either mode. **These need live Nightshift**
(sample mode makes no model call):

| On screen | Sample mode | Live |
|---|---|---|
| Header **Model** | "Not yet called" | The Nemotron that answered (`last_routed_model`) |
| Processing Log → Technical details, "Answered by" | `offline-heuristic` | `nvidia/nemotron-…` per step |
| Summary and finding explanations | Grounded template text | Written by the Writer (Nemotron), checked by Q3 |
| Caveat strip | "Sample mode: … no model was called." | Absent unless a step degraded |
| A **Withheld** step in the Processing Log (verifier blocked a claim) | Never appears: there is no model text to block | Appears only if the model writes an unsupported claim. **Not guaranteed on any take** |
| Run time | About 2 s | 30 s to 9 min (Arnav, 26 Oct): cut or speed up the wait |

PLAN §8's "Nemotron model ID in the pill" is therefore **live only**. Record scene 2
live if you can, or a live run of MRN0000089 plus a cutaway to the header.

---

## Scene 0 · 0:00–0:30 · The problem

**Screen:** MedTrace with no patient run yet: navy header with the "Synthetic data ·
Not for clinical use" badge, and the empty state.
**Clicks:** none.

> "In a landmark Canadian study, more than half of older inpatients had at least one
> unintended medication discrepancy at admission. Medication-related problems cause
> about 250,000 hospital admissions in Australia each year, at a cost of $1.4 billion
> — and about half of that harm is preventable.
>
> Reconciling a patient's medicines means finding them in four places that don't talk
> to each other: the admission chart, the GP, the pharmacy and the patient. MedTrace
> does that search and produces a pre-populated medication history for clinician
> verification."

## Scene 1 · 0:30–1:15 · Who is this patient? (MRN0000015)

**Clicks:**
1. Select patient → "Nichoolas Walker — MRN0000015".
2. **Run reconciliation**. The Processing Log fills in; the run pauses.
3. Point at the identity card: the interview record "Nicholas Walker", **84% match**.
   Given name is a partial match (amber), family name and date of birth agree (green).
4. Point at **Withheld from automatic linkage**: "This record carries no IHI, and it
   falls in a group of matching records that includes Malcolm Walker (DOB 1965-06-10,
   admission chart MRN0000159), who carries a different IHI — confirm it is this
   patient."
5. Click **Same patient**. The reconciliation resumes.
6. On the Discrepancies tab, point at **Warfarin · Dose cannot be confirmed ·
   APINCHS · H** and its **Verify before acting** callout.
7. Optional: Processing Log → **Technical details** shows the World Model operations
   (`world_model.upsert+relate`, `world_model.relate`, `world_model.neighbors`).

**Must be visible:** the 84% match, the withheld reason naming Malcolm Walker, the
Same patient / Different patients buttons, then summary cards (Sources located 4 of 4;
5 discrepancies, 3 requiring pharmacist review), and the warfarin and insulin aspart
discrepancies with APINCHS pills.

> "The interview spells the name differently, and another patient, Malcolm Walker,
> has a birth date four days away and a different IHI. A wrong link would mix two
> people's medicines, so MedTrace withholds it and asks. One click confirms it, and
> the decision is recorded for future runs.
>
> High-alert medicines come first. Warfarin's dose can't be confirmed from the
> records, so the screen says to verify before acting, never to stop it."

## Scene 2 · 1:15–2:15 · What is the patient actually taking? (MRN0000089)

**Clicks:**
1. Select "Dorothy Nguyen — MRN0000089" → **Run reconciliation**. No review is needed.
2. Discrepancies tab: point at **Oxycodone/Naloxone · Therapeutic duplication ·
   APINCHS · N**, **Gliclazide · Omission · APINCHS · Ext** and **Dapagliflozin ·
   Possibly discontinued**. Hover a record chip under "Supporting records" to show
   its original text and SQL template.
3. **Medication History** tab: the four sources side by side. Point at the legend:
   **No record available** (hatched violet) is not **Not listed** (grey).
4. Click Dapagliflozin's **Patient interview** cell. The panel shows the source
   record `PAT-000725`, "Forxiga · one a day · unsure", **SQL template Q2**.
5. Point at Turmeric's Pharmacy cell: **No record**.
6. **Actions Required** tab: the checklist (8 actions), each naming the discrepancy it
   came from.

**Must be visible:** the three discrepancies with priority and APINCHS pills;
"Unresolved — verify with patient" on dapagliflozin's row; the provenance panel with
record ID and SQL template; the 8 actions.

> "Every line traces back to a record. The duplication is flagged because the
> combination product is broken into its ingredients; dapagliflozin is still on the
> GP list, but the sources disagree, so it is left for the pharmacist rather than
> guessed.
>
> Where a source can't be seen, it says 'No record available', which is not 'not
> taking'. That difference is how these tools tell a patient to stop a medicine they
> still take.
>
> The two-source rule is consistent with NSQHS Actions 4.05 and 4.06, and ACSQHC
> guidance that a BPMH needs at least two sources."

## Scene 3 · 2:15–2:50 · It learns from the pharmacist (MRN0000003 → MRN0000007)

**Clicks:**
1. Select "Christine O'Brien — MRN0000003" → **Run reconciliation**.
2. **Medication History**: Candesartan reads **Unresolved — verify with patient ·
   Daily dose: GP 16.0 vs Pharmacy 8.0**. The Record Sources card says the GP list is
   about 12 months old.
3. Click Candesartan's **GP** cell → **Mark GP daily dose as outdated**. The panel
   shows "Marked outdated · confidence 0.70 → 0.50".
4. **Source Confidence** tab: the box at the top reads "GP · Daily dose: 0.70 → 0.50
   (−0.20) — Candesartan daily dose rejected as source outdated".
5. Select "MRN0000007" → **Run reconciliation**. Discrepancies: **Rosuvastatin · Dose
   discrepancy**.
6. **Medication History**: Rosuvastatin resolves to **Daily dose 10**, sources
   "Pharmacy, GP, Patient interview"; the GP cell reads **Disagrees · 20.0**.
7. **Source Confidence**: GP daily dose **0.50**, "Earlier feedback: 0.70 → 0.50".

**Must be visible:** the 0.70 → 0.50 change, and on the second patient the new
rosuvastatin discrepancy and the resolved dose.

> "The pharmacist marks a year-old GP dose as outdated. Confidence in GP doses drops,
> and on the next patient the same kind of conflict resolves to the pharmacy's
> recent fill, and surfaces a chart error copied from the stale GP list."

**Say it honestly:** this pair is staged in the synthetic data (`input_examples/README.md`)
to show the effect; do not present it as chance.

## Scene 4 · 2:50–3:00 · Measured, not claimed

**Screen:** terminal, `python3 scripts/eval.py --split heldout`.
**Clicks:** none.

> "On held-out synthetic patients, read straight from the scorecard: per-type
> precision and recall, zero false merges, and core APINCHS recall of [read the
> 'core' line]. Synthetic data, not medical advice: a pharmacist confirms every item."

Read the numbers from the screen on the day. At rehearsal (26 Oct): F1 0.96, 0 false
merges across 286 auto-merged records, core APINCHS 30/32, extended 5/5. Quote
**core** APINCHS recall, not the pooled 35/37, anywhere it reads as ACSQHC
compliance (Arpon, HANDOFF 25 Oct).

---

## What doesn't work or looks wrong (rehearsal, 26 Oct)

**Fixed in the UI on this branch**
- Scene 1: the withheld reason read "(DOB 1965-06-10, Admission chart)", because
  the display cleanup replaced the record key `emr:MRN0000159` with the source name.
  It now keeps the MRN: "admission chart MRN0000159".
- Every scene: September displayed as "Sept" (locale); dates are now formatted by
  hand ("8 Sep 2026").
- Scene 2: the cell panel had two adjacent "Technical details" toggles; the
  record-level one is now "Query ID".
- Every scene: the Processing Log footer read "4 model calls via Nightshift" in
  sample mode, contradicting the caveat strip. It now counts only calls whose
  `routed_model` is not `offline-heuristic`: "0 model calls via Nightshift · 4
  agent steps offline".
- Scenes 2–3: the run time read "0.0 s" (sample runs take ~0.03 s); it now reads
  "< 0.1 s". MRN0000015 shows ~1.9 s because the clock includes the identity pause.

**Not UI: needs the API or the data (Arnav)**
- **Scene 2, provenance:** 18 of 36 listed cells on MRN0000089 cite no source record
  (dashed-circle icon). `evidence_index` still holds only rows cited by findings and
  notices (`app/orchestrator.py:506`), not every row behind the grid, as `schemas.py`
  promises. Click a cell **without** the icon on camera.
- **Scene 1, text:** the aspirin/clopidogrel explanation reads "appears more than once
  once combination products are decomposed" (doubled word in the API text).
- **Every scene, Processing Log:** the identity-resolution step reads "…the Zetaris
  adapter sends it (read-only check, Bearer key, X-Org-ID, fresh X-Request-ID)".
  That's developer prose on a judge-facing screen. Scroll past it or ask Arnav to
  reword it.
- **Scenes 2–3:** doses still have no unit ("Daily dose 10", "Daily dose 3990").
- **Scene 4:** PLAN §8 lists "false-cessation 0". `eval.py` prints no such line, so
  don't say it.

**PLAN §8 beats these patients cannot show**
- "Lipitor vs atorvastatin NOT flagged": the brand-vs-generic suppression has no
  visible trace on screen for these patients.
- "Coversyl Plus + perindopril duplication": MRN0000089 shows the same mechanism
  (oxycodone/naloxone); MRN0000001 has perindopril/indapamide but no duplication finding.
- "'GP not found' shown as UNKNOWN": MRN0000089 shows one "No record" cell (Turmeric,
  pharmacy). The full case is MRN0000013 (`example_3`: only two of four sources). Add
  it as a 10-second cutaway if time allows.
- "The verifier blocked a claim": live only, and not guaranteed (table above).
