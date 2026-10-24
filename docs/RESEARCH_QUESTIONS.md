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
