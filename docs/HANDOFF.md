# Handoff log

**Append-only. Newest first.** Add an entry at the end of every working session, above
the previous one. Never edit or delete someone else's entry — if something was wrong,
say so in a new entry.

Why it exists: three people on a five-day deadline, working at different hours. The
only way the next person starts from where you left off instead of rediscovering it is
if you write down what broke and what you need.

Copy this template:

```markdown
### YYYY-MM-DD HH:MM AEDT · <name> · <branch>

**Did:**
**Changed shared files:**
**Broken:**
**Needs from teammates:**
**Next:**
```

Fill every field, including the awkward ones. "Broken: nothing" is a useful sentence.
**Changed shared files** means anything a teammate will hit a conflict on or silently
depend on: `app/schemas.py`, `app/config.py`, `.env.example`, `CLAUDE.md`,
`requirements.txt`, `Makefile`, CI. If you changed one, say so here *and* in the PR.

---

### 2026-10-27 · Arnav · arnav/live-examples

**Did:** Re-recorded **`output_examples/live/`** on the batched model calls (#68), with
Nightshift's highest-quality features off. **All five are now `success`.** Every model call
was answered by `nvidia/nemotron-3.5-lightning-30b-a3b`. There are no unanswered calls and
no degradation caveats, and the live findings are identical to sample mode.

| Example | Findings | Seconds |
|---|---|---|
| example_1 | 5 | 453 |
| example_2 | 5 (was `partial`) | 463 |
| example_3 | 0 | 26 |
| example_4 | 1 | 496 |
| example_5 | 1 | 154 |

- **First pass:** example_4 ended `partial`. Its summary call (4096 tokens) came back
  `nemotron…_empty_response` after 142 s, because the hidden reasoning used the whole
  budget. `writer.summarise` now has 8192, and examples 4 and 5 were re-run together, both
  `success`.
- **`scripts/generate_examples.py --only <example …>`** re-records named examples only.
  It refuses example_5 without example_4, because example_5 learns from the verdict
  applied after example_4.
- **`test_live_examples_name_the_nemotron_that_answered`** predated S9. It now requires
  every *answered* call to be `nvidia/*`, and allows a call with no model only in a run
  marked `partial`.

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Watch:**
- **example_4 took 496 s** of the 600 s budget. If Nightshift slows, the S5 time guard
  skips late model steps and the run says `partial`.
- **Example_5's free-text resolution used 7,995 of 8,192 tokens.** It didn't truncate,
  but it was close.

**Needs from teammates:** nothing.

**Next:** S31, S27, then S26, S28, S29.

---

### 2026-10-27 · Arnav · arnav/batch-model-calls

**Did:** Nightshift cuts any call at about 90 s. Even with its highest-quality features off,
the 5-finding critique was cut at 92 s on every run. So the Writer and the critique are
now batched:
- **`MODEL_BATCH = 2`** findings per call (`app/orchestrator.py`).
  - **Writer:** drafts explanations batch by batch (`with_summary=False`).
  - **Summary:** its own short call, `writer.summarise`, which sees each finding's
    headline and statement, not its rows. The S10 summary checks still apply.
  - **Critique:** batch by batch.
  - **Revise:** only the flagged findings, in batches.
  - **Round 2 onwards:** only the revised explanations are re-checked, since the rest
    already passed and haven't changed.
- **Each batch is its own `_llm_step`,** so the time guard, failed-call recording (S9)
  and fallback apply per batch. A failed batch loses only its own explanations, which
  fall back to the template. The degraded caveat is said once per step name, however many
  batches fail.
- **Tests:** 2 in `tests/unit/test_batched_model_calls.py` (mock Nightshift). Example_2's
  calls split 2/2/1 for drafting and for critique, with one summary call. A batch that
  gets a 499 twice costs exactly its 2 explanations, the run is `partial`, and the
  failed call is still listed. `test_summary_verify` now patches `writer.summarise`.
  `output_examples/sample_mode/` regenerated.

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:** nothing. Live `output_examples/` re-record follows.

**Next:** re-record `output_examples/live/` on this code.

---

### 2026-10-27 · Arnav · arnav/s42

**Did:** Scan **S42**, my half (Anshu's Supply section was already on main).
- **Ranking.** `executor.check_shortages` ranks each TGA row against the patient's own
  product. `_patient_products` reads that from the patient's rows for the medicine:
  - lexicon brands named in their `med_text`;
  - strengths, via `parse_strength_mg`;
  - route families, from the statement route and the pharmacy dosage form.

  `_relevance` then decides:
  - **different route or form** (an injection ampoule for a patient on tablets):
    dropped;
  - **same brand**, or the **same strength** when no brand is recorded:
    `relevance: "affects_this_patient"`, with "Check supply of … before discharge";
  - **anything else:** `"other_product"`, one notice each (the UI collapses per
    medicine), and no task.

  `salt_quantity` is never read.
- **Wording.** The detail keeps the sentence the UI parses ("Known shortage listed for X
  (Current, expected to resolve …).") and adds "It matches the patient's product (Endone
  5 mg)." or "The patient's product (…) is a different one."
- **Disclaimer.** It's now said once, as a run caveat (`executor.SHORTAGE_DISCLAIMER`),
  not on every notice.
- **Trace.** It counts what matched, what was another product, and what was dropped.
- **Contract:** **`Notice.relevance: str | None = None`** is a new optional field in
  `app/domain/packs/medtrace/types.py`. The frozen-surface test still passes.
- **Not verified live:** the TGA view isn't registered on my Zetaris, and registering it
  would create objects. The 9 tests in `tests/unit/test_shortage_relevance.py` use rows in
  the export's shape, taken from the scan's examples (ENDONE tablets, an oxycodone
  ampoule, NOXICID, digoxin in micrograms).
- **Guardrail:** `scripts/eval.py --split tune` unchanged: `ALL 145 17 5 precision 0.90
  recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges.

**Changed shared files:** **`app/domain/packs/medtrace/types.py`**, the frozen
MedTrace contract. One additive optional field on `Notice`. Arpon, this is your S42 ask;
shout if you'd rather it lived elsewhere.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Arpon (TGA registered on your machine):** please run P0089 live once and check the
  ranking on real rows. If brand detection misses, the cause is the case of the first
  word in `medicine_name`: a brand is only taken from an all-caps first word.
- **Anshu:** `relevance` arrives top level, as `affects_this_patient` or `other_product`.
  Your `relevanceOf` regexes already map both.

**Next:** my low-priority items (S26–S29, S31). S31 first: repeating the same feedback can
drive trust to 0.

---

### 2026-10-27 · Arnav · arnav/s41

**Did:** Scan **S41**, my half (Anshu had already done the display half and ticked it).
- **Plain wording after unchanged prefixes** in `coverage.py`:
  - "single pharmacy: Only one pharmacy's records found (PHX03). Anything filled at
    another pharmacy won't show here."
  - "single pharmacy: Records from 2 pharmacies found (PHX03, PHX07)."
  - "dispensing incomplete: Some scripts were private (not PBS). Those can be missed or
    matched less reliably."
  - "stale document: GP list last updated 30 Apr 2025, about 18 months ago. It may be out
    of date."
  - **Identity** (no prefix): "A possible match for this patient is waiting for you to
    confirm. Nothing from it is used until you do." It's also used for the paused run's
    coverage; that note used to read "waiting for identity review".
- **Robustness:** the evaluator found stale-GP notes by matching the words "updated" and
  "month". It now uses the `SCOPE_STALE_DOCUMENT` prefix, so wording can change freely.
- **Private scripts, per medicine:** coverage is per source, so the note stays at the
  source level. Whether a medicine had a private script is in its own pharmacy rows
  (`script_type: "private"` in `evidence_index`, since #47).
- **Guardrail:** `scripts/eval.py --split tune` before and after: `ALL 145 17 5 precision
  0.90 recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges.
- 1 test covering every scope note across all 13 recorded patients.
  `output_examples/sample_mode/` regenerated.

**Changed shared files:** none on the list. `app/domain/packs/medtrace/coverage.py` (the
pack, mine under §5): wording only, plus one private constant.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** to show the private-script note only on medicines that had one, show it in
  a pharmacy cell only when that cell's cited rows include
  `evidence_index[row].fields.script_type == "private"`.

**Next:** S42 (rank each shortage against the patient's own product, with `relevance`).

---

### 2026-10-27 · Anshu · anshu/pipeline-hover

**Did:** Powered-by pipeline nodes now light up on hover and keyboard focus, each in its
own agent colour (solid border, tint, soft glow, 1 px lift). Before this, a hovered
node showed only its tooltip. Nodes not used in this mode (Nightshift and Nemotron in
SAMPLE_MODE) stay dimmed but still show their tooltip. With reduced motion there is no
lift. Checked with Playwright: every used node glows on hover. `web/src/styles.css` only.
**Changed shared files:** none.
**Broken:** nothing.
**Needs from teammates:** nothing.
**Next:** demo recording.

---

### 2026-10-27 · Anshu · anshu/ui-cleanup (round 2: app shell, balance, copy, sponsors)

**Did:** second pass on the same branch, `web/` only, presentation only:
- **App shell:** the page itself never scrolls.
  - The sidebar is full height: logo and search at the top, the patient list scrolling
    in the middle with a fade, "This reconciliation" and status pinned at the bottom.
  - Only the right-hand column scrolls.
  - At phone width (≤940 px) the sidebar stacks on top and the page scrolls normally.
  - `html.shot-full` lets the page flow for full-page screenshots;
    `web/scripts/rehearse-demo.cjs` uses it.
- **Balance:**
  - Welcome hero has two columns: text and "The problem" on the left; the four sources
    flowing into MedTrace plus "Start with a patient" on the right.
  - Then three equal cards, four sponsor cards and three demo-patient cards.
  - The Powered-by pipeline wraps in two deliberate rows.
  - The learning card has two columns.
- **Copy audit:** every screen shortened. No restated headings, no "This section shows",
  no marketing words, no exclamation marks. Footer disclaimer and Limitations text
  unchanged. `docs/DEMO_SCRIPT.md` quotes updated to match ("Why held back", the change line).
- **Powered-by sponsor cards on Welcome:**
  - Zetaris (Data), Meterless Nightshift (AI runtime), Meterless engines H-MEM · World
    Model (Engines), NVIDIA Nemotron (Models).
  - Each has a generic line icon in a soft-teal tile, with a teal glow and 2 px lift on
    hover and focus (reduced motion: glow only).
  - No logos are drawn. Official SVGs dropped into `web/public/sponsors/{zetaris,meterless,nvidia}.svg`
    are picked up at build time.
- **Review fixes:**
  - The cell-card and compare wording is now "Current" / "Not current" under a "Read as"
    row (was "Says current" / "Says stopped").
  - Silo status sits left under the icon and name.
  - The MedTrace hub shows "No run yet", "Reconciling…" or "Waiting for identity review"
    instead of empty space.
  - Finding evidence rows are a bordered list with source icons.
  - Welcome caption: "No record in a source means unknown, not stopped".
- **Checks:**
  - 37 Playwright screenshots against SAMPLE_MODE: no page errors, no phone horizontal
    overflow, and the sidebar unchanged at the bottom of a long scroll.
  - Rehearsal clean on a fresh server.
  - `npm run build`, `make test` (835 passed) and the secret scan are clean.

**Changed shared files:** none.
**Broken:** nothing. One test, `test_datasvc.py::test_each_reference_table_serves_a_records_array`,
still skips locally after `make lexicon`: it needs a reference file that `make lexicon`
does not build. That predates this branch.
**Needs from teammates:** official sponsor SVGs, if we want logos in the cards (drop
them in `web/public/sponsors/`).
**Next:** Anshu's review of the screenshots; then the demo recording.

---

### 2026-10-27 · Anshu · anshu/ui-cleanup

**Did:** UI cleanup from my review of the live UI (`web/` only, presentation only):
- **Sidebar:**
  - Stays in view while the page scrolls (sticky, full height, scrolls inside).
  - The patient list has its own scroll area with a bottom fade, so the last name is
    no longer cut off or run into the sections below.
  - A search box filters by name or MRN, with a × button and Escape to clear, and
    "No patients match" when nothing does.
- **Overview tiles:** a fixed-height title row, so every tile's status line sits at the
  same height.
- **Header and footer:**
  - "MedTrace" alone in the brand and the hub tile; no "Synthetic data" badge up top.
  - The footer is one line: "Synthetic data. Not medical advice. A pharmacist must
    confirm every item."
  - The patient header is larger, with MRN, date of birth, sex and admission date as
    label/value pairs.
- **Welcome page:** the default view and the first sidebar item.
  - Contents: the one-line brief, "The problem" (claim 1, cited), how it works with a
    "Start with a patient" button, the four sources, what it checks, it learns,
    Powered by, clickable demo patients and the PLAN §8 Limitations card.
  - Wording only from README, metadata.json and PITCH_CLAIMS. "Why it matters" moved
    here from the patient view.
- **Processing log summaries:** fixed plain-English labels per step, plus counts only
  from structured fields: the planned actions from `TraceEvent.action`, "N sources
  found" from coverage, "N records" from `row_count`. The full message stays under
  "Show details".
- **Live Powered-by pipeline:**
  - Zetaris → Planner · Executor · Evaluator · Writer → H-MEM, World Model →
    Nightshift → Nemotron.
  - Each node is dimmed until used, filled with a count once used, and pulses on the
    current step.
  - Connectors flow while data passes, and the query counter flashes on each new
    query.
  - In SAMPLE_MODE, Nightshift and Nemotron stay dimmed ("not used · sample mode").
  - Click a node to filter the log; click again to clear. Respects reduced motion.
- **Demo script and rehearsal:** updated for the Welcome landing and the pipeline.

**Changed shared files:** none.

**Broken:** nothing.
- Build passes; `make test` 835 passed / 2 skipped; secret scan clean; rehearsal clean.
- Contrast, labels, focus and phone width pass (my Playwright audit). The audit now
  waits for colour transitions before measuring: mid-fade, the browser reports the
  raw `color-mix()` and gave false failures.

**Needs from teammates:**
- **Arnav:** still open from my last two entries:
  - the per-agent `meterless-app` header;
  - S41 wording and S42 `relevance`. The Supply section groups by `relevance` as soon
    as it arrives.

**Next:** demo recording.

---

### 2026-10-27 · Anshu · anshu/final-day

**Did:** My last open scan items (all `web/`, presentation only):
- **S39:** grid-cell cards say what the source says, with a reason read from its cited row.
  - The badge: "Says current / Says stopped / Not in this source / Not reached". It uses
    the API's existence value for that source, then `per_source`.
  - P0089 dapagliflozin, pharmacy: "Last dispensed 24 Oct 2025 (28 days) — ran out
    about 21 Nov 2025; no fills for 11 months."
  - GP: "On the GP list, last updated 30 Apr 2026."
  - Patient: "'Forxiga, one a day' — still taking? unsure."
  - The card opens with `detail.statement` when a finding on that medicine has one.
  - The button is now "This pharmacy record is out of date" (or "This GP daily dose is
    out of date").
- **S41, my half:** scope notes show their `prefix:` as a small label (One pharmacy
  only · Private scripts · Old GP list), one per line, with dates as dates.
- **S42, my half:** a **Supply** section, shown when the API sends shortage notices.
  - The disclaimer appears once, and expected-back dates show as dates.
  - It groups by `relevance` when present: "Affects this patient", then "Other products
    short" per medicine; different route or form dropped.
  - Without `relevance` it lists shortages per medicine and never claims they affect the
    patient. Shortages no longer appear under Notices.
- **Scan:** ticked S39, S41 and S42 (my halves, noted in each).
- **Demo script and rehearsal:** the renamed button is updated.
- **Checks:** build passes; `make test` 835 passed / 2 skipped; secret scan clean;
  demo rehearsal clean.

**Changed shared files:** none.

**Broken:** nothing.
- Supply has only been seen with the mock example (MRN0000001 famotidine): SAMPLE_MODE
  has no recorded shortage data.
- The parser was checked against the exact sentence `app/agents/executor.py` writes.

**Needs from teammates:**
- **Arnav, S41 wording:** the plain sentences after each `prefix:`. Attach the
  private-script note only to medicines that had a private script.
- **Arnav, S42 ranking:** rank TGA rows against the patient's product and put
  `relevance` (e.g. `affects_patient` / `other_product` / `different_route`) and the
  product in the notice. The UI groups by it as soon as it arrives. With `Notice.detail`
  a string in the frozen types, a top-level `relevance` field is easiest; the UI reads
  either.
- **Arnav, still open from my last entry:** the per-agent `meterless-app` header.

**Next:** nothing open in the scan for Anshu. Demo recording.

---

### 2026-10-27 · Anshu · anshu/ui-judges

**Did:** Judge-readiness pass on `web/` (presentation only; every value from the API):
- **Design B, "Calm Workspace":** teal accent, Public Sans, a white sidebar (patient
  list, section links with counts, status) and soft rounded panels.
- **For a 5-second look:**
  - a 3-step flow;
  - a "Four silos, one view" strip;
  - a "Powered by" strip (Zetaris → agents → Meterless engines → Nightshift →
    Nemotron, naming a model only if the API says it answered);
  - a "Why it matters" line using PITCH_CLAIMS claim 1, cited.
- **Learning card:** "System learned 0.70 → 0.50", prominent on the feedback run, and
  on a later run only where its grid shows the changed source disagreeing
  (MRN0000007). Elsewhere a quiet "Earlier feedback on file" line.
- **Findings:** one line each, high-alert first and loudest; full text, a
  side-by-side table (one column per source, highlights from the API's
  `dissenting`/`abstained`) and grouped source records (S38) behind **More**.
- **`detail.by_source` strip (S37):** dose findings lead with `detail.statement` and
  one row per source. It renders from Arnav's S36 (#60), merged here.
- **Grid:** `dose_units` shown after resolved doses; the cell panel opens with the
  same side-by-side table; Technical details IDs on one line with a Copy button.
- **Processing log:** condensed to one line per step (repeats "×n"), full text
  behind "Show details"; a colour per agent (dot plus name) wherever an agent is
  named.
- **Accessibility:** keyboard navigation, focus rings, contrast ≥ 4.5:1, labelled
  controls and phone width all checked with a Playwright script.
- **Scan:** ticked S4, S24, S25, S37, S38 and S40. S4 and S24 already worked
  (`anshu/live-mode`) and are re-proved here.
- **Checks:** main merged (through #60). Build passes; `make test` passed (835 passed,
  2 skipped) after `make synth`; secret scan clean; demo rehearsal clean.

**Changed shared files:** none. `docs/DEMO_SCRIPT.md`, `web/scripts/rehearse-demo.cjs`
and `docs/SCAN_2026-10-25.md` (ticks) changed.

**Broken:** nothing.
- The "once once" duplication text is gone since #50, checked on a fresh SAMPLE_MODE run.
- **After pulling #59 (S35), run `make synth`.** The new generator test reads your local
  gitignored silos and fails on the old ones; rebuilding changes no tracked file.

**Needs from teammates:**
- **Arnav:** Please send the agent name in the meterless-app header
  (hakken-agent/planner, /executor, /evaluator, /writer) in
  app/adapters/meterless.py:255, passing the role the adapter already has for the
  trace, so Nightshift shows a separate job per agent. Experiment: check with one
  live call.
- **Still open for Anshu:**
  - S39 (cell cards: "Says current/stopped" with a reason);
  - S41's display half (strip the `prefix:` from scope notes, show it as a small label);
  - S42's display half.

**Next:** S39, then S41/S42 display.

---

### 2026-10-26 · Arnav · arnav/s36

**Did:** Scan **S36**, plus a retry once on Nightshift HTTP 499.
- **`detail.by_source`** on every dose_unconfirmable, dose, frequency, formulation and
  route finding: `{gp | pharmacy | patient | emr: "<the words as written>"}`. Each value
  comes from the rows the finding cites:
  - **GP:** dose and directions ("as directed").
  - **Pharmacy:** "N fills, latest <strength>, <qty> per <days> days, no dose stated".
    The silo has no directions column, so it says so.
  - **Patient:** their words ("up 2 units every three days").
  - **Chart:** dose, unit (taken from the strength) and frequency ("5 mg variable per
    INR"; insulin "11 units tds with meals").
- **`detail.statement`**, where the detector wrote none:
  - dose_unconfirmable: "No source confirms the current dose: GP as directed · pharmacy … ·
    patient '…' · chart …". When the sources do disagree, it leads with "The sources
    disagree on the dose".
  - Formulation, route and PRN findings: "charted X against Y before admission".
  - Dose and frequency findings keep their existing statement.
- **Template:** dose_unconfirmable now reads "has a dose that changes without a new script,
  so it cannot be confirmed from the records". The old "the sources disagree on" was
  false when no source states a dose. Every template still passes the verifier.
- **Differs from the brief:** this is built in the evaluator (`_what_each_source_says`),
  not in `detect.py`. `detect` sees `MedStatement`s, which keep the parsed dose but not the
  words each source wrote; for the chart, only the generic name. The raw Q2 rows are in
  the evaluator. The scored pack is untouched.
- **Guardrail:** `scripts/eval.py --split tune` before and after: `ALL 145 17 5 precision
  0.90 recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges.
- **HTTP 499 ("Fetch is aborted")** is retried exactly once, outside `MAX_RETRIES`. A
  second 499 is an upstream failure, so it's recorded in `model_calls` (S9) and the step
  falls back.
- Tests: 10 in `tests/unit/test_what_each_source_says.py`, 2 in the adapter tests.
  `output_examples/sample_mode/` regenerated.

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu (S37):** `detail.statement` and `detail.by_source` are live on the
  dose-unconfirmable and chart-comparison cards. `by_source` keys are `gp`, `pharmacy`,
  `patient` and `emr` (label it "Admission chart"). They're in SAMPLE_MODE after your next
  pull, and in Docker after a rebuild.

**Next:** S41 and S42, the backend halves.

---

### 2026-10-26 · Arnav · arnav/s35

**Did:** Scan **S35**. The generator wrote the insulin **concentration** into the chart's
dose: "100 units/mL" became `dose="100.0"` with `dose_unit="mg"`, i.e. "100.0 tds with
meals", 300 units a day.
- **`chart_dose(p, med)`** in `scripts/generate_synthetic.py` returns `dose` and
  `dose_unit` for every EMR row (admission chart, commission, prior discharge):
  - **mass products:** mg, unchanged;
  - **unit-based products** (the two insulins): units per dose, `dose_unit="units"`.
    Glargine is drawn inside its own regimen's range (10–40 units). Aspart is 4–20.
- **Differs from the brief:** the units come from `random.Random("chart-units:<patient>:
  <generic>")`, not from the patient's main `rng`. One extra draw there would shift every
  later value for that patient and rewrite their GP, pharmacy and interview rows. As it
  is, the ground truth is byte-identical, and the only committed fixture change is
  P0006's insulin aspart chart row (`"100.0"` → `"11"`).
- **P0015:** its insulin aspart is an *omission* (not charted), so its card has no chart
  row. Arpon's "100.0 tds" came from the old data. All 44 unit-based EMR rows are now in
  range, and no insulin row carries a mg strength.
- **Zetaris:** `make synth` → `make refresh` (re-cache only; nothing created or dropped)
  → `make verify`: 6/6 patients, 0 mismatches. A live Q3 read returns EMR-000055 as
  `dose 11 · tds with meals` and EMR-000167 as `dose 19 · 10 to 40 units nocte`.
- **Guardrail, `scripts/eval.py --split tune`:**
  - before: `ALL 145 17 5 precision 0.90 recall 0.97 F1 0.93`
  - after: `ALL 145 17 5 precision 0.90 recall 0.97 F1 0.93`
  - High-risk 34/34 and 0 false merges, both times. Held-out not touched; no floor
    changed.
- **`output_examples/`:** none of the five example patients has a unit-based chart row,
  so neither the sample nor the live outputs change. Not re-recorded.
- 1 test in `tests/unit/test_generator.py`.

**Changed shared files:** **`scripts/generate_synthetic.py`** and the committed fixture
`tests/fixtures/medtrace/Q2__P0006.json`.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Everyone with local data:** run `make synth`. If your Zetaris is registered, also run
  `make refresh`, or your silos still have the old insulin doses.

**Next:** S36 (`by_source` and `statement` on the dose findings, for Anshu's S37), plus a
single retry on Nightshift's HTTP 499. S9 (failed calls in `model_calls`) was already
merged in #50.

---

### 2026-10-26 · Arnav · arnav/s17

**Did:** Scan **S17** (the backend half). A `documented_intentional` finding now carries
the chart note that made it intentional:
- `detect.emit` sets `detail["chart_note"]`, using the same note `detect` uses to decide
  intent.
- The evaluator sets `intent_reason` from it.
- Before, `intent_reason` read `detail["reason"]`, which the chart comparisons never
  set, so it was always null.
- **Example_2:** `frequency:oxycodone/naloxone` now has `intent_reason: "withheld:
  hypotension"`, from EMR-000737.
- **Guardrail:** `scripts/eval.py --split tune` before and after is identical: `ALL 145
  17 5 precision 0.90 recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges. Held-out
  was not touched.
- 1 test in `tests/unit/test_orchestrator.py`. `output_examples/sample_mode/`
  regenerated.

**Changed shared files:** none on the list. **`app/domain/packs/medtrace/detect.py`
(Arpon's pack)** gets one additive detail key. No detection logic changed.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu (the UI half of S17):** `Flags.tsx` shows the intent line only when
  `intent_reason` is set. It's now set for this case. The scan also suggests showing
  "Documented as intentional (no reason text)" when it's null.

**Next:** the low-priority items (S26–S29, S31).

---

### 2026-10-26 · Arnav · arnav/s16

**Did:** Scan **S16**. `output.recommendations` used to be the first five task strings,
each with confidence 0.5 and no rationale. Each recommendation now comes from a ranked
finding, in triage order:
- **`text`:** the finding's first task.
- **`rationale`:** its verified explanation.
- **`confidence`:** triage's evidence strength: 0.6 + 0.2 per independent pre-admission
  source it cites, capped at 1 (the `triage.prioritise` formula). In example_2 it's 0.8
  for a one-source finding and 1.0 for the others.

Notice and dose-lane tasks have no honest confidence, so they aren't put in
`recommendations` with an invented one. They're still all in `RunResponse.tasks`. A
zero-finding run (example_3) therefore has no recommendations, and its tasks are
unchanged.
- 2 tests in `tests/unit/test_orchestrator.py`. `output_examples/sample_mode/`
  regenerated.

**Changed shared files:** none (`Recommendation` is unchanged).

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** if the UI reads `output.recommendations`, it now has one entry per finding,
  each with a rationale. The UI's task list should keep reading `tasks`.

**Next:** S17 (documented-intentional findings lose their chart reason). It touches
`detect.py`, so it needs the eval guardrail.

---

### 2026-10-26 · Arnav · arnav/s15

**Did:** Scan **S15**. Free text is resolved only when it names a medicine and the model
is sure.
- **Not identifiable:** a line with more than 2 ingredient candidates and no class is
  never sent to the model. The trace says "names no medicine" and lists the candidates.
  In the five examples this stops only "a little white one" (5 unrelated candidates),
  which is exactly the line the scan named.
- **Not sure:** an ingredient answer below `MIN_RESOLVE_CONFIDENCE = 0.8` is discarded.
  The line stays unmapped, and the trace names the answer and its confidence. The prompt
  now asks for a confidence and states the bar.
- **Differs from the scan:** it suggested adding a confirm task naming the candidates.
  An unmapped line already gets "Identify … with the patient" from S6, so I didn't add a
  second task for the same line. The candidates are in the trace instead.
- 4 tests in `tests/unit/test_free_text_gate.py`, with mock Nightshift answers.
  `output_examples/sample_mode/` regenerated (new trace lines only).

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:** nothing.

**Next:** S16 (every recommendation has confidence 0.5 and no rationale), S17.

---

### 2026-10-26 · Arnav · arnav/s9

**Did:** Scan **S9**, plus Anshu's two text fixes.
- **Failed Nightshift requests now show in `model_calls` and the trace** (rule 3).
  `MeterlessError.calls` carries every request a failure spent:
  - **invalid JSON:** both answered calls, with the model that answered each;
  - **truncated:** `truncated: true`, the model and the completion tokens;
  - **upstream 502 or timeout after retries:** `routed_model: null`, because no model
    answered and none is invented;
  - **failure on the repair:** the first, unvalidated answer as well.

  `_llm_step` records them before falling back. Nothing is recorded when nothing was
  sent (`not_configured`). Before, a step that failed looked as if it had never called
  a model.
- **Anshu's strings:** the duplication template now reads "appears more than once when
  combination products are split into their ingredients". The route log step now reads
  `Planner need "…" -> the Executor runs verified query Q1 on Zetaris, read-only.` (no
  header names).
- **Changed test:** `test_live_nightshift_failure_degrades_visibly` used to assert
  `model_calls == []` on a run where Nightshift answered 502. That was the S9 bug, so it
  now asserts the requests are listed with no model named. Six new tests (five adapter,
  one orchestrator). `output_examples/sample_mode/` regenerated.

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** both strings are fixed. You can clear the "Scene 1, text" and "Processing
  Log" items in `docs/DEMO_SCRIPT.md`; I haven't edited your file.

**Next:** S15 (free-text resolution accepts any candidate), S16, S17.

---

### 2026-10-26 17:40 AEDT · Anshu · anshu/demo-rehearsal

**Did:** Demo rehearsal.
- **`docs/DEMO_SCRIPT.md`:** the 3-minute narration for PLAN §8. External facts are
  word for word from `docs/PITCH_CLAIMS.md`. For each scene it gives the patient,
  the exact clicks and what must be visible:
  - MRN0000015, identity review, then warfarin "Verify before acting";
  - MRN0000089, discrepancies, provenance and actions;
  - MRN0000003 → MRN0000007, the learning pair;
  - the scorecard.
  It also has a sample-vs-live table and a per-scene issues list.
- **`web/scripts/rehearse-demo.cjs`:** Playwright walks that click path against a
  fresh `SAMPLE_MODE` API, screenshots each scene and fails on any page or HTTP
  error. Re-run after merging #47: clean, every MRN0000089 cell cites its record.
- **UI fixes found while rehearsing (presentation only):**
  - the Processing Log footer no longer counts `offline-heuristic` steps as
    Nightshift calls;
  - sub-0.1 s runs read "< 0.1 s";
  - `emr:` record keys keep their MRN in cleaned text;
  - dates read "Sep", not the locale's "Sept";
  - the cell panel's second toggle is now "Query ID".

**Changed shared files:** none.

**Broken:** nothing in the UI. Still wrong in API text, so on screen:
- "appears more than once once combination products are decomposed";
- the identity-resolution log step reads like developer notes ("Bearer key,
  X-Org-ID, fresh X-Request-ID").

**Needs from teammates:**
- Arnav: reword those two strings.
- Everyone: PLAN §8's "false-cessation 0" isn't printed by `eval.py`, so the
  script doesn't say it.
- Scene 2 should be recorded **live**: the header Model pill shows "Not yet called"
  in sample mode.

**Next:**
- Show `dose_units` (from #47) in the grid's reconciled column.
- The `anshu/ui-judges` pass.

---

### 2026-10-26 · Arnav · arnav/s11-s12

**Did:** Scan **S11** and **S12**.
- **S11:** `_guard` now ends with `except Exception`. Any unexpected error (a bug, or an
  odd response shape) ends the run as `status: "error"` with `ErrorInfo(type, message,
  recoverable=False)`, plus an `ERROR` trace event. The event names the exception and
  the last three frames (file:line function), masked with the tracer's secret mask.
  Before, a background run stayed `running` forever and the UI polled until it gave up.
  `POST /run?wait=true` now returns that error response instead of a 500.
- **S12:** a zero-finding run gets a summary. `writer.draft` returns the grounded
  summary when there's nothing to explain. `_offline_summary` says "No discrepancies
  found for <patient> among the sources found; see the notices and tasks." plus the
  coverage banner, deliberately not "nothing to worry about". example_3 (P0013) now
  shows it.
- Tests: an orchestrator test and an HTTP test with the real background thread (S11),
  and a P0013 test (S12). `output_examples/sample_mode/` regenerated.

**Changed shared files:** none.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:** nothing.

**Next:** S9 (Nemotron calls that fail validation are missing from `model_calls`), then
S15–S17.

---

### 2026-10-26 · Arnav · arnav/grid-evidence

**Did:** Anshu's two asks from 12:16.
- **Arnav 1: `evidence_index` now holds every row behind a grid cell.** `analyse` builds
  `Evidence` for each `FusedMed.row_ids` and each attribute's `row_ids`, from the Q2 rows
  already fetched (no extra query), and `_respond` merges them in. On P0001, all 101 grid
  rows are present (78 were missing). The same holds for P0089 and P0015.
- **Arnav 3: dose units.** New optional field **`RunResponse.dose_units`**: generic →
  `"mg"`, `"units"` or `"mL"` for the grid's resolved `daily_dose`. It's read from the
  cited rows the way `parse_strength_mg` reads them: a stated dose in the direction
  first, else the strength. Masses become `"mg"` because the parser converts them, and
  a combination like "25/1000 mg" counts its first component. The field is **absent** when
  the rows state no unit or disagree, so the UI shows the bare number rather than
  guessing. P0001: amlodipine mg, colecalciferol units, empagliflozin/metformin mg.
- 13 tests in `tests/unit/test_grid_evidence.py`. `output_examples/sample_mode/`
  regenerated, so it now carries the new fields. The committed live examples predate
  them.

**Changed shared files:** **`app/schemas.py`**: additive optional field `dose_units`
(default `{}`). No existing field changed.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** show `dose_units[generic]` after the daily-dose value in the grid (e.g.
  "Daily dose: 16 mg"), and nothing when it's absent. Every grid cell can now show its
  provenance from `evidence_index`. The hand-written mock fixtures in
  `tests/fixtures/api/` don't have `dose_units`.
- **Whoever owns `normalise.py` now:** `parse_strength_mg("2 puffs")` returns 2.0. A
  number with no recognised unit defaults to mg, so a puff count can become a "mg/day"
  dose. `dose_units` won't label such a value (it has no stated unit), but fusion still
  compares it as mg. This is a domain change, so it needs the eval guardrail. I haven't
  touched it.

**Next:** S11 (a background run that throws stays `running`), then S12.

---

### 2026-10-26 · Arnav · arnav/s10

**Did:** Scan **S10**. Also ticked **S1** and **S13**, both already resolved by earlier
work, with the evidence noted in the scan doc.
- **The patient summary is no longer shown unchecked.** `evaluator.summary_problems`
  checks it against all of the run's findings:
  - every cited row must belong to some finding;
  - every number must appear in the evidence, the detail, the banner or the patient's
    identifiers and dates, or be one of the counts;
  - no "not taking" while any source is unknown;
  - no instruction to change therapy.

  It runs after the draft, and again after verification if that dropped a finding. A
  failing summary is replaced with `writer._offline_summary`, and the trace records a
  `blocked` event saying why.
- **Instructions are now a code problem in explanations too.** `_INSTRUCTION` flags an
  imperative opening a sentence ("Stop warfarin.") or a modal or advice form ("should be
  reduced", "recommend switching", "consider withholding"). Negations ("do not stop it",
  which the template itself uses) and past tense ("the GP stopped it") pass.
- **Checked against real output:** all four committed live summaries and every live
  explanation pass the new checks. No false positives.
- 11 tests in `tests/unit/test_summary_verify.py`, including a full run in which the
  Writer returns "Stop oxycodone/naloxone now (GP-999999); 987 mg." and the response
  shows the grounded summary.

**Changed shared files:** none. `app/agents/` and `app/orchestrator.py` are mine, and
`app/domain/` is not touched.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:** nothing.

**Next:** S11 (a background run that throws stays `running` forever), then S12.

---

### 2026-10-26 16:30 AEDT · Anshu · anshu/ui-design-a

**Did:** Restyled `web/` to the team's "Clinical Navy" design (design A). The branch also carries `anshu/live-mode` and `anshu/ui-polish`, which were not on `main` yet.
- **Layout:** navy header; patient banner; four summary cards counted from the response; tabs (Discrepancies, Medication History, Actions Required, Source Confidence); identity review in place of the tabs while `needs_review`; a Record Sources sidebar (with data quality notices) and a Processing Log; stacks at phone width.
- **Wording and IDs:** formal wording and enum labels throughout (e.g. Therapeutic duplication, Possibly discontinued, "Unresolved — verify with patient"). API prose is cleaned for display, with the original kept on hover and under "Technical details". Record keys, query IDs, tool names, per-step routed models and the trace path live behind that toggle.
- **From the merged branches:** live mode checked against the `SAMPLE_MODE` API, including the learning demo P0003 → P0007 via grid-cell "Mark … as outdated".
- **Checks:** checked in mock and live mode with Playwright. `make test` 738 passed / 45 skipped; build and secret scan clean.

**Changed shared files:** none on the list. `PROGRESS.md` and `docs/AI_TOOLS_USAGE.md` updated.
**Broken:** nothing in the UI. IBM Plex loads from Google Fonts; offline it falls back to system fonts.
**Needs from teammates:**
- Arnav — still open from my 12:16 entry: `evidence_index` lacks grid rows, so most Medication History cells show "No source record cited". The dose unit is also still missing.
- Note: there is no undo for feedback in the API, so the design's "Undo" button is not shown.
**Next:** demo rehearsal against the `SAMPLE_MODE` API. The UI build in CI still needs a team OK (`.github/workflows/ci.yml`).

---

### 2026-10-26 · Arnav · arnav/s14

**Did:** Scan **S14**. In SAMPLE_MODE, `GET /patients` listed all 200 admissions from Q0,
but only 13 have recorded Q1–Q3. A judge picking any of the other 187 got a replay-miss
error partway through a run.
- `ZetarisClient.replayable()` returns the MRNs that have a full recording (Q1, Q2 and
  Q3). It uses the existing fixture-verified index plus a check that the files exist.
- `Orchestrator.patients()` lists only those 13 in SAMPLE_MODE. `create()` refuses any
  other patient with `UnknownPatient`, which the API turns into a **404** naming the
  recorded patients. Live mode is unchanged and still lists all 200.
- Tests updated (`test_api.py`, `test_orchestrator.py`), plus a new 404 test. A note
  added to the README "Sample mode" section.

**Changed shared files:** none. `PatientSummary` is unchanged: the list is filtered, not
flagged.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** in SAMPLE_MODE the picker now gets 13 patients instead of 200. No UI change
  is needed.

**Next:** the remaining scan items (S9–S13, S15–S17, S20, S26–S29, S31–S33).

---

### 2026-10-26 · Arnav · arnav/docker

**Did:** **The Docker run path is verified**, plus scan **S18** and **S30**.
- **Fresh clone, no `.env`:** `SAMPLE_MODE=true docker compose up --build`. example_2
  succeeds with 5 findings (offline-heuristic). example_1 pauses at needs_review and
  succeeds after `POST /run/{id}/identity`.
- **Live in Docker (`~/Hakken`, real `.env`):** Zetaris connected, and Nightshift is
  online through `host.docker.internal`. example_3 paused, was confirmed, and succeeded,
  with every call answered by `nvidia/nemotron-3.5-lightning-30b-a3b`. The trace landed
  in `./logs`, and H-MEM and World Model state in the volume.
- **Compose fixes** (without them a fresh clone could not run):
  - `env_file` is optional, and `SAMPLE_MODE` comes from the shell, else `.env`.
  - datasvc mounts `./data` read-only (the silos are kept out of the image, so it
    served 503 before).
  - `.state` is a named volume (`hakken-state`): a bind mount of an untracked directory
    is created root-owned on a fresh clone.
- **S18:** `create_app` mounts `web/dist` at `/` when a build exists, after every API
  route. The image builds the UI with `VITE_API_MODE=live VITE_API_URL=`, so it calls
  the API on the same origin. I checked the bundle: no `localhost:8000`, no mock data.
- **S30:** `run.py serve` binds `127.0.0.1` unless `HOST` is set. The image sets
  `HOST=0.0.0.0`, and compose publishes the app on `127.0.0.1:8000` only. datasvc
  stays on every interface: the Zetaris containers reach it through
  `host.docker.internal`, and it serves only synthetic data.
- Three tests in `tests/unit/test_api.py`.

**Changed shared files:** **`Dockerfile`**, **`docker-compose.yml`**, `run.py`, and
`app/main.py` (mine). **`run.py serve` now listens on 127.0.0.1 by default.** If you
reach a host-run API from another machine, set `HOST=0.0.0.0`.

**Broken:** nothing. Unit tests pass. On my machine the compose stack is what's
running now: it replaced the host API server and host datasvc on 8000/8100.

**Needs from teammates:**
- **Anshu:** the image now serves your UI in **live** mode at http://localhost:8000.
  It has never been reviewed against the real API. Your six open questions in
  HANDOFF still stand. Note that `requested_route` in `model_calls` comes from
  `METERLESS_MODEL_FAST`/`_DEEP`: `.env.example` says `meterless/fast`, but
  `app/config.py` defaults to `nvidia/*` ids, which is what a no-`.env` SAMPLE_MODE
  run shows.

**Next:** the remaining scan items. S14 (SAMPLE_MODE `/patients` lists 200 patients,
but only 13 are replayable) is the next one a judge would hit in Docker.

---

### 2026-10-26 12:16 AEDT · Anshu · anshu/live-mode

**Did:** Ran the UI in live mode against the real API in `SAMPLE_MODE` for the first time. P0001, the P0015 identity review → resume (14 rows, 5 findings), and the learning demo P0003 → P0007 all work in the browser, with no page or HTTP errors. Fixes:
- **The learning demo couldn't be done from the UI.** Step 1 rejects a grid value (P0003 candesartan GP dose), not a finding. Click a cell, and the inspector now offers "<source> <attribute> is outdated" on values that disagree or conflict. It sends `grid:<generic>:<attribute>` with `source`/`attribute`.
- `zetaris`/`meterless: "sample_mode"` shows as a blue "sample mode" pill, not a red "down".
- "Other findings" opens when nothing is must-review, so P0007's new dose finding is visible.
- `web/README.md` explains how to run the UI against the `SAMPLE_MODE` API and rehearse the learning demo.

**Changed shared files:** none.
**Broken:** nothing in the UI. **One backend bug, see Arnav 1.**
**Needs from teammates:**
- **Arnav 1 — `evidence_index` only holds rows cited by findings.** `app/orchestrator.py:424` builds it as `{e.row_id: e for f in findings for e in f.evidence}`, but `schemas.py` says it holds "every row cited by a finding **or a grid cell**". On P0001, 78 of the 101 rows behind the grid are missing. The UI therefore marks most present cells "no row" and can't show provenance on hover, which is a PLAN §8 demo beat. The fix is to add the grid's `row_ids` (from the rows Q2 already fetched) to the index.
- Arnav 2 — answered, thanks: the real trace puts what answered in `model` (`offline-heuristic` in sample mode) and the requested model in `route`. The UI already shows it that way.
- Arnav 3 — still open: resolved doses have no unit ("Daily dose: 16.0").
- **The server learns and remembers identity decisions in memory.** Restart it, or use a fresh `STATE_DIR`, before recording the demo, or P0015 won't ask for review and trust starts already lowered.
**Next:** script the 30-second demo rehearsal against the `SAMPLE_MODE` API. The UI build in CI is waiting on a team OK, because it touches `.github/workflows/ci.yml`.

### 2026-10-26 · Arnav · arnav/s23-docs

**Did:** Scan **S23**: the judge-facing docs now describe the code as it is.
- **`docs/ARCHITECTURE.md`**: a mermaid diagram drawn from `app/orchestrator.py`, using
  the trace step names. It shows recall → PLAN → identity (World Model, the review
  pause) → fetch/normalise/free text → analyse → shortages → Writer draft → one Q3
  verify → critique ⇄ revise → template fallback → DONE/PARTIAL, with Zetaris on the
  query steps and Nightshift on the five model steps. Below it: an agents and handoffs
  table, what the engines do in the product, and the boundaries.
- **`README.md`**: the Architecture and Agents sections are filled in (a short
  diagram plus a four-row table: role, model route, handoff). Also fixed the stale
  status lines: the opening banner, the engines row, the speed note (30 s–9 min), the
  Limitations line and `GET /run/{id}/trace`. The H-MEM threshold now states both
  values: the spec's 0.35, and the 0.15 the Planner's recall uses.
- **`docs/SPONSOR_TECH.md`**: the *pending* markers are replaced with what's verified.
  The feature → engine service → test table is filled in, and "What was unique" is
  written.
- **`PROGRESS.md`** and **`TODO.md`**: the "agent layer is all stubs" paragraph is
  gone, the adapters are no longer marked "not yet called", Q4 is no longer marked
  unwritten, and the Phase 2/4 items are ticked.

**Differs from the scan:** S23 said to mark the engines as not yet built. They are
built (8/8 and 13/13) and wired in, so the docs say that instead.

**Changed shared files:** none. All changes are docs.

**Broken:** nothing. Unit tests pass. **The mermaid diagrams were not rendered
locally** (no Node on this machine), so check them on GitHub.

**Needs from teammates:**
- **Anshu:** skim README "Agents and roles" and the Web UI row. I left the UI text as
  "mock mode only, never run against the live API". Update it when that changes.
- **Arpon:** I updated your `queries.py` row in PROGRESS: Q4 is written, and runs only
  if the TGA view is registered. Correct it if that's wrong.

**Next:** the Docker run path check, then the remaining scan items (S9–S18, S20,
S26–S33).

---

### 2026-10-26 · Arnav · arnav/output-examples

**Did:** Scan **S2** and **S34**.
- **`scripts/generate_examples.py`** (`make examples`, `--mode sample|live|both`) runs the
  orchestrator on every input example with fresh in-memory engines. Examples 1 and 3 save
  the paused `needs_review` response, then apply the confirmation `input_examples/README.md`
  documents. Example 4 is followed by the documented verdict (reject the GP daily dose as
  `source_outdated`) and then example 5. Each run writes its RunResponse and JSONL trace,
  plus a README table generated from the files.
- **Committed:** `output_examples/sample_mode/` and **`output_examples/live/`**. Live, every
  model call was answered by `nvidia/nemotron-3.5-lightning-30b-a3b`. Four runs were
  `success`. **example_2 was `partial`**: Nightshift's Writer call got no answer within
  180 s, and the critique returned an upstream `empty_response`. Both steps degraded to
  the grounded template, the caveats say so, and the findings are still verified. Live
  findings match sample findings exactly.
- **`MAX_AGENT_ITERATIONS` default changed 3 → 2**, agreed with Arnav. Three rounds made
  live runs 8–11 min, and one hit `RUN_TIMEOUT_S`. They now take 30–527 s. I also changed
  that one line in my own `.env`.
- **S34:** `make run` now uses example_2. example_1 stops at review.
- `tests/unit/test_output_examples.py`: the outputs differ by input, committed sample
  outputs still match a fresh regeneration, and every live model call is an
  `nvidia/*` model.

**Changed shared files:** **`app/config.py`** (`max_agent_iterations` default 2),
**`.env.example`** (`MAX_AGENT_ITERATIONS=2`) and **`Makefile`** (`run` target). **If your
`.env` was copied from the old template, it pins `MAX_AGENT_ITERATIONS=3`; change it to 2.**

**Broken:** nothing. Unit tests pass, secret scan clean.

**Needs from teammates:**
- **Anyone with a `.env`:** set `MAX_AGENT_ITERATIONS=2` (see above).

**Next:** the remaining scan items (S9–S18, S20, S26–S33), and S23 (the stale judge-facing
docs: README Architecture/Agents TBD, ARCHITECTURE.md, SPONSOR_TECH.md).

---

### 2026-10-26 · Arnav · arnav/s5-s6

**Did:** Three scan items (ticked in `docs/SCAN_2026-10-25.md`).
- **S5, a late timeout kept nothing.** Finished work (analysis, findings with grounded
  explanations ready, the Writer's text, verification, revisions) now lives on `RunState`
  as each stage completes. A `RunTimeout` or `QueryBudgetExceeded` returns **partial
  with the grid, coverage, findings, notices and tasks**. If Q3 hadn't run, a caveat says
  the findings aren't re-verified. **No model call starts with less time left than one
  call may take** (`METERLESS_TIMEOUT_S`): `_llm_step` uses the grounded fallback and
  traces it as `skipped` with its step.
- **S6, unidentified lines vanished.** Every unmapped line ("spray under the tongue") is
  now a notice: `PATIENT_ONLY_ITEM` for the patient, `COVERAGE_GAP` for other sources,
  since `types.py` is frozen. It carries its row, its raw text in `evidence_index`, and an
  "Identify … with the patient" task.
- **S21, ranges read as tablet counts** (`normalise.py`, Arpon's guardrails followed).
  A number or range with a unit is now a stated dose: methotrexate is 2.14 mg/day, not
  5.36. A per-mL concentration is no longer a strength: no more 7500 "mg/day" insulin.
  **Honest caveat:** P0066's false methotrexate `dose_unconfirmable` remains, because the
  pharmacy's qty/days estimate still disagrees. Fixing weekly-regimen inference from
  dispensing is a bigger change, and it's left documented.

**Guardrails:** the scorecard `--split tune` is identical:
`ALL 145 17 5 precision 0.90 recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges.
Held-out was not looked at. 3 new S5 tests. Full suite: 769 passed.

**Changed shared files:** none on the list. `app/domain/packs/medtrace/normalise.py`
changed (private helpers only).

**Broken:** nothing. **The committed `output_examples/sample_mode/` will need regenerating**
after this merges, because S6 adds notices and tasks and S21 changes grid doses. The
output-examples PR does that.

**Needs from teammates:**
- **Anshu:** unidentified lines arrive as notices whose detail starts "Could not identify",
  plus an "Identify …" task. Skipped model steps show as trace events with
  `status: "skipped"`.

**Next:** finish S2: live output examples (generating now), then the output-examples PR.

---

### 2026-10-25 · Arnav · arnav/scan-items

**Did:** Arpon's four main handed-over scan items (TODO_ARNAV §5; ticked there and in
`docs/SCAN_2026-10-25.md`).
- **S8** `metadata.json` now claims what works: adapters, agent loop, API, `run.py`,
  SAMPLE_MODE and both engines, with Docker unverified. Team GitHub handles (taken from the
  repo history) and roles (from PLAN §1) are filled in.
- **S19** `coverage.bpmh_confirmable`: **the admission chart no longer counts as one of the
  two sources.** I fixed the code rather than the README, because the generator's ground
  truth plants `bpmh_not_confirmable` on exactly the EMR-plus-one-source patients (P0013,
  P0056), and ACSQHC 4.5 is about the pre-admission history. example_3 now produces its
  documented outcome, pinned in `test_orchestrator`, and the README caveat is gone.
- **S22** `identity.py`: the identity-review explanation now names the actual other person
  ("…falls in a group of matching records that includes Malcolm Walker (DOB 1965-06-10,
  emr:MRN0000159), who carries a different IHI…"). It says "same name and DOB" only when
  that's true. The mock-mode review fixture is regenerated.
- **S7** `coverage.evidence_state`: an unmapped lay-term line ("spray under the tongue",
  "my blue puffer", "cholesterol tablet") makes that source **UNKNOWN**, not ABSENT, for
  medicines in the class it names. That removes the false GTN conflict on P0007.

**Guardrails, as §5 asks:** the scorecard `--split tune` is identical after each change:
`ALL 145 17 5 precision 0.90 recall 0.97 F1 0.93`, high-risk 34/34, 0 false merges.
`tests/eval` passes. Held-out was not looked at. New helpers are private. Regression tests
are in `tests/unit/test_scan_fixes.py`.

**Changed shared files:** none on the list. **`app/domain/`** changed: `coverage.py`
(`bpmh_confirmable`, plus `_lay_term_covers` used by `evidence_state`) and `identity.py`
(`_ambiguity_reason`). Also `metadata.json`.

**Broken:** nothing. Unit tests pass.

**Needs from teammates:**
- **Anshu:** `bpmh_confirmable` banners now read "Only N of 3 pre-admission sources found".
  The identity-review guard sentence is longer and names the other person.

**Still open from the scan:** handed-over S20, S21, S32, S33 (lower priority), and my own
items S5 and S6 (high), S9–S18, S26–S31. **S2 (`output_examples/` from real runs) is next.**

---

### 2026-10-25 · Arnav · arnav/hmem

**Did:** H-MEM (TODO_ARNAV §4, last item, ticked). **Both Meterless engines are now
implemented, conformance-green and used in the product.**
- **`app/engines/hmem/`** is a Python port of the Meterless reference. **13/13 official
  vectors pass**: `vectors.json` is copied verbatim, with the attribution in
  `tests/engines/vectors/NOTICE.md`. `make conformance` runs 22 checks across both
  engines.
- **The trust the pharmacist teaches lives in H-MEM** (`app/agents/memory.py`).
  - Each `(source, attribute)` prior is an H-MEM record, and fusion reads trust from them.
  - A verdict is `HMEM.feedback()`: exact deltas, a `review` tag on `wrong`, and a ledger entry.
  - **The learning demo now survives a restart.**
  - The verdict itself is remembered; the Planner recalls such memories (`memory_used`),
    and findings cite `hmem_record_ids`.
  - Persisted under `STATE_DIR/hmem` live, in memory in SAMPLE_MODE.
- **Recall threshold is 0.15, not the spec's 0.35**, measured and justified in
  `docs/DECISIONS.md`: absolute scores depend on the mock embedder.
- **Live check:** World Model through the API on my machine. Run 2 of P0015 skipped the
  review because the World Model remembered the decision.

6 feature tests. `make test`: 758 passed.

**Changed shared files:** none on the list. In `app/feedback.py`, trust updates now
return real H-MEM record IDs (`mem-…`) in `hmem_record_id`.

**Broken:** nothing.

**Needs from teammates:**
- **Anshu:** `RunResponse.memory_used` is now populated once a pharmacist has given
  feedback. A small "what memory was used" panel (PLAN 6) would show judges H-MEM working.

**Next:** Arpon's handed-over items (TODO_ARNAV §5): S8 metadata.json, S19 example_3,
S7, S22. Then `output_examples/` from real runs (S2).

---

### 2026-10-25 · Arnav · arnav/world-model

**Did:** World Model (TODO_ARNAV §4, ticked). **Sponsor rule 2's engine half is now real.**
- **`app/engines/world_model/`** is a Python port of the Meterless reference
  (`reference/src/*.ts`, commit `1742dec`). **8/8 official conformance checks**,
  ported one for one to `tests/engines/` (`make conformance` now runs them). It has
  an Apache-2.0 header on every ported file, and `docs/PREEXISTING.md` is updated.
- **`identity.decide` delegates to the engine** (Arpon's planned swap). Following the
  §5 guardrails, the scorecard `--split tune` is identical before and after:
  `ALL 145 17 5 precision 0.90 recall 0.97 F1 0.93`. Skeleton, identity and scorecard tests pass.
- **The user-facing feature** (`app/agents/identity_memory.py`):
  - Every linked record is written as `patient:<source>:<id>` with Zetaris provenance.
  - Confirmed links are `same-person-as` edges, and the medicine fetch reads the
    linked set from the World Model graph.
  - **A pharmacist's identity decision is remembered:** on P0015, run 2 doesn't pause
    for review.
  - Persisted under `STATE_DIR` live, in memory in SAMPLE_MODE.
  - Trace events carry `engine: "world_model"` and `engine_op`.
- The README "Engines used" section and `docs/DECISIONS.md` are updated.

6 feature tests (including survival across a restart). `make test`: 738 passed.

**Changed shared files:** none on the list. **`app/domain/packs/medtrace/identity.py`**:
`decide` delegates, and the two thresholds come from the engine (same values, same
public names).

**Broken:** nothing.

**Needs from teammates:**
- **Anshu:** World Model trace events have `engine == "world_model"`. A small badge in
  the timeline would show judges the engine working.

**Next:** H-MEM and its 13 vectors, wired into feedback so trust persists. Then
Arpon's handed-over items (§5).

---

### 2026-10-25 18:57 AEDT · Arpon · handover (out of credits for the week)

**Did:** (1) Ran a codebase scan of `main` at 3b0a01a. Seven reviewers raised 57 findings and two skeptics checked each one; 55 survived, merged into **34 items by owner** in `docs/SCAN_2026-10-25.md` (#32). (2) Handed every open Arpon item to Arnav: `docs/TODO_ARNAV.md` §5, with guardrails for editing the scored domain pack (#33). (3) Fixed scan S3, the Docker web stage failing on `@fixtures` (#34). `docker build --target web` now succeeds; the full image is still unbuilt on this machine because of slow Docker downloads. (4) Earlier today: TGA cleared and Q4 registered and live-checked (36 medicines with a known shortage), learning demo verified over HTTP, judge-path reproducibility in CI, lexicon consistency for teammates' Zetaris.
**Changed shared files:** none in this batch (`Dockerfile` only).
**Broken:** nothing. Still open: **no Meterless engine or conformance test** (rule 2), and **`output_examples/` is empty** (rule 8). Both are Arnav's, top of the list.
**Needs from teammates:**
- **Arnav:** everything left, in the order given in the prompt Arpon sent you:
  1. World Model + 8 conformance checks, then swap `identity.decide` for it.
  2. H-MEM + feedback, with `memory_used` populated.
  3. `scripts/generate_examples.py` and `output_examples/`: every input, the identity resumes, the learning sequence, and at least 3 live Nemotron runs.
  4. Your scan items S5–S18 and S26–S31.
  5. Arpon's §5 items.
  6. Docs, the full `docker compose up`, and `make validate`.
- **Anshu:** S4 (grid-cell feedback for learning-demo step 1, the item that matters most for the demo), S24, S25. `output_examples/` too, if Arnav hands it over.
**Next:** Arpon is off Claude until his credits reset. He can still run commands Claude is blocked from (Zetaris registration) if asked in chat.

### 2026-10-25 · Arnav · arnav/planner-driven

**Did:** "Option A", as Arnav asked: **the Planner decides what is needed, and the
Executor turns each need into one of Arpon's verified SQL templates.** The model never
writes SQL text.
- **The Planner** returns each step as `{tool, need}`. The `need` is plain words, for
  example "get every medicine line, dispensing and interview answer for those records".
  Core steps (find_identities, fetch_meds, verify) are added by code if the model leaves
  them out, and the trace says so.
- **The Executor** maps find_identities → **Q1**, fetch_meds → **Q2**, check_shortages →
  **Q4**, verify → **Q3**. resolve_free_text uses the lexicon plus a closed-list
  Nemotron choice, with no SQL. **Optional steps run only when planned.**
- **check_shortages (Q4) now actually runs** when planned. Rows become `known_shortage`
  notices, never "unavailable". If the data isn't there (no SAMPLE_MODE recording, or the
  TGA view isn't registered on this Zetaris, as on mine), the step says so and the run
  continues.
- **Every hand-off is traced:** `Planner need "…" -> template Qn -> Zetaris`, then the
  query event with its SQL, `queryId` and the `X-Request-ID` the adapter sent
  (`QueryRecord.request_id`, new).

3 new orchestrator tests (24 in all); unit tests 717 passed.

**Changed shared files:** none on the list.

**Broken:** nothing.

**Needs from teammates:** nothing.

**Next:** World Model and its 8 conformance checks, per Arpon's hand-over order. Then
the handed-over scan items (TODO_ARNAV §5).

---

### 2026-10-25 · Arnav · arnav/api

**Did:** The API and `run.py` (TODO_ARNAV §4, third item, ticked).
- **`app/main.py`:** `POST /run` returns `running` immediately; the run continues on a
  background thread and the UI polls `GET /run/{id}`. `?wait=true` runs it to the end
  first, for curl and tests. Also `POST /run/{id}/identity` (409 if the run isn't
  waiting), `GET /run/{id}/trace`, `GET /status`, `GET /patients` and `POST /feedback`.
- **Startup:** Q_REF and Q0 are read once at startup. `/status` caches its provider checks.
- **CORS** is open for the Vite dev server.
- **`app/feedback.py` (PLAN 5.7):**
  - confirm +0.05; `source_outdated` / `wrong_patient` −0.20 on the named
    `(source, attribute)`; other rejects −0.03.
  - `intentional_change` / `not_clinically_relevant` lower acceptance per
    `(type, atc_class)`.
  - A `grid:<generic>:<attribute>` target covers the abstained-dose case.
  - **The learning demo works end to end over HTTP:** reject P0003's GP dose, GP
    `daily_dose` 0.70 → 0.50, and P0007 resolves rosuvastatin to 10 mg with a dose
    finding. In-process only until H-MEM.
- **`run.py --input <file> [--confirm <candidate>]`** prints the RunResponse; `run.py serve` starts the API.
- **README and `input_examples/README.md`** now claim what works (adapters, agent loop,
  API, SAMPLE_MODE) and nothing more. Engines and Docker are still marked unfinished.

Live server on my machine: `/status` shows Zetaris connected and Nightshift online
(18 routes); `/patients` serves 200 from my Zetaris. 14 API tests. `make test`: 721 passed.

**Changed shared files:** none on the list. The orchestrator gained `create` /
`execute` / `decide` and a `running` snapshot in `get()`.

**Broken:** nothing.

**Needs from teammates:**
- **Anshu:** the live API is ready. `VITE_API_MODE=live`, `VITE_API_URL=http://localhost:8000`.
  - Grid feedback needs `target_id: "grid:<generic>:<attribute>"` plus `source` and `attribute`.
  - **A `source_outdated` reject must send `source` and `attribute`, or it's a 422** (see my 15:06 entry).
  - A live run takes 6–8 minutes, so keep polling.
- **Arpon — please look at example_3 (P0013).** Once the interview is confirmed, coverage
  is EMR + patient found and GP + pharmacy not found. `coverage.bpmh_confirmable()`
  returns **True**, because it counts the EMR chart as one of the two sources, but
  `input_examples/README.md` says example_3 shows **`bpmh_not_confirmable`**. One of the
  two is wrong. ACSQHC 4.5 suggests the chart shouldn't count, but it's your call; I haven't
  touched `app/domain/`.

**Next:** Arnav asked for Planner-driven execution: the Planner's chosen steps decide
what the Executor turns into SQL, including the shortage check (Q4). Then World Model.

---

### 2026-10-25 · Arnav · arnav/orchestrator

**Did:** The orchestrator and all four agents (TODO_ARNAV §4, second item, ticked).
`app/orchestrator.py` runs
`PLAN → FIND_IDENTITY → (NEEDS_REVIEW) → FETCH_MEDS → NORMALISE → RESOLVE_FREE_TEXT →
FUSE → DETECT → PRIORITISE → DRAFT → VERIFY → (CRITIQUE → revise) → DONE | PARTIAL`, with
the pack in `reconcile()` order:
- **Planner** (Nemotron) chooses the optional steps. The core steps are enforced in code.
- **Executor** runs Q1 then `link_identity`. A review-band link pauses the run as
  `needs_review`, and `resume()` continues it. Then Q2 on the confirmed set only, with
  rows filtered to those records; normalising; and one batched Nemotron call for
  unmapped lines, **choosing only from `llm_candidates`**.
- **Evaluator** runs fuse → detect → `safety_gate` → prioritise. It fills the grid's
  `high_risk_class`, adds the `forced_confirm` dose lane for every current medicine, and
  produces the notices. Then **one Q3 re-reads every cited row**, a code check blocks
  invented numbers, foreign rows and "not taking" over UNKNOWN, and a Nemotron critique
  returns a faithful/unfaithful verdict per finding.
- **Writer** (Nemotron) writes all the explanations and the summary in one call. The
  grounded template is used offline, and wherever the code check **or** the model's
  verdict still objects after the last round. Live, the model caught "40 mg 1 bd (once
  daily)", which every number check had passed.
- The run is bounded by the 8-query budget, `RUN_TIMEOUT_S` and `MAX_AGENT_ITERATIONS`.
  A Nightshift failure in live mode degrades visibly: a caveat, trace status
  `degraded`, run `partial`.
- The JSONL trace goes to `logs/` with secrets masked. 21 orchestrator tests.

**Results:**
- **SAMPLE_MODE matches `input_examples/README.md` exactly:** P0089 (example_2),
  P0015 (example_1: pauses for review, then warfarin and insulin aspart), P0001 (its two
  planted omissions). Three queries per run.
- **Live P0089 on my machine:** every model call (Planner, Executor, Writer, Evaluator)
  was answered by `nvidia/nemotron-3.5-lightning-30b-a3b`, and all 5 findings were
  verified by Q3.
- **Fixed from the live runs:**
  - Token budgets were raised after empty-response 502s; retries are now visible as
    `retry_count`.
  - The critique was too eager: asked for "problems", it restated the findings
    themselves, so it now returns per-finding verdicts.

**Plan vs repo:**
- **SAMPLE_MODE Q3** is answered from the patient's recorded Q2 and Q3 envelopes,
  because the committed Q3 fixtures hold only the planted rows. That's in
  `docs/DECISIONS.md`.
- **Arpon:** re-recording Q3 for the rows a run actually cites would remove the need
  for this.

**Changed shared files:** none on the list. `app/adapters/meterless.py` gained
`ChatResult.attempts`.

**Broken:** nothing. 700 unit tests pass, secret scan clean. **Speed is the open issue:**
a live run takes 6–7 minutes. Nemotron spends 30–60 s per call on hidden reasoning, and
the Zetaris share is about 15 s. That's inside the 10-minute limit, but slow for the demo.

**Needs from teammates:**
- **Anshu:** `RunResponse` from the real orchestrator has the same shape as the
  fixtures. Once the API lands (next), `VITE_API_MODE=live` should just work. Notices
  come from the pack, so a run may show fewer notice types than the mock.

**Next:** the API (`POST /run`, `GET /run/{id}`, `POST /run/{id}/identity`,
`GET /status`, `GET /patients`, `POST /feedback`) and `run.py`. Then World Model.

---

### 2026-10-25 15:55 AEDT · Arnav · arnav/zetaris-adapter

**Did:** The Zetaris adapter, `app/adapters/zetaris.py`.
- **`ZetarisClient.run(sql, template_id, replay_key)`** follows the binding call shape
  (REFERENCE_NOTES 1.1) and **passes the envelope on untouched**: strings stay
  strings, NULL stays `None`.
- **Read-only guard:** SELECT, SHOW, DESCRIBE or WITH, one statement. Quoted text is
  ignored, so `'stop; then DROP'` in a literal is data. Every real template passes it.
- **A result that reaches its row limit is refused rather than silently truncated.**
- **Retries:** bounded, on connection errors and 5xx only. Never on 4xx or a timeout.
- **`RunQueries`** is one run's budget: `MAX_ZETARIS_QUERIES_PER_RUN` = 8, then
  `QueryBudgetExceeded`. It records template, SQL, ms and rows for every query, failed
  ones included.
- **`load_lexicon(client)`** reads Q_REF through the adapter, once per process, not
  counted against any run.
- **SAMPLE_MODE replays `tests/fixtures/medtrace/`** by EMR MRN. The MRN → `P00nn` index is
  built from the fixtures themselves: a file is indexed only if its own rows contain that
  MRN. No ground truth is read, because it's gitignored and absent in Docker. A missing
  fixture raises `ReplayMiss` and never guesses. This is cached Zetaris *data* (diffed
  identical to live), not model text, so it's consistent with the README.

41 tests. Live on my machine: `SELECT 1` and `SHOW LIGHTNING DATABASES` through the
adapter. The MedTrace views are **not** registered on my Zetaris, so I'm staying on
fixtures as agreed.

**Note for the orchestrator (me, next):** a SAMPLE_MODE Q2 replay returns the recorded
rows for that patient whatever links were confirmed. Filter rows to the confirmed
`record_key`s after `rows_from_sql`, and filter Q3 to the requested `row_id`s. Otherwise
a rejected identity link would still contribute medicines in sample mode.

**Changed shared files:** none on the list.

**Broken:** nothing. Unit tests green, secret scan clean.

**Needs from teammates:**
- **Arpon:** when you want me live on MedTrace data, say so and I'll run
  `register_sources.py` (dry run first, with your go-ahead) on my own Zetaris.

**Next:** the orchestrator, wired to the pack in `scripts/eval.py:reconcile()` order,
with the Writer as the first real Nemotron call.

---

### 2026-10-25 15:30 AEDT · Arnav · arnav/meterless-adapter

**Did:** The Nightshift adapter, `app/adapters/meterless.py` (TODO_ARNAV §4, first item, ticked).
- **`status()`** decides from `GET /v1/models`: unauthorized ≠ offline.
- **`chat()`**:
  - `DEFAULT_MAX_TOKENS` 8192, and refuses anything below 512.
  - **Truncation is caught by the token count** (`completion_tokens >= max_tokens`
    raises `TruncatedResponse`), never by `finish_reason`.
  - The receipt is captured defensively. `routed_model` comes from `receipt.routed_model`,
    then `winning_route.model`, then `response.model`, never from `provider_model`.
  - Bounded retries on connection errors and 502/503/504 only; a 401 or a timeout is never retried.
- **`chat_json()`**: schema instruction, pydantic validation, exactly one repair retry.
- **`auto_detect()`**.
- `ChatResult.model_call()` and `.trace_fields()` give the orchestrator its `ModelCall`
  and `TraceEvent` fields.

**Verified live on my machine:** status online with 18 routes; plain text and
schema-validated JSON both answered by `nvidia/nemotron-3.5-lightning-30b-a3b`.
Real responses are recorded in `tests/fixtures/meterless/`: bodies only, no token, and
two secret-shaped build hashes redacted after the pre-commit scan caught them. 33 tests,
all on a mock transport.

**Plan vs repo:** my brief said SAMPLE_MODE should *replay recorded responses*. The
README and TODO.md promise judges an `offline-heuristic` that **never replays saved
model text**, so I followed the repo:
- In SAMPLE_MODE the adapter never touches the network. Each call site supplies an
  `offline` function, and the result is recorded as `offline-heuristic`.
- The recordings are parser fixtures only.

Logged in `docs/DECISIONS.md` with the live observations: routes are still coerced, this
runtime also lists `local-runtime/*` models (so `meterless/auto` *could* answer with a
non-Nemotron), and a one-sentence answer cost up to 1,494 completion tokens.

**Changed shared files:** none on the list.

**Broken:** nothing. 641 passed / 6 skipped, secret scan clean.

**Needs from teammates:** nothing blocking.
- **Arpon:** on your runtime, does `meterless/auto` ever route to a local model? Mine
  lists `local-runtime/*`. If yours does, the NVIDIA story needs a pinned Nemotron route.

**Next:** Zetaris adapter, then the orchestrator with the Writer as the first real
Nemotron call.

---

### 2026-10-25 15:10 AEDT · Arpon · arpon/tga-on

**Did:** (1) **TGA cleared** by the consultant for non-commercial hackathon use. `datasvc` serves `/ref/tga`, the docs record the ruling, and `register_sources.py --with-tga` also works with `--refresh`. Restarted Arpon's local `datasvc` so it serves the route. (2) **Identity evidence has a verdict prefix** for Anshu's UI: `agrees:` / `partial:` / `differs:` / `held:` at the start of every `field_evidence` sentence, from the score itself. (3) Repo stays public (team decision).
**Changed shared files:** none on the list.
**Broken:** **Q4 is not registered in Arpon's Zetaris yet.** The agent's permission check blocked creating Zetaris objects, so Arpon runs `.venv/bin/python scripts/register_sources.py --apply --skip-exists --with-tga` himself. Until then a live `q_shortages` call fails with an unknown view.
**Needs from teammates:** Anshu — colour identity fields from the prefix (`value.split(": ", 1)[0]`, one of `identity.EVIDENCE_VERDICTS`) instead of the keyword regex in `IdentityReview.tsx`; `partial` deserves its own colour. Arnav — real runs now produce prefixed evidence, so hand-written `field_evidence` in `tests/fixtures/api/` will differ until they are regenerated from runs. Q4 is available for a `check_shortages` step; render rows as "known shortage", never "unavailable".
**Next:** nothing on Arpon's side after the registration command.

### 2026-10-25 15:06 AEDT · Arnav · arnav/schema-review

**Did:** TODO_ARNAV section 2, ticked in that file.
- **`Finding.detail`** passes `DiscrepancyCandidate.detail` through (`atc_class`,
  `conflict`, `bpmh_single_source`, `subtype`, `statement`, `daily_dose_ratio`).
- **`FeedbackRequest.source` / `.attribute`**, vocabulary-checked (`Source`,
  `TrustAttribute`), **both required when `reason == "source_outdated"`**.
- **Example API JSON regenerated** against the 25 Oct data:
  - `detail` is on every finding.
  - P0001's overlay rows (`PHM-000076`–`078`) no longer exist, and its interview name is now "Marj".
  - `patients.json` now comes from the real Q0 fixture: the 13 replayable patients.
  - The feedback example uses the learning-demo record `("gp", "daily_dose")` 0.70 → 0.50, with no acceptance update.
- **The needs-review example is now P0015** (`input_examples/example_1`). Since the
  25 Oct data, P0002 links straight through with no review. The file keeps its name
  `run_P0002_needs_review.json` because `web/src/api.ts` imports it. The UI keys on
  `patient_id`, so it picks P0015 up automatically.

Order going forward, agreed with Arnav: the repo's TODO order, not the original
5.2-first list. Meterless adapter → Zetaris adapter → orchestrator / API / `run.py` →
World Model (in this window, no second session) → H-MEM.

**Changed shared files:** **`app/schemas.py`** (`Finding.detail`, `FeedbackRequest.source`,
`FeedbackRequest.attribute`, plus a validator).

**Broken:** nothing on `main`. Unit tests 600 passed / 5 skipped. **One live-mode break is waiting in
the UI, see below.**

**Needs from teammates:**
- **Anshu** — (1) Add `detail: Record<string, unknown>` to `Finding`, and `source?` /
  `attribute?` to `FeedbackRequest`, in `web/src/types.ts`.
  (2) **`Flags.tsx` defaults `reason` to `source_outdated` and `App.tsx` sends only
  `reason`.** Against the live API that is now a 422. A `source_outdated` reject has to
  send `source` (one of the finding's evidence sources: let the pharmacist pick) and
  `attribute` (`daily_dose` for dose and dose_unconfirmable findings, `existence` for
  omission and commission is a reasonable default). Mock mode is unaffected.
  (3) Render `detail.conflict === "confirm"` as *ask first*, and `detail.statement` when
  present.
- **Arpon** — nothing new. The schema review asks from #12 are both done. Structured
  `Task` is deferred: `list[str]` for the demo.

**Next:** Meterless adapter (Nightshift).

---

### 2026-10-25 15:28 AEDT · Anshu · anshu/ui-review

**Did:** Reviewed the merged UI (#22) against PLAN §6, one item at a time. All 10 items done:
- Header shows `GET /status` only.
- Picker handles load, empty and error states, and clears results when you switch patient.
- Timeline survives a dropped poll.
- Identity review runs end to end in mock mode, ending on a labelled placeholder.
- The BPMH banner heading appears only when `bpmh_confirmable` is false.
- The grid flags any present cell that has no cited row.
- Flags follow #23: `detail` is rendered ("Ask first" for `conflict: confirm`), a `source_outdated` reject sends `source` + `attribute`, and there is no default reject reason. Bodies were checked against `FeedbackRequest`.
- Each task names the finding or notice it came from; ticks are labelled screen-only.
- Trust panel: a feedback "after" value only overrides `run.trust` in the run it was given on, so patient B shows its own trust (learning demo). A "What your feedback changed" box sits at the top.
- Disclaimer pill in the header; the API's caveats sit with the result, not in the footer.
- Identity colours come from Arpon's `agrees`/`partial`/`differs`/`held` prefix (#24), with the keyword guess kept only for the unprefixed examples.
- Followed #23: `types.ts` has `Finding.detail` and `FeedbackRequest.source`/`attribute`; the mock placeholder was regenerated for MRN0000015.

**Changed shared files:** none.
**Broken:** nothing. Branch not on GitHub yet: Claude's push gets 403, so it goes up by bundle like #22.
**Open questions for Arnav** (none blocking):
1. Confirm `TraceEvent.model` is always the routed (answering) model, not the requested route. The timeline labels it "answered by". If it can hold the route, send the `meterless` receipt, which the UI prefers.
2. **Resolved doses need a unit.** `FusedValue.value` is a bare number ("Daily dose: 40"); `types.py` says "canonical units" but no field names them. The UI will not print "mg" itself (insulin is in units). Add a unit, e.g. `unit` on `FusedValue`, or send the value as text with its unit. Until then the grid shows the bare number.
3. Every `present` cell should cite at least one row. Warfarin's admission-chart and patient-interview cells cite none in both P0001 examples, so the grid marks them "no row".
4. The cell inspector shows `sql_template_id`, not the SQL text. If PLAN 6.6 means the query itself, `Evidence` needs it.
5. A real resumed-run example (after `POST /run/{id}/identity`) would replace `web/src/placeholders/resumed_run.PLACEHOLDER.json`. It can't go in `tests/fixtures/api/` without updating `test_api_fixtures.py`'s file list.
6. **Task order.** `RunResponse.tasks` arrives in alphabetical order, which buries the warfarin and oxycodone tasks mid-list. Ordering by the priority of the finding each task comes from would put high-risk ones first. The UI won't re-sort them itself, since that would mean the screen deciding what matters most. Each task now shows its source finding and badges.
**Next:** push via bundle and open the PR. Then `VITE_API_MODE=live` as soon as Arnav's `POST /run` lands, and rehearse the 30-second demo arc in mock mode.

### 2026-10-25 14:34 AEDT · Arpon · arpon/judge-path

**Did:** Applied the fresh-clone audit. `make lexicon && make synth` on a clean clone used to rewrite 21 committed fixtures and fail 2 tests. It now reproduces them byte for byte (the generator falls back to the committed lexicon). CI runs that build and `git diff --exit-code`, so the scorecard tests run in CI instead of skipping. Also: honest `make examples`/`validate`/`conformance`, README Quickstart (Docker labelled not working yet, data build documented), `python3` in the docs, `metadata.json` status and pre-existing components, `.dockerignore`, pip timeout in the Dockerfile, `.env.example` PBS comment.
**Changed shared files:** **`Makefile`** (`test` drops the duplicate `-q` so the summary prints; `conformance`/`examples`/`validate` print "not implemented yet" and exit 2 until their scripts/tests exist — they run normally once they do), **`.github/workflows/ci.yml`** (new data-build + reproducibility step before tests), **`.env.example`** (comment only). Also `Dockerfile` (env var) and a new `.dockerignore`.
**Broken:** nothing. CI is slower now, because the scorecard actually runs.
**Needs from teammates:** Arnav — `make examples` and `make conformance` start working automatically once `scripts/generate_examples.py` and `tests/engines/test_*.py` exist. The `.dockerignore` excludes `data/reference/` and `data/synthetic/silos/`, so the image relies on `tests/fixtures/medtrace/` for sample mode, as planned.
**Next:** nothing pending on Arpon's side except the TGA licence answer.

### 2026-10-25 14:24 AEDT · Arpon · arpon/background-1-4

**Did:** (2) `scripts/eval.py --json` and a false-merge count (0/286 held-out, 0/280 tune). A scorecard dashboard was built from that run's JSON (link in chat), for the pitch. (3) Data docs audited: `DATA_SOURCES.md` rewritten (it still said "none registered yet"). `DATA_LICENCES.md` corrected: 108 products; the desvenlafaxine ATC exception; the committed PBS values in `Q_REF__lexicon.json` now have `PBS_COPYRIGHT.txt` beside them. `PREEXISTING.md` TGA row updated. (4) Q4 `q_shortages` written, tested in SQLite, and its dialect checked live, read-only. **Switched off**: TGA licence unconfirmed (`DECISIONS.md`).
**Changed shared files:** none on the list.
**Broken:** nothing. Fresh-clone audit (item 1) is still running; its fixes follow in a separate PR.
**Needs from teammates:** Arnav — Q4 exists if you want a `check_shortages` tool step, but it returns nothing live until the licence is confirmed. Don't register it yourself.
**Next:** apply the fresh-clone audit's fixes; get the TGA licence answered.

### 2026-10-25 14:11 AEDT · Anshu · claude/modest-feynman-dc14du

**Did:** Built the web UI in `web/` (Vite 5 + React 18 + TypeScript, plain CSS): all ten PLAN §6 items in mock mode.
- Header pill (Zetaris, Nightshift, last routed model, MOCK/SAMPLE_MODE).
- Picker + Run.
- Polled live timeline. A blocked verifier claim is shown in red, and each model step shows its routed model; there is also a model-calls table (requested route → answered by).
- Identity review side by side, with Same person / Different people.
- Coverage strip + BPMH banner.
- BPMH grid, where unknown is hatched purple "?" and absent is grey "○". Dissenting cells are outlined, and abstained attributes read "Conflict: ask patient". Hover or click a cell to see its rows from `evidence_index` (source, `row_id`, original text, template, query id).
- Flags: Must review first (high-risk first), then the rest and documented-intentional items collapsed. Confirm / Reject + six reasons go to `POST /feedback`.
- Tasks, notices, a trust panel showing before → after with the delta, and the footer disclaimer.

`VITE_API_MODE=mock|live`. Mock mode replays `tests/fixtures/api/` and never invents data: there is no example for a resumed identity run or other patients, and it says so on screen. `web/README.md` documents the mock scenarios. Checked with Playwright screenshots of every state; no console errors.
**Changed shared files:** none on the list. `README.md` "Not finished" and Limitations now say the UI exists but has only run against example responses. `PROGRESS.md` UI row updated.
**Broken:** **the branch is not on GitHub.** Push failed with 403 (Claude has no access to `poj1738/Hakken` from this session), so the claim and the UI exist only in this cloud session until access is fixed. `npm run build` is not in CI (CI is Python-only; adding a Node job means editing `.github/workflows/ci.yml`, a shared file, so I left it).
**Needs from teammates:**
- Arnav — (1) `POST /run` should return a `RunResponse` with `run_id` and `status: running`; the UI then polls `GET /run/{id}`. (2) A resumed-run example after `POST /run/{id}/identity` would let mock mode show the second half of the identity scene. (3) `run_P0001_gp_not_found.json` shows warfarin GP = `unknown` but still lists `gp: "5 mg"` under `dissenting`; the UI shows both as given. Worth fixing in the fixture.
- Arpon — `IdentityLink.field_evidence` is free text, so the UI colours agree/differ by keywords in the matcher's sentence ("differs", "swap", "typo" → differs; "match" → agrees). A structured per-field verdict would be sturdier, but `types.py` is frozen, so this is only a suggestion.
**Next:** push once GitHub access works, open the PR, then switch to `VITE_API_MODE=live` when the API lands.

### 2026-10-25 14:02 AEDT · Anshu · claude/modest-feynman-dc14du (claim)

**Did:** Claiming the **web UI** (PLAN §6, items 1–10): Vite + React + TypeScript in `web/`, `VITE_API_MODE=mock|live`, mock mode replaying `tests/fixtures/api/*.json`. Nobody else should start on `web/`.
**Changed shared files:** none.
**Broken:** nothing yet — claim only.
**Needs from teammates:** nothing yet.
**Next:** header + status pill, picker + Run, timeline, then the grid, flags, tasks, trust panel.

### 2026-10-25 13:47 AEDT · Arpon · arpon/track-1

**Did:** Recorded the team's **Track 1** choice in `metadata.json` (track, one-liner, Zetaris status, data sources), `README.md`, `TODO.md` (track and data decisions ticked, Phase 3 ticked) and `PROGRESS.md`, plus a superseded note on `docs/AGENT_KICKOFF.md`. Rewrote the README's stale status sections ("only two things are built") to state honestly what works and what does not.
**Changed shared files:** none on the list.
**Broken:** nothing.
**Needs from teammates:** Arnav and Anshu — the README's "Not finished" list is your layers. Tick items off there as they land, so the README never claims more than the code shows.
**Next:** Arpon waiting on Arnav's answer about which of his pieces to take.

### 2026-10-25 13:39 AEDT · Arpon · arpon/demo-data

**Did:** Demo data. (1) **The learning demo had no patient B.** Under one GP-dose rejection, no replay-set patient changed. Staged a pair (`LEARNING_PAIR`: P0003 teaches, P0007 learns). Both abstain at the priors. After −0.20 on GP `daily_dose`, both resolve to the pharmacy dose, and P0007 gains a dose finding (its chart copied the stale GP dose). No rng, no new rows: every other patient is byte-identical. Recorded in the ground truth as `learning_demo`. Pinned by `tests/unit/test_learning_demo.py` on the replay fixtures (runs in CI). (2) **Showcase replay fixtures** for P0013, P0015 and P0089, plus **5 `input_examples/`** with a README saying what each correct run shows (rule 8). (3) **Dockerfile copies `tests/fixtures/medtrace/`**: `SAMPLE_MODE` in the image had nothing to replay. Live Zetaris re-cached (`make refresh`, `make verify` green), and the staged values confirmed by `row_id`.
**Changed shared files:** none on the list. `Dockerfile` changed (one `COPY` line) — called out here and in the PR.
**Broken:** nothing. Tune now 145 TP / 17 FP / 5 FN, F1 0.93: the extra miss is P0007's staged chart error, which the system can only see after feedback. That is the demo. Held-out untouched.
**Needs from teammates:** Arnav — the box at the top of `docs/TODO_ARNAV.md` now says **landed**. Recording outputs is unblocked. Your H-MEM `source_outdated` delta must reach `fuse` as `trust[("gp", "daily_dose")]`; `test_learning_demo.py` is the acceptance test. Anshu — the demo order is example_4 then example_5 (`input_examples/README.md`).
**Next:** nothing on Arpon's side. Pick up whatever is handed back here.

### 2026-10-25 13:14 AEDT · Arpon · arpon/loose-ends

**Did:** Closed Arpon's last loose ends. (1) `coverage()` measured GP-list staleness against `date.today()`, so a fixed dataset changed its answer as the calendar moved; it now measures from the admission chart, the newest document (frozen signature has no `as_of`). Test added. (2) `scripts/eval.py` reports high-risk recall **split core APINCHS vs extended**, as the 24 Oct consultant ruling asked — pooled, a weak extension row moves a number that reads as ACSQHC compliance. Held-out: **core 30/32 [0.80, 0.98], extended 5/5**; tune core 27/27, extended 7/7. Scores otherwise unchanged. (3) PROGRESS "Waiting on Arpon" was stale: sotalol, bundle 6 and the formulation pairs were all decided and applied 24 Oct — verified in `medicines.csv` and struck off.
**Changed shared files:** none.
**Broken:** nothing. Both held-out high-risk misses (P0123 insulin aspart, P0174 temazepam commissions) are core APINCHS — still recorded, still not tuned against.
**Needs from teammates:** Arnav — `docs/TODO_ARNAV.md`, unchanged. Quote core-APINCHS recall (30/32), not the pooled 35/37, anywhere it reads as ACSQHC compliance.
**Next:** Arpon's section is done. Pick up whatever Arnav or Anshu hand back here.

### 2026-10-25 12:30 AEDT · Arpon · arpon/population (green — supersedes the entry below)

**Did:** The entry below is resolved. Then applied the consultant's review of the
detector (briefs 11–14), restored the population to 200, refreshed Zetaris and
reviewed Arnav's schema. Every test green, secret scan clean.

**Held-out (200 patients): precision 0.95, recall 0.95, F1 0.95, high-risk 35/37.**
The full table and what changed per brief are in `docs/DECISIONS.md` (25 Oct,
"Consultant rulings…"). Three things matter most:
- `dose_unconfirmable` is now a finding only on visible conflict. Routine dose
  confirmation is the `safety.forced_confirm` task lane.
- A lapse alone is a `conflict: confirm` item, never an asserted commission.
- **DATA_SPEC's 100% high-risk recall is not met on held-out.** The two missed
  commissions are recorded, not tuned against.

**The two red tests** were sample-sensitive, not regressions. Each now tests its
real property exactly, with no floor lowered:
- 82 of 82 resolvable patient descriptions resolved.
- The blank-IHI format check now looks across all fixtures.
- The population-level free-text figure (0.847) moved to the scorecard.

**Zetaris is current at 200 patients and no slower**: Q1–Q3 run in 2–3 s,
`all_sources` holds 13,856 rows, the fixture diffs match, and Q0 is identical
(1,326 rows).

**Schema review for Arnav:** posted on #12. **Two additions are needed**:
- `Finding` needs `detail` / `atc_class` — without it `POST /feedback` cannot key
  learned acceptance, and the UI cannot show `conflict: confirm` or an
  unverified-BPMH flag.
- `FeedbackRequest` needs `source` + `attribute` so `source_outdated` can lower
  the right trust record.

**Changed shared files:** none. `safety.DOSE_CHANGES_WITHOUT_A_SCRIPT` and the
`trust` priors changed value, not shape.

**Broken:** nothing.

**Needs from teammates:** **Arnav — read `docs/TODO_ARNAV.md` first.** It holds the two schema additions, the `forced_confirm` task lane and the pipeline order, in priority order.

**Next:** merge this; then back to whatever helps the agent layer most.

---

### 2026-10-25 10:40 AEDT · Arpon · arpon/population (NOT merged — 2 tests red)

**Did:** PR #14 merged (domain pack complete). Then raised the population to
**200** (DATA_SPEC's number; default changed in the generator) and re-scored.

**Held-out at 200 patients: precision 0.87, recall 0.97, F1 0.92, high-risk 25/26**
(simulated review); no human review: F1 0.88. Tune: 0.91, high-risk 22/22. At 40
patients the biggest error source was invisible: `dose_unconfirmable` was 21 of 32
false positives at 200. It now fires when the sources show a phone change ("as
directed per INR", disagreeing doses) **or** no patient states a regular dose; where
the patient confirms, the duty is the `safety.forced_confirm` task, not a finding.
Also: pharmacy "present" decays with the age of the last fill; a combination on the
chart no longer hides a separately-taken component; generator stops planting chart
dose errors whose cited GP line states no dose.

**Broken — why this is not merged:** after regenerating at 200, the 10 fixture
patients changed and two sample-sensitive tests fail:
- `test_generator.py::test_fixtures_distinguish_an_absent_column_from_a_blank_value`
  — "expected at least one blank IHI" in the fixture sample.
- `test_normalise.py::test_normalisation_accuracy_against_ground_truth` — patient
  free-text top-1 **0.837** vs floor 0.84 (DATA_SPEC target 0.85).
Do **not** lower either floor to pass. Fix by looking at which fixture patients
`--fixtures` picks (e.g. choose 10 that cover a blank IHI), or improve free-text
resolution.

**Also not done:** review of Arnav's schema additions (#12). **Zetaris is stale**
(still 40 patients) — run `make refresh` then `make verify`, and re-time Q1–Q3 at
~6 MB; latency was not measured at 200.

**Needs from teammates:** nothing new. World Model stays with Arnav.

**Next:** fix the two tests, `make refresh`, re-time, open the PR.

---

### 2026-10-25 09:35 AEDT · Arpon · arpon/sunday-logic

**Did:** Finished the clinical domain pack — `fuse`, `detect`, `triage` — and
`scripts/eval.py`, which scores it end to end against the planted ground truth.
584 tests green, secret scan clean, Zetaris refreshed and verified.

**Held-out scorecard (the number we report): precision 0.83, recall 0.94, F1 0.88,
high-risk recall 2/2**, with simulated review of near-miss identity links. With no
human review at all: F1 0.79. Tune: 0.91. Held-out is within 0.03 of tune and **no
change was made by looking at it.** Pinned by `tests/eval/test_scorecard.py` (F1
floors, 100% high-risk recall, ≤4 findings per patient, zero false merges).

**Building against real patients rather than in the abstract found eleven defects
before they could reach a demo.** In the order they were found:

- **Ground truth:** 9 of 20 planted omissions cited *another patient's* rows, which
  capped omission recall near 55% for any detector. The `dose_unconfirmable` phone
  change left no trace in any silo, so the warfarin finding had no visible reason —
  now rendered per DATA_SPEC 9.5 ("as directed per INR" vs "4 mg Mon Wed Fri").
  Discharge actions contradicted what happened; stale listings were planted for
  patients with no pharmacy record; one pack size per product made a finished
  prednisolone 25 mg course look like 200 days of supply.
- **normalise:** `" cr"` matched "Crestor", so rosuvastatin was modified-release;
  a generic-level AMT code borrowed an arbitrary product's release; pharmacy dosage
  forms were read as routes. Release and route conflicts across 108 medicines: 0.
- **coverage:** a GP line marked *ceased* counted as support. Now evidence against.
- **identity:** a lookalike's un-identified records were rejected outright when the
  patient's own IHI was absent from the cluster — P0008 lost three findings. Now
  review. And Arnav's P0002 label was a **scoring** bug: pharmacy surnames, which
  live inside "SURNAME, Given", were weighted as maiden-name matches.

**The design decisions are in `docs/DECISIONS.md` (25 Oct)** — chart excluded from
the BPMH, silence counts half, commission needs an assertion, frequency-vs-dose by
what changed, `dose_unconfirmable` for every current phone-dose medicine, acceptance
keyed `(type, atc_class)`. Four are out with the consultant as **briefs 11–14**.

**Changed shared files:** none of the listed ones. `types.py` is unchanged.

**For Arnav — things you will hit:**
- **`tests/fixtures/medtrace/Q0__admissions.json`** is new — your first `SAMPLE_MODE`
  replay. Identical to live. It is one row per admission-chart **line** (290 rows,
  40 admissions), so dedupe on `source_patient_id`.
- **The fixtures were regenerated today.** Your `tests/fixtures/api/*.json` still
  validate (no dangling row ids), but their demographics and row text now drift from
  `Q1/Q2`, and `run_P0002_needs_review.json` carries the old surname label. PLAN
  says regenerate them from real runs today anyway.
- **Acceptance is keyed `(type, detail["atc_class"])`**, the 4-character ATC
  subgroup, matching your `AcceptanceUpdate.atc_class`. Read it off the candidate
  rather than computing your own.
- **`fuse` leaves `FusedMed.high_risk_class` as `None`** (it is not given the
  lexicon). Fill it with `safety.high_risk_class(med.atc, lex)`.
- **The orchestrator composition is in `scripts/eval.py:reconcile()`** — Q1 →
  `link_identity` → Q2 on the auto-merge set only → `normalise_med` → `coverage` →
  `evidence_state` → `fuse` → `detect_discrepancies` → `prioritise`. Copy it rather
  than rediscovering the order.

**Broken:** nothing. Known and recorded rather than fixed: `coverage()` uses
`date.today()` for the stale-GP check, so it reads the wall clock instead of the
admission date — harmless today, wrong in a replay.

**Needs from teammates:**
- **Arnav** — the agent layer is where every unmet disqualification rule sits;
  World Model is 17 hours overdue. Tell me what you have and have not started, and I
  will take something off you (World Model is my preference — no coupling to your
  orchestrator).
- **Anshu** — nothing from you is in the repo yet. Everything you need has been on
  `main` since 4am: `tests/fixtures/api/`, `app/schemas.py`, `types.py`.

**Next:** review Arnav's schema additions (#12); then whatever he hands over.

---

### 2026-10-25 04:05 AEDT · Arnav · arnav/api-fixtures

**Did:** PLAN 5.8 — example API responses for the UI in `tests/fixtures/api/`, one per
endpoint: `status.json`, `patients.json`, `run_P0001_trace_partial.json` (mid-run poll),
`run_P0001_done.json`, `run_P0002_needs_review.json`, `feedback_response.json`, plus
one extra, **`run_P0001_gp_not_found.json`** — GP and interview not found, so the UI has
a case with UNKNOWN cells, the BPMH banner and `bpmh_not_confirmable`.

They are **hand-written illustrations, labelled as such** in `output.caveats` and in
`tests/fixtures/api/README.md`, built through the real pydantic models so they match
`app/schemas.py` exactly. Real where possible: demographics and row text from Arpon's
`Q1/Q2` fixtures, P0001's two planted omissions with their real row ids, the trust priors,
and **every identity link in the P0002 review is the actual output of
`identity.link_identity()`** on `Q1__P0002.json`. Invented rows have `-EX` in their id.
Patients are MRNs; `P0001` never appears inside a file.

`tests/unit/test_api_fixtures.py` (20 tests) validates every file against the schema and
checks coverage of the UI states: every `DiscrepancyType`, every `NoticeType`, all three
coverage states, every run status the UI handles, no dangling row ids. **Any schema change
now fails CI until these files are updated in the same PR.**

**Changed shared files:** none (`app/schemas.py` unchanged since #12).

**Broken:** Nothing. 464 passed / 36 skipped, secret scan clean.

**Needs from teammates:**
- **Anshu** — the files are on `main` once this merges; there were **no placeholders of
  yours** on `main` or any branch to replace. Types: copy from `app/schemas.py` (#12) and
  `app/domain/packs/medtrace/types.py`. The README lists which file exercises which screen.
- **Arpon** — one observation, not verified further: on P0002, `link_identity` labels
  `pharmacy:C000006` with *"surname matches a previous surname"*, but that row's
  `name_family` and `name_previous` are both null (its name is the combined
  `"PAPADOPOULOS, Thomas"` in `name_given`). The band and guards look right; the label may
  be off. Still open from my last entry: register silos on my Zetaris or stay on fixtures,
  and a Q0 fixture.

**Next:** PLAN 5.2, the Zetaris adapter (fixture replay first).

---

### 2026-10-25 03:48 AEDT · Arnav · arnav/schemas

**Did:** First session. Machine set up (Windows 11 + WSL2 Ubuntu; local Zetaris, own
Nightshift, preflight 20/2/1 — see my section of `docs/ENVIRONMENTS.md`, PR #11).
**Claiming PLAN 5.1 (schemas), 5.8 (example API JSON), then 5.2–5.7** in that order;
5.9 (engines) runs in a second session on `arnav/engines`.

PLAN 2.8 landed in `app/schemas.py`: `Finding`, `Evidence`, `IdentityReview`,
`ModelCall`, the new `FeedbackRequest`, and the MedTrace fields on `RunResponse`
(`coverage`, `bpmh_confirmable`, `banner`, `grid`, `notices`, `tasks`, `query_count`,
`zetaris_ms`, `model_calls`). The domain types (`Coverage`, `FusedMed`, `IdentityLink`,
`EvidenceState`, `Notice`, `SourceRow`, `DiscrepancyType`) are **imported from
`types.py`, never redefined**. Every new field has a default, so a response with only
the official fields still validates. 24 tests in `tests/unit/test_schemas.py`.

Beyond 2.8, added because PLAN 6 (UI) and 5.8 (the fixture list) need them — **Arpon,
these are the parts to review**:
- `RunStatus` gains `running` (mid-run poll) and `needs_review` (PLAN 6.4 expects
  `status: needs_review`). A finished run still reports only success/partial/error.
- `RunResponse.findings`, `.identity_review`, `.trace` (timeline polling), `.trust`
  (trust panel), `.evidence_index` (row_id → `Evidence`, for the grid's hover), `.patient_id`.
- `Finding.id`, `.explanation` (Writer's 1–2 sentences), `.intent_reason`.
- `IdentityReview.records` (record_key → `SourceRow`) so the UI can lay rows side by side.
- New: `IdentityDecisionRequest`, `PatientSummary`/`PatientsResponse` (Q0),
  `TrustEntry`, `FeedbackResponse` with `TrustUpdate` and `AcceptanceUpdate`.
- `TraceEvent.step` and `.message` (the plain-English timeline line).
- `HealthResponse.last_routed_model` (status pill). `RunRequest.patient_id`; `question`
  now has a default.

**Plan vs repo — followed the repo:**
1. PLAN 2.8 says `Finding` "gains" fields; there was no `Finding` in `schemas.py`. Created it.
2. PLAN 2.8 types `Evidence.fields` as `dict[str, str]`; it is `dict[str, str | None]`,
   because a SQL NULL arrives as JSON null and must stay `None` (Arpon, 24 Oct handoff).
3. Patients are identified by EMR `source_patient_id` (`MRN0000001`), not `P0001`:
   P-keys are ground truth, which the app must not see. The fixture filenames use
   P-keys; mapping them is a SAMPLE_MODE replay detail.
4. Arpon's generated envelopes for P0001–P0010 are already on `main`, so I will **not**
   hand-make P0001 fixtures as my own brief said. There is no Q0 (`q_admissions`)
   fixture yet.
5. The old `FeedbackRequest` (`memory_id`, `kind`) is replaced per 2.8; nothing imported it.

**Changed shared files:** **`app/schemas.py`** (additive except `FeedbackRequest`, which
is replaced per PLAN 2.8). **Anshu:** copy these into `web/src/types.ts`; example JSON
for every endpoint follows next in `tests/fixtures/api/`.

**Broken:** Nothing. 444 passed / 36 skipped, secret scan clean. Merging without
Arpon's sign-off, by agreement — review afterwards and changes come back as a PR.

**Needs from teammates:**
- **Arpon** — review the "beyond 2.8" list above. Also: should I register the MedTrace
  silos on my own Zetaris, or stay on fixtures until you say? And a Q0 fixture would
  let `GET /patients` replay in SAMPLE_MODE.
- **Anshu** — nothing to do yet; the example JSON lands next.

**Next:** PLAN 5.8, the example API JSON in `tests/fixtures/api/`.

---

### 2026-10-25 01:20 AEDT · Arpon · arpon/research-fixes

**Did:** Applied the consultant's round-two findings (briefs 6–10) and fixed three
things that surfaced while verifying them. 456 tests green, secret scan clean.

**1. The dispensing layer was the least believable part of the data. It is fixed,
and the fix came from real PBS numbers rather than better guesses.** `Med` was
inventing a pack of 60 or 30. The lexicon already carried each item's real PBS
maximum quantity and repeat count — we had the number and were not reading it.
Paracetamol 665 mg MR is a pack of **192**, not 60.

Two traps on the way, both worth knowing:

- An inhaler's pack is **1**, so `pack_qty / doses_per_day` collapsed to the 7-day
  floor and NovoRapid came out with **54 fills a year**. Pack size says nothing
  about duration for a device — the same reason `normalise.py` refuses to infer a
  daily dose from one. Devices are now a flat month.
- PBS records `pack_size` as **1** for some oral items too — the quantity unit there
  is a pack, not a tablet. Rosuzet is listed as 1, so it looked like a 7-day supply
  and one patient got **53 fills**. The honest signal is the **repeat count**, from
  the same real PBS row: an item with repeats is ongoing therapy and gets a
  one-month floor; an item with none is a one-off course.

Max fills for one medicine in 12 months: **29 → 14**, median 5, every `days_supply`
now ≥ 28. `repeats_left` is bounded by the item's real repeats instead of a random
0–5. Unlabelled shared ingredients on a chart: **3 → 0** (the three that remain are
the planted duplications, and they are labelled in ground truth).

**2. The TGA loader reported success on 1,010 rows while two columns were empty for
every one of them.** It looked for "Medicine name" and "resolution"; the real columns
are **`ARTG name`** and **`Supply impact end date`**. Also added
`Shortage impact rating` (Critical 90 / Medium 178 / Low 742) — Critical and Low are
not the same notice. A column that is empty for *every* row now warns loudly. This is
the second time this week a row count has passed while the shape was wrong; **a row
count is not a shape check**.

**3. Two silent-staleness bugs, and the second one matters to everybody.**

`datasvc` cached on path alone, on the reasoning that the files are immutable between
runs of `make synth`. They are not immutable *across* one. I regenerated the silos
while the process stayed up, so it kept serving the previous generation, **and
Zetaris cached that**. Every committed fixture then disagreed with the live views.
Now keyed on mtime and size. **If you regenerate data, you no longer need to restart
`datasvc` — but you do need `--refresh` (below).**

The worse one: `time_templates()` returned `None`, so a template query that *errored*
was printed in the timing list and then ignored, and the script **still exited 0**.
`Q_REF(nicknames)` had been failing for a day that way. `COUNT(*)` in `verify()`
cannot catch a missing column because it never names one — only running the real
query does, which is the entire reason those timings exist. It now returns a failure
count and `--verify-only` exits 1.

**New flags on `register_sources.py`:**
- `--refresh` — uncache and re-cache every raw table. **Run this after `make synth`.**
  `CACHE TABLE` on an already-cached table is a no-op, so a plain re-`--apply` leaves
  Zetaris serving the old generation. Creates and drops nothing.
- `--recreate-drifted` — finds REST tables whose *inferred* schema no longer matches
  the files and rebuilds them. **Drops objects, so it needs Arpon.**

**4. Research findings recorded where the code will actually see them.** Brief 8's
never-flag / always-flag rules are now data in `triage.py`, with provenance per rule.
`SUPPRESS` itself is untouched — a contract test pins it. Where the consultant could
not retrieve a dose-equivalence source (metoprolol tartrate↔succinate, gliclazide
IR↔MR, Optisulin↔Toujeo), **no conversion factor is asserted**; those go to a human
instead. An unverified factor silently applied to a high-risk medicine is worse than
no factor at all.

`docs/PITCH_CLAIMS.md` has the four headline claims with approved wording. One was
**wrong as we had it**: Actions 4.05 and 4.06 do not say "two independent sources" —
that is ACSQHC *implementation guidance*, and the numbering is 4.05/4.06. Also: we
must stop saying MedTrace produces a BPMH. A BPMH requires a clinician; ours is "a
pre-populated medication history for clinician verification". That is the same claim
the human-review gate makes in the product, so the pitch and the code now agree.

**Changed shared files:** **`CLAUDE.md` and the `Makefile`** — both on the
say-it-twice list.

- `CLAUDE.md`: two facts under Zetaris (a REST table infers its schema once at
  creation and a view pins its SELECT list the same way, `REFRESH TABLE` re-inferring
  neither; and `CACHE TABLE` on a cached table being a no-op), plus a working-agreement
  line that the gitignored data directories are yours to build and that **no test may
  write into the repo**.
- `Makefile`: `make register` was **broken** — it passed `--dry-run`, which is not a
  flag, so it exited 2 every time. The script is dry-run by default. Added
  `make refresh` and `make verify`, and `make synth` now prints the follow-up step.
- `docs/ONBOARDING.md` gained a "Build the data" section; there wasn't one, which is
  why this keeps catching people.

Also `datasvc/main.py`,
`scripts/register_sources.py` and `scripts/generate_synthetic.py` all changed
behaviour — see the two flags above if you touch Zetaris.

**Broken:** nothing. (`medtrace.nicknames` was broken for most of this session;
**resolved 25 Oct** — see below.)

**RESOLVED — `medtrace.nicknames`.** It failed every query in Zetaris. The REST
table inferred `struct<canonical, variant>` before `sex` was added by the name/sex
fix, and a Lightning REST table infers its schema **once, at creation** — `REFRESH
TABLE` returns ok and changes nothing. So the view reads rows wider than its schema
and Spark throws `ArrayIndexOutOfBoundsException`; `Q_REF(nicknames)` fails with
`UNRESOLVED_COLUMN ... 'sex'`.

To be clear about cause: **this was already broken before I touched it.** A stale
cached copy was masking it, and the only check that would have caught it was being
discarded (see 3). Everything else is green — all 8 other views match `datasvc`
exactly, Q0–Q3 run, and **all 6 live-vs-fixture diffs match**.

Arpon ran `--recreate-drifted` and it took **two passes**, which is the part worth
remembering. The first rebuilt `MT_REF.nicknames_raw` and reported every view `ok` —
but `Q_REF(nicknames)` still failed. **A SchemaStore view pins its SELECT list at
creation exactly as a REST table pins its inferred schema**, so the view went on
exposing two columns over a three-column table. `COUNT(*)` passed the whole time,
because counting rows never names a column — the same blind spot that hid the
original breakage. The tool now checks and rebuilds views too, rebuilds
`all_sources` when a silo view underneath it is replaced, and runs the real
templates at the end instead of stopping at `COUNT(*)`.

Now green: `Q_REF(nicknames)` returns 167 rows with `sex` populated (77 F / 90 M),
and `--verify-only` exits 0.

**Needs from teammates:** nothing.

**5. CI failed on a number that passed locally, and the cause is worth everyone's
attention: the test suite was rewriting the data it tests.**

`test_the_generator_is_deterministic` ran the generator twice **in place**, so running
`make test` silently overwrote `data/synthetic/` and the committed fixtures. On your
own machine that only hides staleness. On a fresh clone it is much worse:
`data/reference/lexicon.json` is **gitignored**, so CI regenerated the silos *without*
the real PBS codes, replaced the committed fixtures with those, and every later test
then asserted against data nobody had committed. That is how the same commit gave
0.846 locally and 0.820 on CI.

I only found it by cloning the repo into a temp directory and running the suite in a
`python:3.11-slim` container — the clone's fixtures came out byte-different from the
ones at the same SHA. Worth remembering as a technique: **if CI and local disagree on
identical commits, reproduce on a clean clone before suspecting the code.** My first
three hypotheses (Python 3.11 vs 3.12, hash randomisation, `SAMPLE_MODE`) were all
wrong, and each was easy to "confirm" by reasoning rather than testing.

Fixes: the generator takes `--out-root` and the test writes under `tmp_path`; the
module's `skipif` now checks the **silos** (gitignored) rather than `ground_truth.json`
(committed), which is what its reason string always claimed. Pack sizes moved to the
committed `medicines.csv` via `scripts/backfill_packs.py`, so the generator no longer
needs anything gitignored.

**Verified:** a fresh clone on Python 3.11 is fully green and the suite now changes
**0 tracked files**.

**Two things this leaves for the team:**
- **`make test` no longer regenerates your silos.** If `data/synthetic/silos/` is
  missing, the generator tests *skip* instead of quietly creating it. Run `make synth`.
- Our fixtures are only as good as the last person to commit them. The suite can no
  longer paper over a stale fixture by regenerating it.

**Next:** Sunday's modules — `fuse`, `detect`, `triage`, `scripts/eval.py`. `detect`
and `triage` now have brief 8 to build against. Q4/TGA registration stays optional.

---

### 2026-10-24 20:55 AEDT · Arpon · arpon/domain-logic (stacked on arpon/generator)

**Did:** Applied the Zetaris registration (step 6) and started step 7.

**1. Registration is LIVE and verified.** All 28 statements succeeded, all 8 views'
counts match the files `datasvc` serves, and
**`SELECT COUNT(*) FROM medtrace.all_sources` = 4,825** in 1.05 s.

**Zetaris is not the time budget.** Q_REF 0.17–0.64 s, Q0 0.33 s, **Q1 1.84 s**,
Q2 1.86 s, Q3 1.72 s — **a complete run costs about 6 s of Zetaris** against a 5–10
minute budget. This finally closes the thread my 24 Oct correction opened: latency
tracks bytes scanned, our silos are ~2 MB, and runs will be dominated by the model. Every
architectural rule still stands but is now *prudent* rather than *forced* — except
"reference the union view only once", which is a hard engine limit.

**2. Going live found a bug nothing else could have.** Diffing the real
`q_identity_candidates()` against the committed fixtures showed **every row count
matching** — 145 vs 145, 387 vs 387, all ten patients — while **409 cells per envelope
differed**. Live Zetaris returns JSON `null` for a column the source does not have, and
`""` for a column it has whose value is blank; the fixture generator stringified both to
`""`. `SAMPLE_MODE` would have replayed a shape the live view never produces, and
because counts agreed **no count check, schema check or existing test could have caught
it**. Fixed; all 10 fixtures now match live exactly.

Kept as a command, not a one-off: **`register_sources.py --diff-fixtures`**. PLAN 2.9
asked for exactly this ("any difference is a view bug"), and the fixtures and views can
drift later from a `HARMONISED_MAP` edit or a regenerated silo. **Lesson for everyone: a
row-count check is not a shape check.**

**3. Step 7, two of five modules done.**

- **`parse.py`** complete — the one place that casts. Dates are **day-first** for the
  non-ISO formats because every source here is Australian. Combination strengths are
  **dropped rather than guessed** when the ingredient and number counts disagree:
  attaching the wrong milligrams to the wrong drug is worse than attaching none, because
  the dose comparison would then be confidently wrong.
- **`safety.py`** complete. A test asserts **every medicine our reference data marks
  high-risk actually matches an APINCHS prefix** — otherwise APINCHS recall cannot reach
  100% and would fail silently. It immediately caught **prednisolone**: DATA_SPEC 10.1
  says prednisolone (H02AB) is *not* APINCHS and carries `steroid_taper_ext` for
  `dose_unconfirmable` only. Implemented as that documented exception with its own label,
  not excluded from the test.

I **broke the frozen `safety_gate` signature** while writing it and the contract test
caught it before commit. That test is now restructured around a single `IMPLEMENTED` set,
so filling in a module is a one-line change, plus a new check that an implemented
function handles empty input rather than raising — which is what a run with a missing
source hands it.

**Changed shared files:** `requirements.txt` — **`jellyfish==1.3.0`** added for
Jaro-Winkler and metaphone per PLAN section 1. Verified metaphone collapses Smyth and
Smith to `SM0`, the demo's "Margaret Smith / Peggy Smyth" case, which string distance
alone scores as a near-miss. Also `pytest.ini` (`slow` marker; the anyio deprecation
ignored **by message only** so our own still fail the build).

**Broken:** Nothing. **342 tests green, secret scan clean on 144 files.**

**Still running on this machine:** `datasvc` on `0.0.0.0:8100`, PID in `/tmp/datasvc.pid`.
The registered tables are `CACHE`d so existing queries work without it, but a cache
refresh or a re-register needs it up. Restart with
`.venv/bin/python -m uvicorn datasvc.main:app --host 0.0.0.0 --port 8100`.

**Needs from teammates:**
- **Arnav** — `main` has DATA_SPEC and the skeleton. Fixtures live on `arpon/generator`
  (PR #7). Two rules that bite: **never build a SQL literal by hand** (use
  `queries.sql_literal()` — the doubled quote fails silently), and **keep `None` as
  `None`**. `parse.dicts_from_sql` is now real, so use it rather than zipping yourself.

**Needs from Arpon:** the five research briefs in `docs/RESEARCH_QUESTIONS.md` are with a
consultant. Nothing in step 7 blocks on them.

**Next:** `coverage.py`, then `identity.py` (both tiers, nickname and DOB comparators,
the lookalike and transitivity guards), then `normalise.py`. Three PRs are open and
stacked: **#6 → #7 → this one**; merge in that order.

### 2026-10-24 18:40 AEDT · Arpon · arpon/generator (stacked on arpon/reference-data)

**Did:** Steps 2, 4, 5 and 6. `docs/DATA_SPEC.md` is **merged to main** (#5) and so is the
**domain-pack skeleton** (#4), so Arnav has both his dependencies.

**1. The PBS public API works — I was wrong to call it a wall.** The 401 body said to
send the key and I read it as "registration required". The published unregistered key
works, free, no login. What is genuinely gone is narrower: the monthly CSV bundle is in
the embargo area behind an HPP login, and the legacy XML/text files were discontinued
1 May 2026. **188 of 207 lexicon rows now carry a real `pbs_code`**, with real
`pack_size` and `number_of_repeats`, from schedule 4751.

**The licence needs a decision from you.** The `_meta` copyright block PLAN §3 required
reading is **more restrictive than the CC BY 3.0 AU** reported elsewhere: *"Permission is
granted to use and redistribute this content, as long as all copyright statements are
retained. **Permission is not granted to modify this content.**"* I honoured the
statement attached to the bytes over the general label, so no PBS value is altered,
`data/reference/` stays gitignored as the plan directed, and only a ≤200-row attributed
sample is committed. Full reasoning in `docs/DATA_LICENCES.md` §1.

**2. The ATC cross-check earned its keep, and two items need a clinician.** 35
disagreements between DATA_SPEC and PBS, in `data/reference/atc_crosscheck.csv`. Only
**two change the APINCHS class**, which is the only kind that matters, and the build
reports exactly those:

| Medicine | DATA_SPEC | PBS | Effect |
|---|---|---|---|
| **sotalol** | `C07AA07` → not APINCHS | `C01BD` → **Ext** | PBS makes it high-risk |
| **paracetamol/codeine** | `N02AJ06` → **N** | `N02BE01` → not APINCHS | PBS loses the codeine |

Sotalol genuinely is a class III antiarrhythmic, so the spec may be under-classifying
it. For Panadeine Forte the spec is right and PBS is wrong. **DATA_SPEC wins in the
build — nothing was applied silently.** The other 33 are PBS systematically giving a
combination the ATC of one component, which doesn't move the class.

**3. The generator runs.** 40 patients, 355 medicines, 73 planted findings, ~4,800 silo
rows, **30 Zetaris envelopes in `tests/fixtures/medtrace/`**. Three defects found while
building it, each of which would have been invisible later:

- `choose_medicines` never topped up when short, so the population sat at **4.3
  medicines per patient** against the spec's 5–12 (mean 8.4) — and every *per-medicine*
  planting rate was then applied to too small a denominator. Now 5–12, mean 8.9.
- **Planted findings had empty `row_ids`**, because findings are planted while rendering
  the EMR, before the GP/pharmacy/patient rows exist. DATA_SPEC §11.2 scores a true
  positive by row_id **overlap**, so every one would have been unmatchable — recall
  capped at zero per type, for reasons nothing to do with the detector.
- **`duplication` had an uncontrolled rate** — only planted when sampling happened to
  draw a combination beside its own component. It produced 3 instances and *all 3 landed
  in held-out*, so the type had nothing to tune against. Now induced at §5.2's 0.18.

**4. `datasvc` serves all 7 endpoints.** `register_sources.py` builds all 28 statements
and is **dry-run by default — nothing has been applied to Zetaris**, per PLAN step 6's
"wait for my go-ahead". The view `SELECT` lists derive from the generator's
`HARMONISED_MAP`, so the live view and the replayed fixtures cannot drift apart.

**Changed shared files:** `app/config.py` and `.env.example` (`PBS_API_BASE`,
`PBS_SUBSCRIPTION_KEY`), `Makefile` (`data`, `lexicon`, `synth`), `pytest.ini` (a `slow`
marker; the anyio deprecation ignored **by message only** so our own still fail the
build), and `app/domain/packs/medtrace/{types,queries,parse}.py` — see the `known_shortage`
note in the previous entry.

**Broken:** Nothing. **241 tests green, secret scan clean on 143 files.** Caveats worth
knowing: no SQL has been applied to Zetaris yet (dry run only); `amt-items` was not
fetched, so **AMT codes are synthetic** and clearly marked; `dos_weight` is real for only
57 of 207 rows because the Item Report is 2016 data against the 2026 schedule.

**Needs from teammates:**
- **Arnav** — everything you need is on `main`: `docs/DATA_SPEC.md` and the whole
  `app/domain/packs/medtrace/` skeleton. Fixtures for 10 patients (Q1/Q2/Q3) and Q_REF
  are in `tests/fixtures/medtrace/` on **this branch**, so merge #6 then #7 (or pull the
  branch) for `SAMPLE_MODE`. Two hard rules: **never build a SQL literal by hand** (use
  `queries.sql_literal()` — the doubled quote fails silently), and **keep `None` as
  `None`**, never `str()` it.
- **Anshu** — unaffected.

**Needs from Arpon (you), in order:**
1. **Go-ahead to `--apply` the registration.** 28 statements, dry run reviewed. This is
   the last step before a live `SELECT COUNT(*) FROM medtrace.all_sources`.
2. **Sotalol and paracetamol/codeine** — the two ATC/APINCHS calls above.
3. **DATA_SPEC §4.2 bundle 6** sums to 0.95, not 1.00. Missing share, or a wrong one?
4. **Four formulation-trap drugs have only one form in §4.2** (metoprolol, gliclazide,
   venlafaxine, tamsulosin), so no IR/MR pair can be planted for them. Needs a brand and
   strength each, from you — I won't invent them.
5. **Population size.** At 20 tune patients, §5.2's "≥15 tune instances per type" is
   unreachable for the low-rate types. Raise `--patients` before the final eval run.

**Next:** DATA_SPEC §7's lookalike, twin and overlay traps — `identity_traps` is empty
and **Q1 currently returns no decoys**, which matters because false-merge rate is a
headline metric and identity is the demo's opening scene. Then `--apply` once you say so.

### 2026-10-24 16:05 AEDT · Arpon · arpon/skeleton

**Did:** Two things: ran the templates against live Zetaris instead of trusting the
dialect, and did PLAN step 1 (the reachability spike). Both found things.

**1. `''` is not an escaped quote in Lightning SQL — it silently deletes the
apostrophe.** `SELECT 'O''Brien'` returns `OBrien`, length 6. `''` closes one literal
and opens another, and adjacent literals concatenate; quotes stay balanced and nothing
raises. On 789 real rows, `zone LIKE '%''%'` matched **789 of 789** (the pattern had
collapsed to `%%`) where the backslash form matched the true 12, and `=` against a real
apostrophe value returned **0 rows with no error**. For us that is a patient-safety bug:
`O'Brien` would reach Zetaris as `OBrien`, match nothing, and the pharmacist would be
told **"GP: no record found" for a record that exists** — a fabricated coverage gap from
a query that succeeded, invisible in a trace. `sql_literal()` now escapes `\` → `\\`
then `'` → `\'`, verified to round-trip every value we embed, with injection attempts
returning as inert strings. **One of my 104 tests had asserted the wrong escaping as
correct**, so the suite agreed with the bug — only sending it to the engine found it.

**2. The step-1 spike passed completely, and closed three risks.** `datasvc` can live
on the host:
- `host.docker.internal:8100` → **HTTP 200 in ~20 ms** from both `zetaris-api-1` and
  `zetaris-driver-1`.
- A real `CREATE LIGHTNING REST TABLE` at that URL **fetched our data**.
- `LATERAL VIEW explode(records)`, a harmonised `SCHEMASTORE VIEW`, and a
  `UNION ALL` union view all work: **4 200 rows, 2.3 s**.
- **The real `q_identity_candidates()` output ran verbatim** against that union view —
  23 rows, 2.6 s, including `UPPER(name_family) LIKE 'O\'BR%'` against a real `O'Brien`.
- A self-join on the union view failed with exactly the documented
  `MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION`. The error names
  `records`, the pre-explode array — so **any** second reference breaks it, not just a
  self-join. `queries.py`'s no-subquery/no-window rule is load-bearing.

So the MinIO/Parquet, Postgres-over-JDBC and four-separate-views fallbacks are all
**retired**. Everything was dropped afterwards; `SHOW LIGHTNING DATABASES` is back to
`NY_TAXI` and `TPCDS_DB`.

**3. I have to correct myself on yesterday's headline finding.** I recorded that Zetaris
latency was "per-query engine overhead, not data volume — smaller synthetic silos will
not make it meaningfully faster", and put it in `DECISIONS.md`, `TODO.md`, `PROGRESS.md`
and the plan as *the* constraint shaping the architecture. **It is wrong.** It tracks
**bytes scanned**, ~1 s + 2–3 s/MB:

| Query | Rows | Bytes | Time |
|---|---|---|---|
| our union view `COUNT(*)` | 4 200 | ~1.1 MB | 2.3 s |
| `taxi_zones COUNT(*)` | 789 | ~11 MB (14 KB/row, multipolygon geometry) | 17.0 s |
| `taxi_trips COUNT(*)` | 500 000 | ~50 MB | 164.2 s |

`taxi_zones` was the worst table to generalise from — smallest by row count, nearly
largest by volume — which is exactly what produced the false reading. The fix was one
extra query against a second table.

**This is good news:** at ~1 MB per silo a query is 1–3 s and a whole run costs ~10 s of
Zetaris, so the 5–10 minute budget is comfortable and Zetaris is **not** the dominant
cost. Two consequences for the generator (step 4): **keep the silos small and narrow —
that is now the main latency lever**, and do not rely on column pruning, because a
narrow projection on an 11 MB table saved only 10% (15.3 s vs 17.0 s). The design rules
(no joins at agent time, budget 8, harmonised views, one batched verification query) all
still stand — prudent rather than forced. `ZETARIS_TIMEOUT_S=180` stays; 164 s on a
50 MB table is what it is for.

**4. A NULL is not a string.** `CAST(NULL AS STRING)` came back as JSON `null`, not
`"null"` — so "every value arrives as a string" has one exception. `parse.py` must treat
it as absent; stringifying it puts the literal text `"None"` into `name_previous`, `sex`
and every source-specific null, which would read as a present, non-matching value in
identity scoring and `evidence_state`. Corrected in `REFERENCE_NOTES` 1.1.

**5. `CACHE TABLE` is not the latency lever we assumed.** 1.39/1.66/1.06 s before,
2.01/1.07/1.33 s after, on the 4 200-row union — no measurable difference. The
sponsor's 49.7 s → 1.2 s figure was a **rate-limited external API**; our `datasvc` is a
local HTTP server where a 643 KB refetch is free. Keep it (it stops a demo hammering
`datasvc`), but it is not what makes runs fast.

**Changed shared files:** `CLAUDE.md` — added the backslash-escaping rule to the Zetaris
behaviour list, so any free-SQL path inherits it. Also `docs/REFERENCE_NOTES.md` (1.1
nulls, 1.2 escaping + `UPPER`/`LIKE` costs), `docs/DECISIONS.md` (two new entries;
yesterday's latency entry marked **superseded in part** in place rather than edited),
`PROGRESS.md`, and **one clearly-marked correction line in `docs/PLAN_2026-10-24.md`
§0** — I did not touch the plan's prose, but three people read that section today and
the wrong justification came from my measurement. Arpon: say if you would rather I
revert that line and leave the plan as a dated snapshot.

**Broken:** Nothing. 161 tests green, secret scan clean, PR #4 CI green. Caveat on all
spike numbers: **one machine, one afternoon, 4 200 synthetic rows** — and the thing I am
correcting today is precisely what over-generalising from one measurement did yesterday,
so treat the ~2–3 s/MB model as a working estimate, not a law. Re-measure on the real
generated data in step 6.

**Needs from teammates:**
- **Arnav** — two things now bind on you. (a) **Never build a SQL literal by hand**; use
  `queries.sql_literal()`. The doubled quote fails silently, so a free-SQL path that
  gets this wrong produces wrong answers rather than errors. (b) Your adapter must keep
  `None` as `None`, not `str()` it. Otherwise unchanged: import from
  `app.domain.packs.medtrace.*`, do not write your own stubs.
- **Anshu** — nothing changes for you.

**Next:** PLAN step 2, the reference build (PBS CSV bundle, lexicon, APINCHS, nicknames,
`DATA_LICENCES.md`). Step 3 (`DATA_SPEC.md`) is Arpon's by hand.

### 2026-10-24 15:10 AEDT · Arpon · arpon/skeleton

**Did:** PLAN step 3b, the MedTrace domain-pack skeleton, brought forward ahead of
steps 1 and 2 because Arnav is blocked on it. `app/domain/packs/medtrace/` now has
`types.py` (final), all ten modules from PLAN 2.5 with their real signatures and
docstrings, `queries.py` with Q_REF and Q0–Q3 **written as real Lightning SQL**,
`SOURCE_TRUST_PRIORS` filled in, and a local `decide()` at 0.85/0.82 with a TODO to
swap in World Model's. 104 new tests; 160 total green, secret scan clean.

Six places where the plan and the repo disagreed, each resolved in favour of the repo
and each documented in the module it affects:

1. **`SqlResult` did not exist.** PLAN 2.5 types `rows_from_sql(result: SqlResult)`
   against a name that is nowhere in the repo. Defined in `types.py` from the envelope
   already recorded in `tests/fixtures/zetaris/`, because `parse.py` consumes it and
   `app/adapters/zetaris.py` is Arnav's file — the shape is the contract between us.
   `timeUsed` is **optional**: the fixtures strip it, so requiring it would fail every
   `SAMPLE_MODE` replay.
2. **No `DISTINCT`, no window functions, no `JOIN`s, no subqueries in any template.**
   `REFERENCE_NOTES` 1.2 says a second reference to a `UNION ALL`-of-`explode()` view
   fails outright, and `medtrace.all_sources` is exactly that shape; `DISTINCT` over
   one is listed in PLAN 2.1 as an unproven spike; and a 2-table `JOIN` took 91 s
   (`DECISIONS.md`, 24 Oct). So Q0 and Q1 do one flat scan and **deduplicate in
   Python**. This refines PLAN 2.4, which assumed one record per row for both.
   Returning 60 rows instead of 8 is free; a second query is 4–91 s.
3. **Per-source views carry the harmonised columns; `all_sources` is a plain
   `UNION ALL`.** PLAN 2.3 reads as though the renaming happens in `all_sources`, but
   then PLAN 2.1's fallback ("if the union fails, query the 4 views separately") would
   need every template rewritten. With the harmonising pushed down one level it is a
   one-line change. `register_sources.py` (step 6) will follow this.
4. **The trust-attribute vocabulary in PLAN 2.5 is inconsistent.** `fuse` is typed
   `trust: dict[tuple[str, str], float]` over the fused attributes (existence,
   daily_dose, frequency, release, route) but the example priors name `strength`,
   `intended_dose`, `actually_taking`, `name` and `admission_chart`. Resolved by
   declaring `types.TrustAttribute` as the union of both, keeping all seven of the
   plan's example values **verbatim** so the H-MEM seed matches what we agreed. A test
   asserts those seven.
5. **PLAN 2.5 names `DiscrepancyType`, `FusedValue`, `GateResult` and the notice types
   without defining them.** Defined from PLAN 2.6, plus a `Notice` model.
6. **Q4 (`q_shortages`) is deliberately not written.** `medtrace.tga_shortages` is not
   registered and nobody has seen its columns, so writing SQL against it would be
   inventing an endpoint. It raises with a pointer to PLAN 3, Monday.

Two bugs the tests caught in my own code before it shipped, both now regression-tested:

- `q_identity_candidates` built its surname prefix by stripping punctuation, so
  `O'Brien` became `OBRI` and `UPPER(name_family) LIKE 'OBRI%'` never matched
  `O'BRIEN`. **Every apostrophe and hyphen surname would have dropped out of the
  candidate set silently** — invisible in testing, and a missed link shows the
  pharmacist one fewer source. The prefix now keeps the characters a surname really
  contains and stops at the first one that is not letter/apostrophe/hyphen/space, which
  also means `%` and `_` can never reach a `LIKE` pattern as wildcards.
- `NotRequired[int]` is **silently ignored** under `from __future__ import
  annotations`: the annotation stays a string and `__required_keys__` reports the key
  as required anyway. `SqlResult` is split across two classes with `total=False`
  instead, which is a class flag and is honoured. Worth knowing before anyone writes
  another optional-key TypedDict in this repo.

**Changed shared files:** **new** `app/domain/packs/medtrace/types.py` — the frozen
shared file from PLAN 1. Nothing else shared was touched: `app/schemas.py`,
`app/config.py`, `.env.example`, `requirements.txt`, `Makefile`, `CLAUDE.md` and CI are
all unchanged. `jellyfish` is **not** in `requirements.txt` yet — nothing imports it
while the bodies are stubs; it arrives with step 7.

**Broken:** Nothing. Every stub raises `NotImplementedError("Arpon: <file>")`, so a
missing piece names its owner rather than returning `None`. Unproven, in order of how
much rests on it: whether the Zetaris containers can reach `host.docker.internal:8100`
at all (step 1, next); whether the union view registers, caches and queries; and
whether the harmonised views accept these templates against real data. **No SQL in
`queries.py` has been run against Zetaris yet** — it is written to the recorded
envelope and the documented dialect rules, not measured.

**Needs from teammates:**
- **Arnav** — import from `app.domain.packs.medtrace.*` now; do not write your own
  stubs. `queries.py`, `identity.decide()` and `trust.SOURCE_TRUST_PRIORS` are real and
  usable today; everything else raises and wants a fixture-backed fallback **in your
  own code**. Don't edit anything under `app/domain/`. The signature table in
  `tests/unit/test_medtrace_skeleton.py` is the contract — if you need a signature
  changed, ask me rather than editing it, since the test exists to stop exactly that
  drift. When World Model lands, `identity.decide` becomes a delegation to yours; the
  thresholds are already the same numbers, and a test pins both edges inclusive.
- **Anshu** — the vocabulary your grid renders is `types.EvidenceState` (three-valued:
  `unknown` must look different from `absent_in_scope`), `types.DiscrepancyType` (11)
  and `types.NoticeType` (6).

**Next:** PLAN step 1 — Zetaris up, then the `host.docker.internal:8100` reachability
spike, and message Arnav either way. Then step 2 (reference build). Step 3
(`DATA_SPEC.md`) Arpon is writing by hand, not in this session.


### 2026-10-24 11:15 AEDT · Arpon · arpon/team-workflow

**Did:** Separated shared rules from per-machine facts. `CLAUDE.md` had grown a "Known
environment facts" block that was really *my laptop's* state — Zetaris up, preflight
green, observed model ids — presented as if true for everyone. Replaced it with
provider/API behaviour that holds anywhere, and moved the machine-specific half out.
Also tightened the Zetaris rule: nobody starts, stops, reconfigures or deletes any
Zetaris stack, and nobody creates or rotates API keys — each person manages their own
install and we talk to it only over REST.

New: `CLAUDE.local.md` (gitignored) for my own machine notes, `docs/ENVIRONMENTS.md`
with a section per person, and a `.state/preflight.json` output from `make preflight`.
Every "verified"/"works" claim in `PROGRESS.md`, `docs/DECISIONS.md`,
`docs/REFERENCE_NOTES.md` and `README.md` now says **where and when** — all of them
read "Arpon's machine, 23 Oct". The Zetaris fixtures are marked as recorded from my
instance, with a note that a different shape on your instance is a finding to record,
not a reason to bend the parser.

**Changed shared files:** `CLAUDE.md` (Zetaris rule rewritten; machine facts removed;
new "Facts about your own setup live elsewhere" + "API behaviour that holds everywhere"
sections), `.gitignore` (`CLAUDE.local.md`), `scripts/preflight.py` (saves
`.state/preflight.json`, new `--no-save`), `PROGRESS.md`, `README.md`,
`docs/DECISIONS.md`, `docs/REFERENCE_NOTES.md`, `docs/ONBOARDING.md`,
`tests/fixtures/zetaris/README.md`. New: `docs/ENVIRONMENTS.md`.

**Broken:** Nothing. 52 tests green, secret scan clean, `make preflight` 19/19 on my
machine just now (services came back up). Caveat: `gh` still not installed here, so the
PR has to be opened through the GitHub web UI and I cannot watch CI from the terminal.

**Needs from teammates:** Anshuman and Arnav — fill in your section of
`docs/ENVIRONMENTS.md` and create your own `CLAUDE.local.md`. Do **not** put
credentials in either. You do not need Zetaris or Nightshift to start: `make test` runs
with no `.env` and no network, which is how CI runs it.

**Next:** Still blocked on the **track decision** — see `TODO.md`. Nothing in Phase 2
should start before that, and roles remain unassigned.

---

### 2026-10-24 09:30 AEDT · Arpon · arpon/team-workflow

**Did:** Set up the team workflow, no features. Removed `.cursor/` and every reference
to it, so `CLAUDE.md` is now the single source of rules (a mirrored rules file drifts
and then misleads). Added this handoff log, `PROGRESS.md`, a SessionStart hook that
orients you automatically, GitHub Actions CI, and `docs/ONBOARDING.md`. Merged the
Cursor note into `docs/AI_TOOLS_USAGE.md`.

**Changed shared files:** `CLAUDE.md` (new "Team workflow" section; rule 4 rewritten
for Claude Code), `metadata.json` (`cursor.used: false`), `README.md`,
`docs/SPONSOR_TECH.md`, `docs/AI_TOOLS_USAGE.md`. New: `.claude/settings.json`,
`scripts/session_start.sh`, `.github/workflows/ci.yml`, `PROGRESS.md`,
`docs/HANDOFF.md`, `docs/ONBOARDING.md`. Deleted: `.cursor/`.

**Broken:** Nothing. 52 tests green, secret scan clean. Two caveats: `gh` is not
installed on this machine, so the PR could not be opened from the terminal and the
session-start hook skips its PR section gracefully. CI has not run before this push, so
its first run on this branch is also its first real test.

**Needs from teammates:** Roles are not assigned — nothing here allocates work. Each
person needs their own Zetaris API key and Nightshift Runtime token in their own local
`.env`; see `docs/ONBOARDING.md`. Nobody shares credentials.

**Next:** The blocking decision is still **which track** — see `TODO.md`. Both Phase 2
adapters are unblocked and contract-complete the moment that lands.
