# Open research questions

Five self-contained briefs for someone outside the project. Each is written to be
handed over on its own — copy the whole section, including its Context block.

They are **blocking clinical and statistical judgement calls**, not engineering tasks.
Every one of them is a place where we deliberately stopped rather than guess, because
the alternative was inventing clinical data in a medication-safety tool.

**Rules that apply to all five answers.**

- **Cite a source for every factual claim.** A URL, a document name, or a product name
  plus the register it appears in. "I believe" or "typically" is not usable — we have to
  be able to defend every number to a judge, and a wrong one here is a wrong clinical
  claim.
- **Say "not found" rather than filling a gap.** An honest gap is cheap for us to work
  around; a plausible invention is not, because it will look like real data in a
  synthetic dataset and we will stop being able to tell the difference.
- **Flag where you are extrapolating** from a non-Australian source.
- The project builds a **medication-reconciliation prototype on 100% synthetic patient
  data**. Nothing here will touch a real patient. But the *reference* data (which
  medicines exist, how they are classified, which are high-risk) has to be real, because
  that is what the tool's output is judged on.

| # | Question | Blocks | Effort |
|---|---|---|---|
| 1 | Is sotalol a high-risk medicine, and which ATC code applies? | A classification decision already in code | ~30 min |
| 2 | Do four named medicines have both IR and MR forms in Australia? | A discrepancy type we cannot currently plant | ~45 min |
| 3 | How many synthetic patients do we need for credible per-type metrics? | Dataset size, and the honesty of our scorecard | ~1 h |
| 4 | What are the real Australian antidepressant utilisation shares? | A spec table whose shares sum to 0.95, not 1.00 | ~45 min |
| 5 | What does the PBS public API licence actually permit? | Whether PBS-derived rows can be committed | ~1 h |

---

## 1. Is sotalol a high-risk medicine, and which ATC code should it carry?

### Context

We classify medicines as "high-risk" using **APINCHS**, the Australian Commission on
Safety and Quality in Health Care's grouping of medicines where an error is most likely
to cause serious harm (**A**ntimicrobials, **P**otassium and other electrolytes,
**I**nsulin, **N**arcotics and other sedatives, **C**hemotherapeutic agents,
**H**eparin and other anticoagulants, **S**ystems). We implement it as a lookup table of
**ATC code prefixes** — for example `B01AA` (vitamin K antagonists) → class H, so
warfarin is high-risk. The table has 40 rows and includes facility-level *extensions*
beyond the core ACSQHC list, following SA Health's APINCHEN and WA Health's published
APINCHS material: digoxin (`C01AA05`), amiodarone (`C01BD`), sulfonylureas (`A10BB`),
clozapine, lithium, oral methotrexate.

We hit a conflict for **sotalol**:

- Our data specification assigns sotalol **`C07AA07`** (beta blocking agents,
  non-selective), which matches **no** APINCHS prefix, so sotalol is **not** high-risk.
- The **PBS public API** (`item-atc-relationships`, October 2026 schedule) returns
  **`C01BD`** (antiarrhythmics, class III) for sotalol items. `C01BD` **is** in our
  table, as the amiodarone extension — so under the PBS code sotalol **becomes**
  high-risk.

Both are defensible on paper. WHO ATC does list sotalol under C07AA07. But sotalol has
genuine class III antiarrhythmic activity, QT prolongation and proarrhythmic risk, which
is the clinical reason amiodarone is on high-risk lists in the first place.

The consequence matters in two directions. If we classify sotalol high-risk and it is
not, we add a "must review" alert that wastes a pharmacist's attention. If we classify
it as ordinary and Australian hospital practice treats it as high-risk, our tool fails
to flag a high-risk medicine — and we publish a metric called "APINCHS recall" with a
target of 100%, which would then be measuring the wrong denominator.

### What we need you to find out

1. **Do Australian hospital or state-health high-risk medicine lists include sotalol?**
   Check at minimum: ACSQHC's APINCHS material, SA Health's high-risk medicines list
   (they publish an extended "APINCHEN"), WA Health's APINCHS resource, and any state or
   large-network medication-safety list you can find (NSW CEC, Safer Care Victoria,
   Queensland Health). Quote the actual wording where sotalol appears or is absent.
2. **Is sotalol treated as high-risk specifically because of QT/proarrhythmic risk** in
   any Australian guidance — for example a requirement for ECG or QT monitoring, or
   inclusion in a "look-alike/sound-alike" or "double-check" list?
3. **Which ATC code is correct for sotalol**, and why do the two sources differ? Check
   the WHO ATC/DDD index entry for sotalol, and check whether PBS assigns `C01BD` to all
   sotalol items or only some (there may be a split by indication or by strength).
4. **Is the PBS–WHO disagreement a known, systematic thing?** We found 35 ATC
   disagreements between our specification and the PBS API across ~100 medicines. 33 are
   PBS giving a *combination product* the ATC of one of its components — for example
   Caduet (amlodipine + atorvastatin) coming back as `C08CA01` (amlodipine) rather than a
   `C10BX` combination code. **Is that expected PBS behaviour?** If so, say so plainly,
   because it tells us to ignore that whole class of disagreement rather than chase it.

### What to give us back

- A one-line recommendation: **sotalol high-risk, or not**, and under which ATC code.
- The evidence, with sources, including anything that points the other way.
- A yes/no on whether PBS's combination-product ATC behaviour is systematic and expected.
- If you find any *other* medicine among these that is clearly misclassified, name it:
  `data/reference/atc_crosscheck.csv` in this repo has all 35 disagreements if useful.

---

## 2. Do metoprolol, gliclazide, venlafaxine and tamsulosin each have both an immediate-release and a modified-release form in Australia?

### Context

One class of medication error we detect is a **formulation discrepancy** — the same drug
at the same total daily dose, but immediate-release (IR) in one record and
modified-release (MR/XR/CR/SR) in another. This is a real and clinically significant
error: metoprolol tartrate 50 mg twice daily is **not** interchangeable with metoprolol
succinate MR 100 mg once daily, and swapping oxycodone IR for oxycodone CR changes the
whole risk profile.

To generate a *synthetic* example of this error, we need **both forms of the same drug**
present in our reference table, with a real Australian brand name and real strengths.

Our specification names seven drugs as eligible for this error type: **metformin,
metoprolol, gliclazide, oxycodone, paracetamol, venlafaxine, tamsulosin**.

It only actually supplies both forms for three of them:

| Drug | IR form we have | MR form we have | Gap |
|---|---|---|---|
| metformin | Diabex / Diaformin 500, 1000 mg | Diabex XR 1000 mg | — |
| oxycodone | Endone 5 mg | OxyContin 10, 20 mg | — |
| paracetamol | Panadol 500 mg | Panadol Osteo 665 mg | — |
| **metoprolol** | Betaloc / Minax 25, 50 mg | **missing** | need MR |
| **gliclazide** | **missing** | Diamicron MR 30, 60 mg | need IR |
| **venlafaxine** | **missing** | Efexor-XR 75, 150, 225 mg | need IR |
| **tamsulosin** | **missing** | Flomax 400 microgram | need IR |

We will not invent a brand name or a strength for a medicine. So either someone confirms
the missing forms exist and tells us what they are, or we remove those four drugs from
the eligible list and keep the error type working on the three that already have both
forms.

### What we need you to find out

For **each** of metoprolol, gliclazide, venlafaxine and tamsulosin:

1. **Is the missing form currently marketed in Australia?** Check the TGA's Australian
   Register of Therapeutic Goods (ARTG) and the current PBS schedule. Be specific about
   which salt or ester, because it matters here: metoprolol **tartrate** is the IR salt
   and metoprolol **succinate** is the MR one, and they are not dose-equivalent 1:1.
2. If yes: **brand name(s), strength(s), and dosage form** as they appear on the
   register. Note whether it is PBS-listed or private-only.
3. If no: **say so explicitly.** We think tamsulosin may be MR-only in Australia, and
   gliclazide IR may have been largely displaced by the MR form — but we would rather be
   told than assume.
4. **Is an IR/MR mix-up for this specific drug clinically significant?** Briefly. If
   swapping the forms is clinically trivial for one of these, it is a poor choice for a
   safety alert regardless of whether both forms exist, and we would rather drop it.
5. **Are there better candidate drugs we have missed?** We are looking for drugs where
   (a) both forms are marketed in Australia, (b) they are commonly prescribed to people
   aged 60–90, and (c) confusing them actually matters. Nifedipine, diltiazem,
   verapamil, quetiapine, lithium, potassium chloride and morphine are plausible — but
   check rather than assume.

### What to give us back

A small table: drug, missing form, exists in Australia (yes/no), brand, strength(s),
dosage form, PBS-listed (yes/no), clinically significant if confused (yes/no + one
line), source. Plus any additional candidate drugs for point 5.

---

## 3. How many synthetic patients do we need for a defensible per-type scorecard?

### Context

We generate a synthetic population and plant known medication discrepancies in it, then
measure how many our tool finds. The scorecard reports **precision, recall and F1 per
discrepancy type**, with **Wilson 95% confidence intervals**, on a held-out split that
was never used for tuning.

There are **11 discrepancy types**, planted at very different rates. Some are per
medicine, some per patient:

| Type | Planted rate (from our spec) |
|---|---|
| omission | 0.055 per medicine |
| dose | 0.030 per medicine |
| frequency | 0.020 per medicine |
| stale_listing | 0.040 per GP-listed active medicine |
| commission | 0.20 per patient |
| duplication | 0.18 per patient |
| identity_uncertain | 0.18 per patient |
| formulation | 0.15 per eligible patient |
| route | 0.15 per patient |
| unpropagated_discharge_change | 0.25 per discharge action |
| dose_unconfirmable | 0.85 per *eligible* patient, where only ~8 per 100 patients are eligible (they must be on warfarin, insulin or a tapering steroid) |

Each patient carries 5–12 regular medicines, mean about 8.4.

Our specification asks for **200 patients (100 tuning / 100 held-out)** and states a
target of **at least 15 tuning instances of every type**. We are currently running
**40 patients (20 / 20)** for speed of iteration, which produces 73 planted findings
across 7 types — and at that size the rarest types have 3–5 instances in total, which
makes a per-type confidence interval almost uselessly wide.

There is a real cost to scaling up. Our data layer's query latency tracks **bytes
scanned** at roughly 1 second fixed plus 2–3 seconds per megabyte (measured). At 40
patients the dataset is about 2 MB and a query takes 1–3 seconds. At 200 patients it
would be about 10 MB, so perhaps 20–30 seconds per query — and a demo has a 5–10 minute
budget for a complete run of 3–4 queries. So "just use 2,000 patients" is not free.

### What we need you to find out

1. **How many held-out instances of a type do you need** for a per-type recall estimate
   with a Wilson 95% interval narrow enough to be worth reporting? Give the arithmetic.
   For example: if true recall is 0.8, what is the interval width at n = 5, 15, 30, 50,
   100? At what n does it stop being embarrassing to publish?
2. **Given the rates above, what total population size** delivers that for the *rarest*
   type? `dose_unconfirmable` is the binding constraint: 0.85 × ~8% eligible ≈ 0.068 per
   patient, so about 15 instances needs roughly 220 held-out patients — please check that
   and the others.
3. **Is there a smarter design than scaling the whole population?** Specifically:
   - Is **stratified or targeted oversampling** of rare types legitimate here, if the
     oversampling factor is declared and the metric is reported per type rather than
     pooled? What exactly has to be disclosed for that to be honest?
   - Would reporting a **pooled** metric across types, alongside sparse per-type numbers,
     be more defensible than publishing 11 very wide intervals?
   - Is there a standard way to present "this type has only 4 instances, here is the
     number but do not lean on it"? We would rather report an honest wide interval than
     quietly omit a type.
4. **What do comparable published studies use?** Medication-reconciliation and
   record-linkage evaluations — what sample sizes do they report per error type, and do
   they report per-type CIs at all? If the field typically reports pooled metrics, that
   is useful for us to know.
5. **Is Wilson the right interval** for proportions this small, or should we use
   Clopper–Pearson or Jeffreys when the count is in single digits?

### What to give us back

- A recommended **total population size**, with the arithmetic behind it.
- A recommended **minimum reportable n per type**, below which we should mark a figure as
  indicative rather than publish an interval.
- A yes/no, with conditions, on targeted oversampling of rare types.
- A recommendation on the interval method for small counts.

---

## 4. What are the real Australian utilisation shares for antidepressants in people aged 60–90?

### Context

Our generator builds each synthetic patient from "condition bundles". Within a bundle it
picks one **anchor** medicine according to a share, and the shares in a bundle are meant
to be a probability distribution summing to 1.00.

The **depression/anxiety** bundle in our specification does not sum to 1.00:

| Agent | Share in spec |
|---|---|
| escitalopram | 0.30 |
| sertraline | 0.28 |
| mirtazapine | 0.18 |
| venlafaxine XR | 0.12 |
| duloxetine | 0.07 |
| **Total** | **0.95** |

Every other bundle in the document sums to exactly 1.00, so this looks like either a
**missing sixth agent worth 0.05** or a **typo in one of the five**. We have transcribed
it faithfully and are normalising the five at sampling time, which is safe but silently
changes all five shares. We would rather know the intended answer.

The shares are supposed to be ordered by real PBS utilisation. The specification cites
2023–24 PBS data giving escitalopram 6,431,014 scripts and sertraline 6,041,182, which
is where the 0.30/0.28 ordering comes from.

### What we need you to find out

1. **What are the actual Australian dispensing volumes** for antidepressants, ideally
   restricted to people aged 60+ or 65+? Best sources: PBS statistics (Services
   Australia / Department of Health PBS item reports), the *Australian Prescriber* annual
   "Top 10 drugs" article, AIHW mental-health medication reports.
2. **Is a sixth agent missing from this list** that would plausibly carry about 5% of
   antidepressant use in this age group? Candidates: amitriptyline (common in older
   people, often for neuropathic pain rather than depression), paroxetine, fluoxetine,
   citalopram, agomelatine, vortioxetine, desvenlafaxine, moclobemide. Note that
   **desvenlafaxine** is a notable omission given its Australian volumes.
3. If a sixth agent belongs, **give the share for all six** so they sum to 1.00, with the
   volumes you based it on.
4. If instead one of the five existing shares is simply wrong, **say which and what it
   should be**.
5. **A caution we want checked:** amitriptyline in people aged 60–90 is frequently
   prescribed for neuropathic pain or sleep, not depression. If it belongs in the list by
   volume but not by indication, say so — it changes whether it belongs in a
   *depression/anxiety* bundle at all.

### What to give us back

A six-row table (agent, share, 2023–24 or latest script volume, source) summing to 1.00
— or a one-line correction to a single existing share. Plus a note on whether any agent
is high-volume for a non-psychiatric indication in this age group.

---

## 5. What does the PBS public API licence actually permit?

### Context

This one has potential legal exposure, which is why it is here rather than decided by us.

We fetch Australian medicines reference data (item codes, pack sizes, repeat counts, ATC
links) from the **PBS public API v3** at `https://data-api.health.gov.au/pbs/api/v3`.
It is free and needs no login, though every request carries a published unregistered
`subscription-key` header.

**Two different licence statements apply to the same data, and they disagree.**

1. Third-party summaries, and the `data.gov.au` listings for related PBS datasets, say
   **CC BY 3.0 Australia** — which permits commercial use, redistribution **and
   modification**, with attribution.
2. The API's own `_meta` block, returned in the body of every response, says:

   > Copyright (c) 2024 Department of Health, Commonwealth of Australia
   >
   > Permission is granted to use and redistribute this content, as long as all copyright
   > statements are retained. **Permission is not granted to modify this content.**
   >
   > For further copyright information of this content, please refer to:
   > https://www.health.gov.au/using-our-websites/copyright

CC BY permits modification. The `_meta` statement explicitly does not. We took the
conservative reading — honour the statement shipped with the bytes — and as a result we:

- never alter a PBS field value (we select rows and copy values verbatim);
- keep the raw snapshot **out of version control**;
- commit only a ≤200-row attributed sample;
- retain the copyright block alongside the data.

That is defensible but may be unnecessarily restrictive. It currently stops us from
committing the reference data a judge would need to reproduce our results without
re-fetching, which is a real cost.

### What we need you to find out

1. **Which statement governs?** Is the `_meta` block a deliberate licence term, or
   boilerplate that predates a later CC BY release? Check the Department of Health
   copyright page it links to, the PBS website's own terms, and any `data.gov.au` entry
   for the **API** specifically (as opposed to the statistical report datasets, which are
   clearly marked CC BY).
2. **What does "modify" mean here in practice?** We need a clear answer on each of:
   - selecting a **subset of rows** (we keep ~190 of 15,073 items);
   - selecting a **subset of columns**;
   - **reformatting** from JSON to CSV;
   - **joining** a PBS `pbs_code` into a table of our own and publishing the result;
   - **deriving** a new value from a PBS value.
3. **Can we commit a PBS-derived subset to a public GitHub repository**, and if so with
   what attribution and notice? Exact wording for the attribution would be ideal.
4. **Is the published unregistered subscription key intended for public use?** Check the
   PBS API documentation. Does using it in an open-source project breach any terms of
   use, and does registering our own key at `data-api-portal.health.gov.au` change the
   licence position at all?
5. **Is there a cleaner-licensed alternative** for Australian medicines reference data —
   item codes, ATC classification, pack sizes? Specifically worth checking: the TGA ARTG
   bulk export (reported CC BY), and whether AMT (Australian Medicines Terminology) has
   any openly redistributable subset. We know SNOMED CT-AU and the WHO ATC/DDD index are
   **not** redistributable and we are not using them.

### What to give us back

- A clear statement of which licence governs the API, with the source.
- A yes/no on each of the five operations in point 2.
- If yes to committing: the exact attribution and notice text to include.
- Any alternative source with an unambiguous licence.

### Why this matters more than it looks

The project must document every data source's origin, licence, subset and regeneration
method, and must not misrepresent what it used. Getting this wrong in either direction is
bad: over-claiming a licence is a real breach, and under-claiming means we ship a
submission a judge cannot reproduce.

---
---

# Round two

Briefs 1–5 are answered (see `docs/DECISIONS.md`, 24 Oct). These five are the next
highest-value questions, **ordered by how much they change the submission**. Brief 6 is
worth more than the other four combined.

The same rules apply: cite everything, say "not found" rather than filling a gap, and
flag extrapolation from non-Australian sources.

| # | Question | Why it matters | Effort |
|---|---|---|---|
| 6 | Does this synthetic data look real to a pharmacist? | The one thing no amount of code review catches | ~1–2 h |
| 7 | What is the *current* citable basis for our high-risk extensions? | Brief 1 showed ours rests on a superseded 2015 poster | ~1 h |
| 8 | Which differences must **never** be flagged? | Every one we miss is a false positive in the live demo | ~1.5 h |
| 9 | Are the statistics in our 3-minute pitch correct? | A judge in this field will know | ~45 min |
| 10 | Age-stratified medicine utilisation (unfinished from brief 4) | Population realism | ~1 h |

---

## 6. Does this synthetic data look real to a pharmacist?

### Context

**This is the highest-value brief, and it needs a pharmacist or a prescriber rather than
a researcher.** Everything else on this list is a fact to look up. This one is judgement,
and it is the failure mode that no test we write can catch: the code can be perfectly
correct and the data still obviously fake to anyone who reads medication lists for a
living.

**`docs/research/SAMPLE_PATIENTS.md` contains three complete generated patients**,
rendered verbatim — the hospital admission chart, the GP list, twelve months of pharmacy
dispensing, the patient interview, and the errors we deliberately planted. Read those
first; this brief is about them.

We have already found two problems ourselves by looking at that output, which is why we
are asking:

- 35% of patients had a given name contradicting their sex ("Kenneth Lee, F"). Fixed.
- Our lookalike-trap pairs did not share a sex, which made them separable for free.
  Fixed.

Both were invisible in 340 passing tests and obvious in thirty seconds of reading.

### What we need you to tell us

1. **Would you believe these medication lists?** Not "are they possible" — would a real
   80-year-old plausibly be on *this* combination? Name anything that looks wrong:
   - combinations that should not co-occur (we enforce one anticoagulant and one RAS
     blocker per patient; are there other pairs that simply do not happen?);
   - doses or frequencies that are not how the drug is actually prescribed;
   - a medicine that is on the list but would realistically have been stopped;
   - anything *missing* that you would expect alongside what is there — a PPI with
     chronic NSAID use, for instance, or the absence of any analgesia.
2. **Is the dispensing realistic?** We generate roughly 20–40 dispensings per patient per
   year with adherence drawn from a Beta(6, 1.5) distribution, fill intervals jittered,
   and 60-day dispensing for 40% of eligible items. Does the pattern look like a real
   pharmacy record?
3. **Are the planted errors the errors that actually happen?** We plant omission,
   commission, dose, frequency, formulation, duplication, stale GP listing and
   "dose_unconfirmable". For each, is our *example* realistic? Specifically:
   - Is a GP list that still shows a drug ceased 11 months ago the common shape of a
     stale listing, or does it usually look different?
   - Our `dose_unconfirmable` cases are warfarin, insulin and tapering prednisolone.
     Are there others where the dose changes without a new script?
4. **What do we plant that you would not care about?** If a type is technically a
   discrepancy but no pharmacist would act on it, we would rather drop it than report a
   finding that trains people to ignore the tool.
5. **What do we* not* plant that you would most want caught?** Our 11 types come from the
   literature. If the error you actually chase on a ward is missing from that list, that
   is the most useful single thing you could tell us.
6. **The free-text patient interview.** We render medicines as lay terms ("my blood
   thinner", "the water tablet"), brands, generics and vague descriptions ("a little
   white one"), at 25/45/20/10%. Is that the right mix, and are those the words people
   actually use in Australia?

### What to give us back

Prose is fine — a list of "this is wrong because X" is more useful than a table. Rank
them if you can: we have limited time and would rather fix three real problems than
twenty cosmetic ones.

---

## 7. What is the current, citable basis for a high-risk medicines list beyond core APINCHS?

### Context

Brief 1 produced an uncomfortable finding we need to resolve properly.

We classify high-risk medicines by ATC prefix using a 40-row table. Rows 1–33 map to core
ACSQHC APINCHS and are solid. **Rows 34–40 are "extensions"** — digoxin, class III
antiarrhythmics, sulfonylureas, sulfonylurea combinations, clozapine, lithium and
neuromuscular blockers — and brief 1 found that at least two of them rest on a **WA Health
APINCHS poster from August 2015**, while WA Country Health's *current* list (v6.05,
7 October 2026) contains no antiarrhythmics at all.

So our extension rows may be citing a superseded document. We have labelled them honestly
in the data, but "labelled honestly as weakly sourced" is not the same as right, and
these rows decide whether a medicine is high-risk — which drives the single number the
demo leads with.

### What we need you to find out

1. **Which Australian high-risk medicines lists are current as of October 2026?** For
   each: publisher, version, date, and whether it is a *national* standard or a facility
   or state policy. Cover at least ACSQHC, SA Health, WA Health / WA Country Health, NSW
   Clinical Excellence Commission, Safer Care Victoria and Queensland Health.
2. **For each of our seven extension rows, is there a current citable source?**
   digoxin · class III antiarrhythmics (amiodarone, sotalol) · sulfonylureas (gliclazide,
   glimepiride) · metformin/glibenclamide · clozapine · lithium · neuromuscular blockers.
   Name the document and the wording for each one you can support, and say plainly which
   you cannot.
3. **Is there a current list that uses ATC codes directly?** Everything we have found maps
   by drug name, which is why we built the prefix table ourselves. A published
   ATC-based mapping would let us cite rather than construct.
4. **How do these lists treat a medicine that is high-risk only in some circumstances?**
   Prednisolone is our example: not APINCHS, but a tapering course genuinely cannot be
   reconciled from dispensing records. Is there an established way to express "high-risk
   for this purpose only", or did we invent that distinction?
5. **What would a reviewer expect to see?** If we publish "APINCHS recall", does that
   phrase commit us to the core ACSQHC list only? We plan to report core and extended
   recall separately — is that the convention, or is there a better one?

### What to give us back

A row-by-row verdict on our seven extensions (keep / keep-with-weaker-claim / drop), each
with its current citation. Plus a clear statement of what "APINCHS" may and may not be
claimed to cover.

---

## 8. Which differences must *never* be flagged?

### Context

A medication reconciliation tool is judged as much on what it stays quiet about as on
what it catches. Our own rules already say: never flag a brand-vs-generic difference,
never flag a notation difference, never flag the same ingredient at an equivalent daily
dose. The demo deliberately shows "Lipitor" and "atorvastatin" **not** being flagged.

We are about to write the comparison logic, so **this brief directly determines how many
false positives appear in a live demo.** Every pair you give us is one we suppress; every
one we miss is an alert a pharmacist would roll their eyes at.

Our reference table has about 108 products — the full list is
`data/reference_src/medicines.csv`, and the condition bundles are in
`docs/DATA_SPEC.md` §4.2. The known-hard case already in our spec is perindopril:
**arginine 5 mg = erbumine 4 mg**, same drug, different salt, different number.

### What we need you to find out

1. **Salt and ester equivalences** among our products where the *number changes but the
   medicine does not*. Perindopril arginine/erbumine is the one we know. Candidates worth
   checking: metoprolol tartrate vs succinate (we believe these are **not** equivalent
   1:1 — please confirm, because we currently treat them as a genuine discrepancy),
   amlodipine besylate/maleate, bisoprolol fumarate, quetiapine fumarate, venlafaxine
   base vs hydrochloride, desvenlafaxine base vs succinate.
2. **Dose-form equivalences that are not errors.** 2 × 20 mg versus 1 × 40 mg daily is
   plainly the same. Where is that *not* true among our products — where splitting or
   combining a dose genuinely matters (modified-release tablets that must not be halved,
   for example)?
3. **Frequency notations that mean the same thing** in Australian practice: `bd` / "twice
   daily" / "morning and night" / "1 tab bd"; `mane` / "in the morning"; `nocte` /
   "at night". Are there notations we should treat as equivalent that we might not think
   of, and any that look equivalent but are not?
4. **Combination versus components.** If a patient's GP list shows Coversyl Plus and the
   hospital chart shows perindopril + indapamide separately, that is the same therapy
   written two ways — **not** a duplication. But Coversyl Plus *plus* separate
   perindopril **is** a duplication. Is that distinction as clean in practice as it looks,
   and are there combinations where the components are not interchangeable with the
   combination product?
5. **Brand families that are not interchangeable.** Our rule says a brand difference is
   never a finding. Where is that wrong? Narrow-therapeutic-index medicines and
   modified-release products are the obvious candidates — is there an Australian list of
   products where brand substitution is discouraged or flagged (the "a" flag on the PBS,
   for instance)?

### What to give us back

A list of pairs with a verdict: **never flag** / **always flag** / **depends, and here is
the condition**. Concrete products from our list are far more useful than general
principles. If you can only do one section, do section 1 and section 5.

---

## 9. Are the statistics in our three-minute pitch correct and current?

### Context

Our demo opens with claims about the scale of the problem, and closes with a scorecard.
A judge in this field will know whether the opening numbers are right, and a wrong or
stale statistic in the first thirty seconds costs more credibility than it buys.

The claims we currently plan to make:

- **"53.6% of admitted older patients have at least one unintended medication
  discrepancy"** — attributed to Cornish et al. 2005, *Archives of Internal Medicine*.
- **"About 250,000 medicine-related hospital admissions a year in Australia"** —
  attributed to PSA 2019.
- Positioning: a **draft** Best Possible Medication History for pharmacist confirmation,
  consistent with **ACSQHC NSQHS Standard 4, Actions 4.5 and 4.6**, which we describe as
  requiring at least two independent sources.

### What we need you to find out

1. **Is each number stated correctly**, in the right units, from the right study, and
   does it say what we claim? Cornish 2005 is Canadian and twenty years old — is there a
   more current Australian figure we should lead with instead?
2. **The 250,000 figure** — is that the current PSA number, what exactly does it count
   (admissions? presentations? medicine-related problems?), and is there a newer estimate?
   We have also seen a cost figure quoted alongside it; is that sound?
3. **Standard 4, Actions 4.5 and 4.6** — quote the actual wording. Does 4.5 in fact
   require **at least two independent sources** for a BPMH, or is that a common gloss?
   Our entire "BPMH not confirmable" banner rests on that reading, so if it is wrong the
   banner is wrong.
4. **Is "Best Possible Medication History" the correct Australian term**, and are we
   using it the way the standard does? We are careful to call our output a *draft* BPMH
   requiring pharmacist confirmation — is that the right framing, or does the term imply
   something we should not claim?
5. **Anything else in this space a knowledgeable judge would expect us to cite** and
   would notice the absence of.

### What to give us back

For each claim: correct as stated / correct but better phrased as X / wrong, and the
source. Plus the exact Standard 4 wording.

---

## 10. Age-stratified medicine utilisation (finishing brief 4)

### Context

Brief 4 found the PBS volumes we needed but **no age-restricted agent-level data**, so
our prescribing shares are all-ages figures applied to a population aged 60–90. The
consultant noted two directional problems with that: mirtazapine is the 5th most
dispensed medicine in residential aged care and is probably under-weighted, while
venlafaxine and desvenlafaxine appear in the top 10 for women aged 18–39 and are probably
over-weighted for our cohort.

This is the lowest-priority of the five. It affects how believable the population is, not
whether anything works.

### What we need you to find out

1. **Any agent-level dispensing data restricted to 65+ or 70+** in Australia. Worth
   trying: AIHW's medicines and polypharmacy reporting, the PBS "under co-payment"
   datasets, the *Australian Prescriber* top-10 series (does it break down by age?),
   residential aged care medication studies, and the 45 and Up Study.
2. If agent-level data does not exist, **class-level by age** would still help: what
   share of people aged 65+ are on a statin, a PPI, an antidepressant, an anticoagulant?
3. **Condition prevalence by age band** for our 16 bundles, if published Australian
   figures exist. Our bundle weights are currently ordered by PBS utilisation rank rather
   than measured prevalence, which the spec flags as an assumption.
4. **Sex differences worth modelling.** We currently vary only osteoporosis, BPH and
   hypothyroidism by sex. Is that the right set?
5. **Polypharmacy distribution.** We use a mean of 8.4 regular medicines with 34% on ten
   or more. AIHW reports 5+ in 40% of people aged 75+. Is our distribution defensible, and
   is there a published distribution shape rather than a single threshold?

### What to give us back

Whatever age-stratified figures exist, with sources. "No age-stratified agent-level data
is published" is a perfectly good answer — we will say so in the submission rather than
implying a precision we do not have.
