# Decisions

Decision, why, date. Newest first.

Anything discovered by observation rather than from a published contract is marked
**[live]** with **whose machine and when**, so a later reader can tell evidence from
assumption — and can tell a team-wide fact from one person's setup. A `[live]` finding
is one data point: it may not reproduce on your machine, on a different runtime build,
or after a provider update. Re-verify before depending on it, and add your own
observation rather than editing someone else's.

---

## 2026-10-25 — Track 1, recorded **[team decision, 25 Oct]**

The team chose **Track 1**. The product is MedTrace, as already built. Recorded in
`metadata.json`, `README.md`, `TODO.md` and `PROGRESS.md`, which still said "track not
chosen". The README status sections, which still claimed only a preflight script and a
config layer existed, were rewritten to say what is built and measured (data,
Zetaris registration, domain pack, scorecard) and what is not (adapters, agent loop,
engines, API, UI). The official Track 1 title is not written anywhere in the repo, so
it is recorded as "Track 1" rather than guessed.

## 2026-10-25 — The learning demo is staged, and says so **[measured, 25 Oct]**

**Problem.** PLAN's 2:15 beat ("reject a GP dose as outdated, then patient B
resolves differently") had no patient B. I lowered GP `daily_dose` by one
`source_outdated` rejection (−0.20, PLAN 5.7) and re-fused all 200 patients:
3 changed their resolved dose (P0012, P0116, P0134), none in the replay set,
and none gained or lost a finding. The beat would have shown nothing.

**Decision.** Stage one pair, deterministically, on two replay-set patients
that had no planted findings (`LEARNING_PAIR` in the generator): P0003 teaches,
P0007 learns. The shape: a GP list 380 days old still carrying the pre-reduction
dose, against a pharmacy fill at the current dose six days ago. At the priors,
GP 0.70 × e^(−380/730) ≈ 0.42 against pharmacy 0.55 × e^(−6/180) ≈ 0.53, a
margin of 0.12, so the dose abstains. After one rejection GP falls to about 0.30,
the margin is 0.28, and the pharmacy wins. P0007's chart copied the stale GP dose,
so resolving it surfaces a real chart error.

**Why staged, not searched for or tuned.** Changing trust priors or the margin
to make a random patient flip would move every score to serve a demo. Staging
moves no prior, uses no rng, and adds no rows, so every other patient's rows and
ids are byte-identical. It is recorded in the ground truth (`learning_demo`, and
`detail.learning_demo` on P0007's planted dose finding), so nobody can present it
as chance.

**Cost, stated.** Without feedback the detector abstains on P0007's dose, so the
tune scorecard carries one more miss: 145 TP / 17 FP / 5 FN (it was 4), F1 still
0.93. Held-out is untouched (P0003 and P0007 are tune). That miss is the point:
it is what the system cannot see until it learns.

Pinned by `tests/unit/test_learning_demo.py` on the committed replay fixtures,
so it runs in CI and is exactly what `SAMPLE_MODE` replays. Live Zetaris was
re-cached and serves the staged rows (checked by `row_id`, since `make verify`
compares row counts and a value change keeps them).

Also: showcase replay fixtures for P0013, P0015 and P0089 (`SHOWCASE`), five
`input_examples/`, and the Dockerfile now copies `tests/fixtures/medtrace/`.
Without that, `SAMPLE_MODE` in the image had nothing to replay.

## 2026-10-25 — Consultant rulings on the detector applied; population back to 200 **[consultant review + measured, 25 Oct]**

The consultant pharmacist's review of briefs 11–14 is
`docs/research/MedTrace detect.py_ Consultant Pharmacist Review of Medication
Reconciliation Rules 11 to 14.md`. Three of the four rules stood, each with a
change; this entry supersedes the matching points in the entry below.

| Brief | Ruling | What changed |
|---|---|---|
| 11 | Label fine; severity must follow the dose change and the drug | Dose vs frequency judged **per administration** ("2 tablets daily" for 1 is dose). Severity from the daily-dose ratio and APINCHS class. `subtype`, ratios and a plain-English `statement` in `detail`. Equal-daily-dose split changes flagged (low) only for `detect.SPLIT_SENSITIVE` |
| 12 | Confirming a phone-changed dose is a **task**, not a ranked finding | `dose_unconfirmable` fires only on a **visible conflict**. The routine confirmation is `safety.forced_confirm`, emitted by the orchestrator for every current one. All insulins in scope; methotrexate added; DOACs excluded (fixed-dose) |
| 13 | The patient's "I stopped" outranks an active GP list; supply evidence is asymmetric; **a lapse alone is never a commission** | Patient existence prior 0.65 → **0.80**. Lapse weighs 0.75 of a running supply (≈0.64). Lapse-only → a low-severity commission marked `conflict: confirm` with an ask-first task. GP 0.60 relabelled an **assumption**: Elliott 2023's 16.9% is a prescription-exchange rate, not a GP-list one |
| 14 | Excluding the chart from the BPMH is correct | Unchanged. A finding resting on one BPMH source is marked `bpmh_single_source` with a second-source task |

**Ground truth followed the same definitions.** The generator now plants
`dose_unconfirmable` only where the change shows in a rendered row, and treats
insulin aspart as a phone-dose medicine. That is the rule used all day: a planted
finding must be supported by evidence some silo actually contains.

**Population restored to 200** (DATA_SPEC's number). At 40 the largest error
source was invisible: `dose_unconfirmable` was 21 of 32 false positives only once
there were enough patients to see it. **Zetaris costs nothing extra at 200**: Q1
1.99 s, Q2 1.92 s, Q3 2.95 s, the same as at 40, because the tables are cached.

**Scores** (200 patients, simulated review):

| split | precision | recall | F1 | high-risk recall |
|---|---|---|---|---|
| tune | 0.90 | 0.97 | 0.93 | 34/34 |
| **held-out** | **0.95** | **0.95** | **0.95** | **35/37** |
| held-out, after a post-hoc fix | 0.95 | 0.97 | 0.96 | 35/37 |
| held-out, no human review | 0.94 | 0.93 | 0.93 | 35/37 |

The post-hoc row: the first held-out run showed commission recall of 0.53,
because a lapse-only case produced nothing at all, contrary to the consultant's
"conflict: confirm". The fix implements the ruling, but it was *noticed* on
held-out, so the clean figure to quote is 0.95. **DATA_SPEC's 100% high-risk
recall is not met on held-out.** The two misses are commissions (P0123 insulin
aspart, P0174 temazepam). They are recorded here and deliberately not tuned
against; `test_scorecard` pins 35/37 as a regression floor, not as the target.

Also fixed: the interview silo's "Given Family" field was fuzzy-matched whole
against a given name, so a one-letter typo lost a patient's record (P0076).
Linkage at 200: 535 auto-merged, 31 review, 2 lost, 0 false merges.

---

## 2026-10-25 — How the detector decides what is a finding **[built and scored against ground truth, 25 Oct]**

Six decisions made while implementing `fuse`, `detect` and `triage`. Each was
forced by a specific failure on real synthetic patients, and four are out with the
consultant as briefs 11–14 (`docs/RESEARCH_QUESTIONS.md`) — overturn any of them
there, not by editing the code quietly.

**1. The current admission chart does not vote in the BPMH.** The BPMH is the
pre-admission history; the chart is what gets reconciled against it (ACSQHC Action
4.06). With the chart voting, P0002's planted error (chart 2.5 mg, pharmacy 5 mg)
resolved to 2.5 mg — the chart outweighed a six-week-old dispensing — and the error
disappeared. The chart stays visible in the grid; older EMR documents (prior
discharge summaries) are history and do vote. *(Brief 14.)*

**2. Silence counts half, and a commission needs someone to say it stopped.** A
source that is in scope but never mentions a medicine gets `SILENCE_WEIGHT = 0.5`
of the weight of one that says it was stopped, and `commission` requires a positive
assertion — a ceased listing, a patient's "no", a discharge "cease" or a lapsed
regular supply. Counting silence fully made a current GTN spray a commission:
outvoted by a patient and pharmacy that had simply never mentioned it. *(Brief 13.)*

**3. PRN medicines: the pharmacy has no say on existence.** A year-old GTN fill does
not prove current use and no fill does not prove stopping. The PRN signal has to
come from the chart, GP or patient, because dispensing rows carry no directions.

**4. Frequency vs dose is classified by what changed.** Same strength per unit at a
different number of doses a day is `frequency` (clopidogrel charted bd instead of
daily, which doubles the daily dose); anything else is `dose`; an equal total daily
dose is never a finding (brief 8 §2). This matches the generator and overturns the
skeleton docstring, which had said "frequency = same daily dose, different split".
*(Brief 11.)*

**5. `dose_unconfirmable` for every current warfarin, insulin and prednisolone.**
Agreement between sources that cannot see a phone instruction is not confirmation
(DATA_SPEC 9.5). Uses `safety.DOSE_CHANGES_WITHOUT_A_SCRIPT` as the single list,
which includes insulin aspart; the generator plants only glargine, so aspart
currently scores as a false positive (6 of the 12 across both splits). *(Brief 12.)*

**6. Learned acceptance is keyed `(type, atc_class)`**, where `atc_class` is the
first 4 characters of the ATC code (e.g. `C09A`), written by `detect` into every
candidate's `detail["atc_class"]`. Matches `schemas.AcceptanceUpdate`, so the
ranking and the feedback endpoint read one value. Core APINCHS is floored at
`triage.MUST_REVIEW_FLOOR`, above anything a non-high-risk finding can score.

**Also decided:**
- **Identity sends a lookalike's un-identified records to review, not rejection**,
  even when the patient's own IHI is absent from the cluster. Review never merges,
  so false merges stay 0; P0008 had lost three findings to rejection.
- **`eval.py` reports two review modes.** `oracle` simulates a pharmacist confirming
  exactly the true review-band links (the designed workflow); `none` is the system
  alone. Both are reported; neither is presented as the other.
- **Not emitted yet:** `unpropagated_discharge_change` (not planted; the generator
  only now makes discharge actions coherent) and `identity_uncertain` (review-band
  rows are not read until confirmed, so nothing can rest on one).

**Scores** (40 patients, `scripts/eval.py`, simulated review):

| split | precision | recall | F1 | high-risk recall |
|---|---|---|---|---|
| tune | 0.83 | 1.00 | 0.91 | 8/8 |
| **held-out** | **0.83** | **0.94** | **0.88** | 2/2 |
| held-out, no human review | 0.80 | 0.77 | 0.79 | 2/2 |

Held-out is within 0.03 F1 of tune and no change was made by looking at it. The
Wilson intervals are wide — several types have 1–4 instances per split — which is
the population-size decision still open (raise `--patients`).

---

## 2026-10-24 — Research briefs answered, and one of my own bugs manufactured most of a finding **[consultant research + live verification, 24 Oct]**

A consultant worked the five briefs in `docs/RESEARCH_QUESTIONS.md`. Two closed from
public sources, two need a team judgement call, one needs the Department of Health.

### The ATC "disagreements" were mostly my bug

I reported **35 disagreements** between DATA_SPEC and the PBS API and attributed them to
PBS systematically giving a combination the ATC of one component. The consultant
suspected the join instead. They were right about the cause and wrong about the
mechanism — it was not the `atc_priority_pct` tie-break (only 37 of 6,857 codes have
multiple ATC rows, and that logic was already correct). It was `match_item`:

> When a combination's name did not match a PBS `drug_name`, it fell back to the
> **first ingredient**. So every one of our 15 combination products was matched to a
> plain single-ingredient item — Caduet to amlodipine, Targin to OxyContin, Panadeine
> Forte to plain paracetamol — and then inherited that item's real PBS code and real
> ATC.

**A real code belonging to a different medicine is far worse than a synthetic one.** A
synthetic code is visibly ours and resolves to nothing; a wrong real one is confidently
wrong, and the entire value of the `code` tier in `normalise_med` is that it is a fact
rather than a guess.

Fixed: a combination now matches only when the PBS `drug_name` mentions **every**
ingredient, or the brand is ours. Never a component. Results:

| | before | after |
|---|---|---|
| real PBS codes | 188/207 | **203/224** |
| combination products matched correctly | 0 of 22 | **22 of 22** |
| ATC disagreements | 35 | **6** |
| disagreements changing APINCHS class | 2 | **1** |

**I have to withdraw a claim.** I told Arpon that paracetamol/codeine showed DATA_SPEC
right and PBS wrong because "PBS loses the codeine". It does not. I had matched plain
paracetamol. PBS returns `12022R` "Paracetamol + codeine" and agrees with the spec.
Only **sotalol** is a genuine disagreement.

The remaining five are all benign: pregabalin (PBS `N02BF02` is the newer code, neither
is APINCHS), methotrexate (DATA_SPEC 10.1 deliberately maps it under both, both → C),
hydroxychloroquine and magnesium (same class, more specific code).

### Sotalol: keep `C07AA07`, and our extension rows are weaker than they looked

**Decided: keep DATA_SPEC's `C07AA07`.** WHO deliberately keeps sotalol out of `C01BD` —
its C01B guidance says sotalol is classified in C07AA despite class III properties. PBS
deviates from WHO here, across both items checked (8398B, 2043M), so it is PBS-wide
rather than strength- or indication-specific.

**The uncomfortable part is our own table.** Sotalol would only become high-risk through
our `C01BD` extension row, and that row cites a **WA Health APINCHS poster from August
2015**. WA Country Health's *current* list (v6.05, 7 October 2026) contains **no
antiarrhythmics at all**. Neither does core ACSQHC, nor SA Health's APINCHEN. So rows 34
(digoxin) and 35 (amiodarone) rest on a superseded document — they are defensible as
facility-policy extensions but should not be presented as ACSQHC. The `source` column in
`apinchs_atc.csv` now says so.

**Consequence for the scorecard:** report **core-APINCHS recall separately from
extended-list recall**. Pooling them lets a weak extension inflate or deflate a headline
number that reads as ACSQHC compliance.

### Formulation pairs: three added, two confirmed impossible

Verified against the October 2026 PBS schedule in our own snapshot, with real codes and
real ATC — not from general knowledge:

| Drug | Added | Brands | Strengths |
|---|---|---|---|
| metoprolol MR | ✅ | Toprol-XL, Metrol-XL, Minax XL | **47.5 / 95 / 190 mg** |
| gliclazide IR | ✅ | APX-Gliclazide, Nidem | 80 mg |
| diltiazem IR | ✅ | Cardizem, Vasocardol | 60 mg (we already had CD 180/240) |
| venlafaxine IR | ❌ | not marketed in Australia | — |
| tamsulosin IR | ❌ | not marketed; the MR is RPBS-only | — |

**Note the strengths.** Australian metoprolol MR is labelled by *succinate* weight, so
"succinate MR 100 mg" does not exist here — 95 mg is the equivalent of 100 mg tartrate.
Writing 100 mg would have put a product in the lexicon that no Australian pharmacy
dispenses.

Two further corrections to our own data: the tamsulosin brand is **Flomaxtra**, not
Flomax, and **Efexor-XR 225 mg** was not found on the PBS listing (strengths trimmed to
37.5/75/150).

So `formulation` now has **six** eligible drugs instead of three. Venlafaxine and
tamsulosin are recorded in `NO_AUSTRALIAN_PAIR` with the reason, so re-adding one has to
come with a brand and a strength.

### Bundle 6 was a missing agent, not a typo

The 0.95 gap is resolved. **Desvenlafaxine** had 2,457,365 PBS scripts in 2023-24,
*out-ranking* duloxetine's 2,261,367 — so omitting it while keeping duloxetine
contradicted the volume ordering the spec says it used. Added at `N06AX23` (from our PBS
snapshot), and all six reweighted to the real split: escitalopram 0.264, sertraline
0.248, venlafaxine 0.147, mirtazapine 0.144, desvenlafaxine 0.102, duloxetine 0.095.

Amitriptyline is high-volume (2,862,712) but **deliberately excluded**: in this age group
it is typically 10–50 mg for chronic pain rather than 75–150 mg for depression, so it
does not belong in a depression bundle.

**Still open:** no age-restricted agent-level volumes were found, so these are all-ages
shares. Directionally, mirtazapine should probably be up-weighted for 60–90 (5th most
dispensed in residential aged care) and the SNRIs down-weighted.

### Sample size: our 100% APINCHS recall target needs more care than we thought

- **~300 held-out patients** for 15 instances of the rarest type — and that is for a 90%
  chance of actually getting 15, not the expected count (221).
- **The number that matters:** with *perfect* recall, the Wilson lower bound is
  `n/(n+3.84)`. So **15/15 supports a lower bound of only 0.80**. Claiming ≥0.95 needs
  about **73 instances**. We cannot responsibly print "APINCHS recall 100%" off 15 cases.
- **Reportability floor:** below 10 instances report `k/n` as indicative only; 10–29 with
  the interval; 30+ normally.
- **Keep Wilson.** Clopper–Pearson is wastefully conservative (Brown, Cai & DasGupta);
  show it only as a sensitivity check if asked.
- **Targeted enrichment beats scaling everything** — but **precision is not transferable
  under enrichment** because it depends on prevalence. Recall is fine (it is conditional
  on an instance existing). So precision must be reported on the natural-rate split only,
  and the enrichment factor per type disclosed.
- **The scorecard does not have to run through the demo query path.** Score a large
  held-out set offline and keep the demo on a small subset — which removes the latency
  objection to a bigger population entirely.
- `formulation` may be the real binding constraint, not `dose_unconfirmable`: at 0.15 per
  *eligible* patient it needs ~500 patients if 20% are eligible.

### PBS licence: our conservative reading stands, and needs a letter

No CC BY statement exists for the **API**. The CC BY 3.0 AU listings on `data.gov.au` are
Services Australia's *statistical reports* (Item Report, ATC Report, Patient Category
Report) — different products. The third-party CC BY claim for the API is an extrapolation
from those. The Department's own copyright notice, as mirrored on MBS Online (April
2024), reserves all other rights.

So **keep `data/reference/` gitignored, keep committing only the ≤200-row attributed
sample, and keep altering no PBS value.** Of the five operations we asked about: row
subset probably fine, column subset ambiguous, JSON→CSV probably fine, joining a
`pbs_code` into our own table unresolved, deriving a new value likely a modification.

**Action:** email `copyright@health.gov.au` and `HPP.Support@health.gov.au` listing the
five operations. A written answer is the only thing that settles it. Nothing blocks on
it — our current handling is the safe side of every ambiguity.

---

## 2026-10-24 — Registration is live, and Zetaris is **not** the time budget **[live — Arpon's machine, 24 Oct]**

PLAN steps 5 and 6 applied with Arpon's go-ahead. All 28 statements succeeded, all
8 views verified against the files `datasvc` serves, and
`SELECT COUNT(*) FROM medtrace.all_sources` returns **4,825**.

| View | Zetaris | datasvc | Time |
|---|---|---|---|
| `medtrace.emr` | 325 | 325 | 0.39 s |
| `medtrace.gp` | 307 | 307 | 0.25 s |
| `medtrace.pharmacy` | 3 869 | 3 869 | 0.94 s |
| `medtrace.patient_report` | 324 | 324 | 0.19 s |
| `medtrace.med_lexicon` | 207 | 207 | 0.20 s |
| `medtrace.apinchs` | 42 | 42 | 0.22 s |
| `medtrace.nicknames` | 167 | 167 | 0.16 s |
| **`medtrace.all_sources`** | **4 825** | **4 825** | **1.05 s** |

**Template timings, the number that matters:**

| Template | Time | Rows |
|---|---|---|
| Q_REF ×3 (lexicon, apinchs, nicknames) | 0.17–0.64 s | 207 / 42 / 167 |
| Q0 admissions | 0.33 s | — |
| **Q1 identity (the federated query)** | **1.84 s** | 145 |
| Q2 meds | 1.86 s | 9 |
| Q3 verify | 1.72 s | 9 |

**A complete run costs about 6 s of Zetaris**, against a 5–10 minute judging budget.
This closes the question the 24 Oct correction opened: latency tracks bytes scanned, our
silos are ~2 MB, and at that size the data layer is nowhere near the constraint. The
4 queries + 6 model calls the plan budgets for will be dominated by the model, not the
database.

Every architectural rule still stands and is still worth keeping — no joins at agent
time, harmonise in registered views, one batched verification query, a hard query budget
— but they are now **prudent rather than forced**. The one that is genuinely load-bearing
is "reference the union view only once", which is a hard engine limit, not a performance
choice.

### The bug this found: a NULL is not an empty string

Diffing the **real** `q_identity_candidates()` output against the committed fixtures
showed every row count matching — 145 vs 145, 387 vs 387, all ten patients — while
**409 cells per envelope differed**. Nothing failed. Normalising nulls made the two sets
byte-identical, which isolated the cause:

| Case | Live Zetaris returns |
|---|---|
| a column the source **does not have** (view emits `CAST(NULL AS STRING)`) | **JSON `null`** |
| a column it **has**, whose value is blank (a missing `ihi_syn`) | **`""`** |

The fixture generator stringified both to `""`. So `name_family` was `""` where live
gives `null` for every pharmacy and patient row. **`SAMPLE_MODE` would have replayed a
shape the live view never produces**, and because row counts agreed, no count check,
schema check or test would ever have caught it. `parse.py` treats both as absent, so the
*behaviour* would have looked fine until the first live run disagreed with the recorded
one.

Fixed in `harmonise()` and `envelope()`: `None` is preserved as JSON null. All 10
fixtures now match live exactly.

**Kept as a command, not a one-off:** `register_sources.py --diff-fixtures` re-runs the
live Q1 per patient and diffs. PLAN 2.9 asked for this ("any difference is a view bug"),
and the fixtures and views can drift later — a `HARMONISED_MAP` edit, a regenerated silo,
an edited template. `--verify-only` now runs it too.

**Lesson worth keeping:** a row-count check is not a shape check. Counts matching is
weak evidence; it was true here while every single row was wrong in one column.

### Housekeeping

`medtrace_spike` from the morning's reachability spike still exists as an empty
SchemaStore container. There is no SQL path to drop a container
(`REFERENCE_NOTES` 1.3), so it needs the Data Explorer. Cosmetic; it does not collide
with `medtrace`.

---

## 2026-10-24 — PBS reference data: PLAN §3's backbone is not publicly obtainable; the hand-built lexicon becomes the primary **[live, 24 Oct]**

PLAN §3 names "the PBS monthly *PBS API CSV files* ZIP (October 2026 bundle, about 5 MB)"
as the backbone, with the join spine
`PBS item code → AMT MP/MPP/TPP via amt-items → primary ATC via item-atc-relationships → APINCHS`.
**None of that is reachable without credentials.** Checked, in order:

| Source | Result |
|---|---|
| `data.pbs.gov.au` | 200, but states **"The legacy outputs have been discontinued. The PBS embargo API is now the only source of embargo data available."** The CSV bundle PLAN §3 relies on is gone. |
| `data-api.health.gov.au/pbs/api/v3/schedules` | **401** — `"Access denied due to missing subscription key"`, header `Subscription-Key`. Requires registration. |
| "Developer Downloads" on `data.pbs.gov.au` | "Available to all authorised users who have a **login** to the embargo downloads area." |
| `data.gov.au` — PBS **Item Report** (CC BY 3.0 AU) | Downloaded, 27 MB. Columns: `Year, Item_number, State, Scheme, Month, Patient_Category, Services, Benefits ($)`. **No drug names, no ATC codes, no strengths.** |
| `data.gov.au` — PBS **ATC Report** (CC BY 3.0 AU) | Downloaded, 207 KB. Columns: `Year, Month, State, ATC_Classification, Scheme, Services, Benefits ($)`, where `ATC_Classification` is an **ATC level-1 name** ("Alimentary Tract and Metabolism"). **No ATC codes, no item codes.** |
| `data.gov.au` — any PBS dataset with drug names or a Date of Supply file | Only three PBS datasets exist there (Item, ATC, Patient Category), all utilisation statistics. No Date of Supply. |

So the two open mirrors are **dispensing statistics**, not the schedule. Neither carries
`item_number → drug_name → ATC code`, which is the join the whole lexicon depends on.
That mapping exists only in the current schedule, behind the subscription key or the
embargo login.

**Decided: PLAN 11's named fallback becomes the primary** — *"the hand-built ~150-row
lexicon, marked as our own, using codes from the sample."* With one amendment: there is
no PBS sample to take codes from, so the ATC codes are written from general
pharmacological knowledge for a small set of common medicines. That is a defensible
position and it is **not** a redistribution of the WHO ATC/DDD index (which PLAN §3
forbids committing): it is roughly 80 individual, widely-published classification facts,
hand-entered, for drugs we chose. It is stated plainly in `docs/DATA_LICENCES.md` and the
README rather than implied to be PBS-derived.

**Consequences.**
- **No credential is introduced.** Pursuing the API would have added a
  `Subscription-Key` secret to manage, against the grain of "no credentials anywhere
  shared" (PLAN §9).
- **The licence question dissolves.** PLAN §3 and PLAN 11 both flagged the PBS licence as
  *unconfirmed* and made committing PBS-derived rows conditional on reading a `_meta`
  copyright block. Hand-built reference data is our own work under the repo's licence, so
  there is nothing to confirm and nothing to gitignore for licence reasons. The two
  CC BY 3.0 AU mirrors are declared in `docs/PREEXISTING.md` as *consulted and not used*.
- **`dos_weight` loses its real basis.** It was to come from PBS Date of Supply volumes.
  The Item Report has real volumes but no drug identity, so they cannot be attached to a
  named medicine. Weights are therefore hand-assigned on clinical plausibility and
  **labelled as such** — they only bias sampling toward common medicines, and no result
  depends on them being accurate.
- **Reduced from ~150 products to ~80.** The generator is now 40 patients at 5–12 meds
  (decided 24 Oct), so ~80 products covering the PLAN 4.4 condition bundles and every
  APINCHS class is ample. Padding to 150 would add hand-written content that nothing
  samples.
- `scripts/fetch_reference.py` is kept, and **documents this investigation and fails
  loudly with the reason** rather than being deleted. If someone obtains a subscription
  key later, the regeneration path is already written down.

**Honesty note for the README.** We should say that our medicines reference data is
hand-built and why, rather than claiming an open-data pipeline we do not have. The
synthetic *patients* were always synthetic; this makes the *medicines* our own work too.

---

## 2026-10-24 (later) — **Correction: Zetaris latency tracks bytes scanned, not a fixed per-query floor** **[live — Arpon's machine, 24 Oct]**

**This supersedes the central claim of the "Zetaris latency is the binding constraint"
entry below.** That entry says: *"This is per-query engine overhead, not data volume.
A `COUNT` on 789 rows costs ~4 s warm. Smaller synthetic silos will not make it
meaningfully faster — the floor stays."* **That is wrong, and it was wrong in the
direction that matters.** It was inferred from one table without checking a second.

Measured across four tables of very different size:

| Query | Rows | Approx. bytes | Time |
|---|---|---|---|
| `SELECT 1` | — | — | ~1.0 s |
| our union view, `COUNT(*)` | 4 200 | ~1.1 MB | **2.3 s** |
| `NY_TAXI.taxi_zones`, `COUNT(*)` | 789 | ~11 MB (14.2 KB/row — multipolygon geometry) | **17.0 s** |
| `NY_TAXI.taxi_trips`, `COUNT(*)` | 500 000 | ~50 MB | **164.2 s** |

Roughly **~1 s fixed + 2–3 s per MB scanned**, consistent across all four. The 789-row
table is slow because its rows are 14 KB each, not because 789 rows are expensive.
`taxi_zones` was the worst possible table to generalise from: it is the smallest by row
count and nearly the largest by volume, which is exactly what produced the false
"volume doesn't matter" reading.

**What this changes.**

- **Keeping the silos small and narrow is the primary latency lever**, not a
  nice-to-have. The previous entry said the opposite. A 200-patient dataset at ~1 MB
  per silo queries in 1–3 s.
- **A realistic run is ~4 queries × 2–3 s ≈ 10 s of Zetaris**, not minutes. The 5–10
  minute judging budget is comfortable, and Zetaris is **not** the dominant cost at our
  data size. Yesterday's "Zetaris, not the model, is the judging time budget" held only
  for the sample tables.
- **The `91.2 s` join from yesterday is explained**: it scanned `taxi_trips` against
  `taxi_zones`'s 11 MB of geometry. It was not evidence of a join penalty in general.
- **Column pruning does not avoid the scan.** A narrow two-column projection on
  `taxi_zones` took 15.3 s against 17.0 s for a full `COUNT(*)` — a 10% saving, not the
  order of magnitude a columnar format would give. So trimming Q1 to 12 columns helps
  the response payload, not the scan. **Generate less data; do not rely on selecting
  fewer columns from more.**

**What does not change.** The design decisions the earlier entry drove are still the
right ones, for reasons that survive the correction: no `JOIN`s at agent time (the
union view cannot be referenced twice anyway — see the spike entry), harmonise in
registered views, one batched verification query, a hard query budget. They are now
*prudent* rather than *forced*, and `ZETARIS_TIMEOUT_S=180` stays — 164 s on a 50 MB
table is exactly the kind of worst case it exists for.

**Method lesson, recorded because it caused the error.** One table, one shape, one
afternoon, generalised into an architectural constraint, written into `DECISIONS.md`,
`TODO.md` and `PROGRESS.md`, and reported as the finding of the day. The fix was a
single extra query against a second table. Before a measurement becomes a design
constraint, vary the thing you are claiming is irrelevant.

---

## 2026-10-24 — The reachability spike passed, and the whole REST→explode→view→union chain works **[live — Arpon's machine, 24 Oct]**

PLAN step 1. **No fallback is needed.** `datasvc` can sit on the host and Zetaris will
read it, which keeps `docker-compose.yml` as it is and retires the MinIO/Parquet and
Postgres-over-JDBC contingencies (PLAN 11).

**The network path.** A throwaway `python3 -m http.server 8100 --bind 0.0.0.0`, then
from inside the containers:

| From | Result |
|---|---|
| `zetaris-api-1` → `http://host.docker.internal:8100/records.json` | **HTTP 200 in 0.023 s** |
| `zetaris-driver-1` → same | **HTTP 200 in 0.020 s** |

That only proves the containers' own network. The part that matters is whether
Zetaris's **REST-table client** honours it, so the full chain was registered against
two throwaway silos (2400 and 1800 records, 643 KB and 479 KB):

| Step | Result |
|---|---|
| `CREATE LIGHTNING DATABASE MT_SPIKE` | ok, 0.52 s |
| `CREATE LIGHTNING REST TABLE … endpoint "http://host.docker.internal:8100/…"` | ok, 0.51 s |
| `SELECT * FROM MT_SPIKE.emr_raw` — **does Zetaris fetch our URL?** | **yes**, the records array came back |
| `CREATE SCHEMASTORE CONTAINER medtrace_spike` | ok, 0.10 s |
| `CREATE SCHEMASTORE VIEW … LATERAL VIEW explode(records) AS r` | ok, 0.34 s |
| `SELECT COUNT(*)` through the explode view | **2400**, 1.42 s |
| `CREATE SCHEMASTORE VIEW all_sources … UNION ALL …` | ok, 0.84 s |
| `SELECT COUNT(*) FROM medtrace_spike.all_sources` | **4200**, 2.34 s |
| **The real `q_identity_candidates()` output, run verbatim** | **23 rows, 2.63 s** |

**Three things this settles.**

1. **The union view registers, caches and queries.** PLAN 2.1 listed this as a spike
   and the fallback was four separate per-source views on a budget of 14. Not needed.
2. **`queries.py` generates SQL that Zetaris accepts.** The Q1 built by the real
   function — `IN` list of DOB spellings, nested `UPPER`/`LIKE` on three name columns,
   the anchor clause, 12-column projection — ran unmodified against a live union view
   over explode views, including `UPPER(name_family) LIKE 'O\'BR%'` against a real
   `O'Brien` row. That retires "no SQL here has touched Zetaris".
3. **The "reference the union view only once" rule is confirmed on *our* view shape**,
   not just the reference repo's. A self-join on `medtrace_spike.all_sources` failed
   with exactly the documented error:
   `MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION … attribute(s) "records"
   missing … in operator !Generate explode(records#13223)`. The error names `records`,
   the pre-explode array column — so the failure is in the explode, and **any** second
   reference breaks it, not just a self-join. `queries.py`'s no-subquery /
   no-window-function rule is therefore load-bearing, and a test asserts the view
   appears exactly once per template.

**`CACHE TABLE` is not the latency lever we assumed.** Measured either side of it on
the 4200-row union:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| before `CACHE TABLE` | 1.39 s | 1.66 s | 1.06 s |
| after `CACHE TABLE` | 2.01 s | 1.07 s | 1.33 s |

No measurable difference. The sponsor's 49.7 s → 1.2 s figure
(`REFERENCE_NOTES` 1.3) was a **rate-limited external API**; our `datasvc` is a local
HTTP server on the same machine, where a refetch of 643 KB is free. Keep
`CACHE TABLE` — it still stops a demo hammering `datasvc` on every query, and it is
harmless — but it is **not** the thing that makes runs fast, and the earlier
"`CACHE TABLE` mandatory" framing overstated it. The real lever was avoiding joins.

**A NULL is not a string.** `CAST(NULL AS STRING)` in a view came back as JSON `null`
(Python `None`), not `"null"` — see `REFERENCE_NOTES` 1.1. `parse.py` must treat it as
absent rather than stringifying it, or `name_previous`, `sex` and every other
source-specific null become the literal text `"None"` and read as present,
non-matching values in identity scoring and `evidence_state`.

**Cleanup.** `MT_SPIKE`, its two REST tables, `medtrace_spike` and its three views are
throwaway and dropped. There is **no SQL path to drop a SchemaStore container**
(`REFERENCE_NOTES` 1.3), so `medtrace_spike` may linger as an empty container; that is
cosmetic and does not collide with the real `medtrace` container.

**Method note for anyone repeating this:** my spike script's stdout was block-buffered
because it was not attached to a tty, so a long run looked like a hang with an empty
output file. Use `print(..., flush=True)` in anything whose progress you intend to
watch.

---

## 2026-10-24 — `''` is **not** an escaped quote in Lightning SQL; it silently deletes the apostrophe **[live — Arpon's machine, 24 Oct]**

**Use `\'` (backslash). Never `''` (doubled quote).**

The standard-SQL doubled quote does not escape in this dialect. It **closes one
string literal and opens another**, and adjacent literals are concatenated — so the
apostrophe is deleted, the quotes stay balanced, nothing raises, and the value is
quietly corrupted.

Measured directly:

| Statement | Returns |
|---|---|
| `SELECT 'O''Brien'` | `OBrien` — **length 6, not 7** |
| `SELECT LENGTH('' '' '' '')` (four quotes) | `0` |
| `SELECT 'AB' 'CD'` | `ABCD` — adjacent literals concatenate |
| `SELECT 'O\'Brien'` | `O'Brien` — correct |

And against real rows (`NY_TAXI.taxi_zones`, 789 rows, 2 zones containing an apostrophe):

| Predicate | Rows | Truth |
|---|---|---|
| `zone LIKE '%''%'` | **789 of 789** | pattern collapsed to `%%` |
| `zone LIKE '%\'%'` | **12** | correct |
| `zone = 'Eltingville/Annadale/Prince''s Bay'` | **0, no error** | silently wrong |
| `zone = 'Eltingville/Annadale/Prince\'s Bay'` | **3** | correct |

**Why this matters more than it looks.** For MedTrace it is a patient-safety bug, not
a style issue. `O'Brien`, `D'Souza`, `O'Connor` are ordinary Australian surnames. With
the doubled form the name reaches Zetaris as `OBrien`, matches nothing, and the
pharmacist is told **"GP: no record found" for a record that exists** — a fabricated
coverage gap, produced by a query that succeeded. No exception, no empty-result
warning, nothing in a trace to notice. It would have looked like a data problem.

**Decided:** `queries.sql_literal()` escapes `\` → `\\` then `'` → `\'`. Backslash is
escaped, not refused (the earlier code refused it, on the assumption that doubling the
quote was the safe path — the exact inversion of the truth). Verified to round-trip
every value these templates embed, and hostile input (`x' OR 1=1 --`, `x'; SELECT 1 --`)
comes back as an inert string rather than altering the statement. Semicolons and
control characters are still refused outright, because no template embeds free text and
refusing keeps the statement-level "one statement, no semicolon" guard sound.

**Caught by testing the dialect rather than trusting it.** The templates had been
written to the published SQL rules and a recorded response envelope, and reviewed, and
had 104 passing tests — one of which asserted the *wrong* escaping as correct. Nothing
short of sending the SQL to the engine would have found it.

**Also measured, same session** — the construct costs for a Q1-shaped predicate on 789
rows, which is the realistic shape of our identity-blocking query:

| Shape | Time |
|---|---|
| `COUNT(*)` with `IN ('a','b','c')` | 3.8 s |
| `COUNT(*)` with `UPPER(col) LIKE 'AST%'` | 8.1 s |
| `COUNT(*)` with `LIKE '%...%'` | 6.6 s |
| 4-column projection, full Q1-shaped `OR` chain (IN + LIKE + nested ORs) | **24.5 s** |
| 6-column projection, 789 rows, no `WHERE` | 9.5 s |

`UPPER()` and `LIKE` are not free, and the `OR` chain is the expensive part. At ~25 s
for Q1 the 8-query budget still fits the 5–10 minute judging limit, but with less room
than the plan assumed. Confirms the no-`JOIN` rule and makes trimming Q1 to the 12
identity columns (rather than all 25) worth keeping.

**Verified safe for `NULL`:** `UPPER(CAST(NULL AS STRING)) LIKE 'A%'` returns 0 rows
rather than erroring. Q1's `OR` chain over `name_previous` — null for three of the four
sources — depends on that.

---

## 2026-10-24 — Zetaris latency is the binding constraint on the whole design **[live — Arpon's machine, 24 Oct]**

> **⚠️ Superseded in part by the correction entry above (24 Oct, later).** The
> measurements here are accurate, but the conclusion drawn from them — *"per-query
> engine overhead, not data volume … smaller synthetic silos will not make it
> meaningfully faster"* — **is wrong.** Latency tracks bytes scanned (~1 s + 2–3 s/MB).
> `taxi_zones` is 789 rows of 14 KB each, so it is a large table that looks small.
> Read the correction before relying on anything below.

**Measured**, against the install's own `NY_TAXI` sample data:

| Query | Rows involved | Time |
|---|---|---|
| `SELECT 1` | — | ~1.1 s |
| `SHOW LIGHTNING DATABASES` | 2 | 0.15 s |
| `COUNT(*) FROM taxi_zones` | 789 | 20.7 s cold, then 11.2 / 3.9 / 6.1 s warm |
| `SELECT * ... LIMIT 5` | 789 | 5.8 / 3.4 / 3.7 s |
| 2-table `JOIN` + `GROUP BY` | ~8 k ⋈ 789 | **timed out once, then 91.2 s** |

**This is per-query engine overhead, not data volume.** A `COUNT` on 789 rows costs
~4 s warm. Smaller synthetic silos will not make it meaningfully faster — the floor
stays. It is Lightning/Spark planning and dispatch on every REST call.

**Decisions that follow.**

1. **`ZETARIS_TIMEOUT_S` raised from 60 to 180.** 60 was below the observed worst case:
   the 91 s join would have failed, and one attempt timed out outright. A too-low
   timeout would have read as "Zetaris is broken" rather than "the query is slow".
2. **`CACHE TABLE` after registration is mandatory, not an optimisation.** Already
   required because a REST table re-calls its source per query; now doubly so.
3. **Push joins into `CREATE SCHEMASTORE VIEW` at registration time.** Agents should
   query flat, pre-joined views, not compute joins live. A 91 s join inside an agent
   loop is unaffordable; the same join computed once at setup costs nothing per run.
4. **The Evaluator must batch verification.** Re-deriving each cited number with its
   own query — the obvious implementation — is the single easiest way to blow the
   judging budget. One query returning all the figures to check, not one per claim.
5. **The orchestrator needs a per-run query budget**, not just `MAX_AGENT_ITERATIONS`.
   At ~4 s per trivial query, 30 queries is 2 minutes of pure latency before any model
   call. `RUN_TIMEOUT_S=600` must cover Zetaris time, model time and retries together.
6. **Keep the synthetic silos genuinely small** and prefer `LIMIT`-ed reads.

**Why this matters for judging.** The brief requires a run that finishes in 5–10 minutes
on a CPU-only machine. Model calls are fast (~0.4–1.2 s to a Nemotron). **Zetaris, not
the model, is the latency budget.** Any design that issues joins per claim fails that
requirement on timing alone, with correct code.

Re-measure on each machine: these numbers are from one install under Docker Desktop on
Apple Silicon, with the driver sharing the host.

## 2026-10-24 — Two datasvc URLs, because two networks reach it

**Decision.** `DATASVC_PUBLIC_URL` is what **Zetaris** uses and goes verbatim into the
`CREATE LIGHTNING REST TABLE ... endpoint` SQL. `DATASVC_INTERNAL_URL` is what **our own
app** uses. `docker-compose.yml` overrides only the internal one, and `config.py`
rejects a `datasvc:` host for the public one.

**Why.** The first draft of `docker-compose.yml` set
`DATASVC_PUBLIC_URL: http://datasvc:8100` — correct for our app on our compose network,
and wrong for its documented purpose. Zetaris runs in a **separate compose project** and
cannot resolve `datasvc`. The registration SQL would have embedded that hostname, the
`CREATE` would have succeeded, and every query against the table would then have failed.

That is precisely the failure the Zetaris HOWTO warns about — "a successful `CREATE`
alone does not confirm a usable table" — and it is slow to diagnose, because the symptom
appears one step away from the cause. Caught by reading the compose file against
`.env.example`, before Phase 3 existed to be broken by it. A validator now makes the
mistake impossible to reintroduce silently, with a test for both directions.

**Still unproven:** whether the Zetaris containers can reach `host.docker.internal:8100`
at all. That is the Phase 3 spike, with fallbacks in order: put datasvc on the Zetaris
compose network, MinIO/Parquet, then Postgres over JDBC.

## 2026-10-24 — `finish_reason` cannot be trusted to detect truncation **[live — Arpon's machine, 24 Oct]**

**Decision.** The Meterless adapter must detect a truncated response by comparing
`usage.completion_tokens` against the `max_tokens` we sent, **not** by reading
`finish_reason`. On truncation it must raise, not return the partial text.

**Why.** Same prompt, two budgets:

| `max_tokens` | `finish_reason` | `completion_tokens` | Output |
|---|---|---|---|
| 2048 | **`"stop"`** | 2048 (exactly the cap) | cut off mid-table, mid-sentence |
| 8192 | `"stop"` | 3001 | complete, ends on a full sentence |

`finish_reason` reported `"stop"` in **both** cases. A truncated answer is
indistinguishable from a complete one by that field alone. Left unchecked, the Writer
would emit half an evidence table and the Evaluator would validate truncated JSON as
if it were whole — exactly the failure the Evaluator exists to prevent.

The tell is `completion_tokens == max_tokens`. Treat that as truncation, always.

**Consequence for the agent loop.** Reasoning-heavy roles need a generous budget: a
single hard analytical prompt legitimately consumed **3001 completion tokens**. Combined
with the earlier finding that a one-word answer costs ~45 tokens, the rule is: never
set a tight cap, and always verify the response was not cut off.

---

## 2026-10-24 — The Nightshift race settings are a ceiling, not behaviour; disable the nondeterministic ones for reproducibility, not provenance **[live — Arpon's machine, 24 Oct, ~40 calls]**

**Context.** Nightshift's global Preferences expose race width (set to 6), optimistic
streaming, consensus escalation, adaptive compute, self-refine and answer fusion. The
worry was that these could put a non-Nemotron model into a request and weaken our
NVIDIA evidence.

**What the receipts actually show.** Across roughly forty calls, including a
deliberately hard analytical prompt chosen because that is when adaptive compute is
supposed to engage:

- **Race width is a ceiling, not a behaviour.** Observed `routing.width` of **1–2 out
  of 4 ready lanes**, never 6, and the router narrows itself by confidence
  (`reason: "confident-exploit"` → width 1; `"leaning"` → width 2).
- **`consensus.raced` was `1` on every single call.** One lane produces the answer. No
  multi-model race is happening in practice.
- **Every optional feature was null, every time:** `fusion`, `synthesis`, `refine`,
  `gen_verifier`, `debate`, `quality_race`, `reasoning_scaffold`, `test_time_compute`,
  `consensus_escalation`, `budget_degrade`. Self-refine is **not** firing on our calls.
- **One phase per response** (`final_synthesis`), one model. No draft-then-upgrade, so
  optimistic streaming is not splicing in another model.
- **`egress.destination: "nvidia"` on every call**, and every answering model was a
  Nemotron.

**So the provenance risk is low, for a reason unrelated to those settings:** all four
ready lanes are cloud Nemotron, no on-device model is cached, and `meterless/local`
returns `privacy_floor_blocks_all_routes`. Optimistic streaming has no local model to
draft with even if it fired.

**The real reason to turn them off is reproducibility.** The answering model still
alternates run to run between `nemotron-3.5-super-vl-120b-a12b` and
`nemotron-3.5-lightning-30b-a3b` on identical input. Our outputs must change with
*inputs*; they should not change randomly between identical runs, or `output_examples/`
and the demo become unexplainable. So before recording examples or demoing, disable the
nondeterministic features — and note in the README that the model can vary.

**Keep cross-check on.** It returned `status: "passed"` with
`recommended_action: "allow"` and per-check results for destructive actions, PII and
schema validity. That is free, provider-side governance evidence toward the
human-review requirement.

**Turn self-refine off anyway**, despite it not currently firing: if Nightshift ever
critiques and revises internally, our own Evaluator → Planner loop gets less credit and
the traces become harder to explain.

**Receipts are unsigned, confirmed.** `served: "in-tab"` and `receipt_envelope: null`
on every call, consistent with `meterlessd` answering 501 — the app window is serving
without a daemon signature. Signed receipts would be stronger evidence, so this is
worth a mentor question. Not blocking: `routed_model` and the rest of the receipt are
present either way.

**`syncTraceRetention` is not findable from outside the app.** It does not appear
anywhere in the Meterless repo, and Nightshift's application-support directory holds
only `keys.json` (the provider key — deliberately not opened). Settings live in the
app's own web storage, so Engineer mode / the command palette are the only route in.

## 2026-10-24 — Keep the pinned role→route mapping; it satisfies the NVIDIA rule but does not choose a lane **[live — Arpon's machine, 24 Oct, 24 samples]**

**Decision.** Keep sending a pinned disposition on every call — `METERLESS_MODEL_FAST`
and `METERLESS_MODEL_DEEP`, mapped by role in `app.config.lane_for()`, never `auto`.
Keep recording what actually answered. Do **not** claim the route selects the model.

**What was tested.** The full procedure: discover route ids from `GET /v1/models`, put
them in `.env`, map role→route in code, then verify from `response.model`. Eight
samples per route with distinct prompts to avoid cache hits.

| Requested route | Answered by | Samples |
|---|---|---|
| `meterless/fast` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |
| `meterless/deep` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |
| `meterless/auto` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | 8/8 |

**Two findings, and they point in opposite directions.**

1. **The NVIDIA requirement is satisfied.** 24/24 calls were answered by an NVIDIA
   Nemotron, and `response.model` names which one. By the test "if it shows a Nemotron
   id, the pin is working", it works.
2. **The route does not choose the lane.** `fast`, `deep` and `auto` are
   indistinguishable — all three converge on the same model, and every response still
   carries `mode_coerced: true`. There is nothing to pin *between*.

**Why an earlier test looked like the lanes differed.** A 3-sample run had
`meterless/fast` return `nemotron-3.5-lightning-30b-a3b` once and `super-vl-120b`
twice, which read as a real distribution difference. It was not: the receipt's
`routing` block shows `policy: "learned-router"` with `reason: "cold-explore"` and
`confidence: 0`. The router was exploring. Once it converged it chose `super-vl-120b`
every time regardless of route. **Three samples were not enough to tell exploration
from routing policy** — worth remembering before concluding anything else from a small
sample against this runtime.

This also corrects the earlier entry below, which inferred "pinning is not honoured"
from a single call per id. The direction was right, the mechanism was not: it is not
that a requested id is overridden arbitrarily, it is that **every mode is coerced to
`auto`** and one learned router decides.

**Where lane control would actually live.** Not in our code. The published API surface
is only `GET /v1/models`, `GET /healthz` and `POST /v1/chat/completions`, and none
takes a lane. The receipt exposes `app_policy{has_rule, lanes, race_width}` — `lanes`
is `null` for us and `race_width` is 6 — so Nightshift has a per-app policy concept
selected by our `meterless-app` header. Configuring it is a Nightshift-side action on
one machine, not a repo change. Arpon's Nightshift has lanes `deep-reasoner`,
`fast-tools` and `deep-verifier` defined, and **none of them appear in
`GET /v1/models`**, so they are internal fleet lanes, not addressable routes.

**What we therefore claim.** That every model call goes through Nightshift to an NVIDIA
Nemotron, and that we record exactly which one per request. Not that we direct a role
to a specific model. Re-test if a later Nightshift build exposes `app_policy.lanes` or
stops coercing the mode.

## 2026-10-23 — Record `routed_model`, not `provider_model`, as the model-per-request evidence **[live — Arpon's machine, 23 Oct]**

**Decision.** The trace field that names which model answered is
`meterless.routed_model` (cross-checked against `meterless.winning_route.model` and
the top-level `response.model`, which agreed on every observed call).
`meterless.provider_model` is **not** that field and must not be presented as it.

**Why.** On this build (Runtime `m1-m4`), `provider_model` returned `meterless/auto`
on every single call — including when a concrete `nvidia/...` id was requested and
when `meterless/deep` was requested. It reports the resolved *mode*, not the model.
Logging it as "which model handled this request" would be actively misleading, and the
NVIDIA award asks for the model.

---

## 2026-10-23 — Lane pinning is NOT honoured; fall back to dispositions **[live — Arpon's machine, 23 Oct — superseded in detail by the 24 Oct entry above]**

**Decision.** Abandon pinning concrete `nvidia/nemotron-*` ids to the FAST and DEEP
lanes. Use the dispositions (`meterless/fast`, `meterless/deep`) and record the model
the router actually chose, honestly, per request. Do not claim lane control anywhere
in the README, video or slides.

**Why.** Tested directly, one request per id:

| Requested | `routed_model` (actual) | Honoured? |
|---|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | `nvidia/nemotron-3.5-lightning-30b-a3b` | yes |
| `nvidia/nemotron-3-super-120b-a12b` | `nvidia/nemotron-3.5-lightning-30b-a3b` | **no** |
| `meterless/deep` | `nvidia/nemotron-3.5-super-vl-120b-a12b`, with `mode_coerced: true` | coerced to `auto` |

Every request runs through `routing.policy: "learned-router"` with `width: 6` — a race
across six lanes — and the router picks the winner. `app_policy.lanes` is `null` and
`race_width` is 6, so the app cannot currently constrain it. The one apparent match
above was coincidence: on that call `routing.predicted` was a *different* model from
the winner.

**Consequence, and why the NVIDIA story survives.** We cannot choose *which* Nemotron,
but every winner observed was an NVIDIA Nemotron (`winning_route.provider: "nvidia"`,
`kind: "cloud"`), because NVIDIA is the only configured cloud provider and no on-device
model is cached. So "a Nemotron answered, and here is exactly which one" stays
provable per request from the receipt; "we direct role X to Nemotron Y" does not.
Role-to-disposition routing (Planner/Executor → `fast`, Evaluator/Writer → `deep`)
stays in the code as our declared *intent*, and the trace records what actually
happened next to it. Recheck if a later Nightshift build exposes `app_policy.lanes`.

---

## 2026-10-23 — Never send a small `max_tokens` **[live — Arpon's machine, 23 Oct]**

**Decision.** Do not set a tight `max_tokens` on any Nightshift call. Leave it unset,
or set it generously (≥512) with an explicit comment saying why.

**Why.** `max_tokens: 16` made every call fail with HTTP 502 and
`meterless_detail: "nvidia/nemotron-3.5-lightning-30b-a3b_empty_response"`, which
reads like an outage and cost real debugging time. The cause is that these Nemotron
lanes spend hidden reasoning tokens before the visible answer: a one-word reply
("ready") consumed 42–49 completion tokens. A 16-token budget truncates the response
to empty before any content exists. Raising the budget turned the identical request
into a 200 with the content `"ready"`.

---

## 2026-10-23 — Capture the whole `meterless` receipt into the trace, not response headers **[live — Arpon's machine, 23 Oct]**

**Decision.** The adapter records the `meterless` object from the **response body** on
every call. `with_raw_response` for headers is not sufficient.

**Why.** `meterless-*` **response headers: none returned** on this build. The body
instead carries a `meterless.compute_receipt.v1` receipt, which is much richer than the
contract doc implies and gives us evidence we would otherwise have to fabricate:

| Receipt field | What it buys us |
|---|---|
| `routed_model`, `winning_route{model,label,provider,kind,tier}` | which Nemotron answered — the NVIDIA award evidence |
| `request_id`, `receipt_id`, `decision_id` | correlate our trace to Nightshift's own record |
| `phases[]{phase,model,ms,tokensIn,tokensOut,outputTps}` | per-phase latency and tokens |
| `usage`, `cost{actual_usd,naive_usd,baseline}`, `savings` | real efficiency numbers, not projections |
| `cross_check{status,checks[],requires_review,recommended_action}` | a provider-side safety gate (destructive-action, PII, schema checks) we can surface in the UI toward the human-review requirement |
| `egress{destination,sent,withheld,redacted}` | where the data went — supports the data-governance story |
| `routing{policy,width,predicted,winner,confidence,reason}` | how the lane was chosen; the basis for the pinning finding above |
| `privacy.path`, `cache.status`, `consensus`, `host_pressure` | context for honest reporting |

**Caveat.** This is one build's undocumented response shape, not part of the published
contract. The adapter must read it defensively (every field optional, no KeyError) and
degrade to `response.model` alone if the receipt is absent.

---

## 2026-10-23 — World Model merge band: 0.85, per the conformance runner

**Decision.** Implement `decide()` as **≥0.85 → auto-merge, ≥0.82 → review, else new**.

**Why.** The engine's own documents disagree. `docs/ingest-pipeline.md` specifies
≥0.92 auto-merge / 0.82–0.92 review / <0.82 new. But `conformance/runner.ts`
(`band-001`) asserts `decide(0.85)=="auto-merge"`, `decide(0.84)=="review"`,
`decide(0.82)=="review"`, `decide(0.81)=="new"`, and that matches the ≥0.85
name-similarity threshold in `AGENTS.md` §merge-detection. Both engine repos say the
conformance suite is the definition of done, so the runnable artefact wins over the
prose. The discrepancy is noted in the test itself so nobody later "fixes" it the
wrong way, and the check is not weakened to make anything pass.

---

## 2026-10-23 — One Zetaris REST table per silo, served whole at one URL

**Decision.** `datasvc` serves each synthetic silo complete at a single endpoint
(`GET /silos/<name>` → `{"records": [...]}`), not as paged pages. One
`CREATE LIGHTNING REST TABLE` plus one `CREATE SCHEMASTORE VIEW` per silo, and a
`CACHE TABLE` immediately after each table is created.

**Why.** A Lightning REST table binds **one fixed endpoint URL** with no paging
parameter, so paged pages would need one table per page. And the reference repo
records that a REST table may re-call its source on *every query* — a `CACHE TABLE`
cut one count from 49.7 s to ~1.2 s. Without caching, every agent query would re-hit
`datasvc` and runs would blow the 5–10 minute judging budget.

---

## 2026-10-23 — Our app reads `.env`; the reference scripts read `.env.local`

**Decision.** The app uses `.env` with the hackathon's official variable names. We do
not read `.env.local` anywhere in `app/`.

**Why.** `.refs/zetaris` deliberately refuses `.env` and reads only `.env.local`. That
is *their* convention. Keeping ours separate means running a reference script never
pulls our config, and our app never depends on a file the hackathon doesn't define.
If we ever run `.refs/zetaris/scripts/*` directly it needs its own `.env.local`.

- **Pitch claims are vetted and the wording is fixed** (24 Oct). Three of our four
  headline claims were loose or wrong — "Actions 4.5/4.6 require two independent
  sources" is not what those Actions say. Approved wording and citations are in
  `docs/PITCH_CLAIMS.md`; the README, slides and video must use it verbatim.
