# For Arnav's next session — read this first

**Written 25 Oct by Arpon's session, for Arnav's Claude Code session.** Nobody is
reading PRs, so everything you need from Arpon's side is here. Work top to bottom.
Tick items off by editing this file in your PR, and say what you did in your
`docs/HANDOFF.md` entry.

Before you start: `git pull origin main`, `make setup`, `make test`. Then
`make synth` — `data/synthetic/silos/` is gitignored, and the generator tests and
the scorecard **skip** without it. A skip there is a missing build, not a pass.

> **✅ Landed 25 Oct: demo data.** `git pull`, then `make synth` (and `make refresh`
> if you use live Zetaris). Recording outputs is unblocked.
> - **Five sample inputs** in `input_examples/` (rule 8), each with a row in
>   `input_examples/README.md` saying what a correct run shows. All have replay
>   fixtures, so all run under `SAMPLE_MODE`:
>   - `example_1`: P0015, **needs_review** first, then warfarin and insulin
>     findings.
>   - `example_2`: P0089, straight through, opioid duplication.
>   - `example_3`: P0013, **needs_review**, then only 2 of 4 sources, so nothing
>     invented.
>   - `example_4`/`example_5`: the learning pair below.
> - **Learning demo:**
>   1. Run P0003 (`MRN0000003`): its candesartan dose **abstains** (GP 16 mg vs
>      pharmacy 8 mg). The pharmacist rejects the GP value: `reason="source_outdated"`,
>      `source="gp"`, `attribute="daily_dose"`. PLAN 5.7 −0.20 takes GP
>      `daily_dose` 0.70 → 0.50.
>   2. Run P0007 (`MRN0000007`) with the updated trust: rosuvastatin resolves to
>      10 mg, and a new **dose finding** appears (the chart says 20 mg, copied from
>      the stale GP list).
>   3. Run P0007 at the priors and it abstains with no finding. That before/after
>      is the demo.
>
>   **The −0.20 must reach `fuse`'s `trust` dict as `("gp", "daily_dose")`.**
>   `tests/unit/test_learning_demo.py` shows the exact call. Use it as the
>   acceptance test for your H-MEM wiring.
> - **Docker:** the image now copies `tests/fixtures/medtrace/` (the replay set).
>   Read sample-mode fixtures from that path.
> - New replay fixtures: `Q1/Q2/Q3__P0013`, `__P0015`, `__P0089`. P0003 and P0007's
>   changed; nothing else did, and Q0 is identical.

> **Scan, 25 Oct:** your items are under **Arnav** in `docs/SCAN_2026-10-25.md`
> (S5 timeout discards results, S6 free-text tasks dropped, S9 failed Nemotron calls
> missing from the trace, S10 unverified Writer summary, S11 stuck runs, and more).
> World Model + conformance is still first.

---

## 0. Where things stand (two lines)

- **Arpon's side is done.** Every function in `app/domain/packs/medtrace/` is real
  code, scored end to end: held-out F1 0.95, high-risk recall 35/37 (core APINCHS 30/32), zero false
  merges over 200 patients. Your stub of the pack is no longer needed — call it.
- **Every unmet disqualification rule is in your layer.** No model call goes
  through Nightshift yet (rules 2 and 3). No Meterless engine or conformance test
  exists (rule 2). `POST /run`, `run.py` and `SAMPLE_MODE` don't work (rule 8).
  No agent queries Zetaris (rule 1). Sections 2–3 are short; section 4 is the
  critical path.

---

## 1. How to call the domain pack (copy this, don't rediscover it)

`scripts/eval.py:reconcile()` is the exact order, already working. In the
orchestrator:

1. **Q0** `queries.q_admissions()` → the picker. It returns **one row per
   admission-chart line** (1,326 rows for 200 patients), so dedupe on
   `source_patient_id`. Fixture: `tests/fixtures/medtrace/Q0__admissions.json`,
   identical to live.
2. **Q1** `q_identity_candidates(anchor)` → `rows_from_sql` →
   `identity.link_identity(anchor, candidates, lex)`.
   - A `review`-band link → status `needs_review` and stop.
     `POST /run/{id}/identity` resumes.
   - A confirmed link becomes `auto-merge`, a rejected one `new`.
3. **Q2** `q_meds_for(links)` on the **auto-merge set only** → `rows_from_sql` →
   `normalise_med` per row.
4. `coverage.coverage(links, rows)`. Then
   `evidence = {g: {src: coverage.evidence_state(g, src, cov[src], stmts)}}`.
5. `fuse.fuse(stmts, evidence, trust, as_of)` — `trust` comes from H-MEM, seeded
   from `trust.SOURCE_TRUST_PRIORS`.
6. `detect.detect_discrepancies(fused, stmts, cov, as_of, lex)` →
   `safety.safety_gate` per candidate → `triage.prioritise(cands, acceptance)`.

Three things the pack leaves to you:

- **`FusedMed.high_risk_class` comes back `None`** (`fuse` isn't given the
  lexicon). Fill it with `safety.high_risk_class(med.atc, lex)` before it goes
  into `RunResponse.grid`.
- **The dose-confirmation task lane.** Call `safety.forced_confirm(med.generic,
  med.atc)` for **every current medicine in the grid**, whether or not there's a
  finding, and put each non-`None` result into `RunResponse.tasks`.
  - That covers warfarin, every insulin, prednisolone and methotrexate.
  - The consultant pharmacist ruled this a separate lane, not a ranked finding.
    `detect` raises `dose_unconfirmable` only when the sources visibly conflict.
- **`ABSENT_IN_SCOPE` now means two things**: "not listed", and "listed as
  stopped" (a ceased GP line, a patient's "no"). The row's `status_text` tells
  them apart if the UI needs to.

---

## 2. Two schema additions (`app/schemas.py`, yours, shared — say so in the PR)

Both are needed because of what the pack produces since 25 Oct.

- [x] **`Finding.detail: dict[str, Any] = {}`**, passed through from
  `DiscrepancyCandidate.detail`.
  - **Without it the learning loop can't work.** Your `AcceptanceUpdate` keys on
    `(type, atc_class)`. `detect` writes `atc_class` (4-character ATC subgroup,
    e.g. `C09A`) into `detail`, and `triage` reads it there. So `POST /feedback`
    must read `finding.detail["atc_class"]`.
  - It also carries what the UI must render:
    - `conflict: "confirm"` — show it as *ask first*, never *stop this medicine*.
    - `bpmh_single_source` — the history rests on one source; unverified.
    - `subtype`, `statement` ("charted 150 mg/day against 75 mg/day before
      admission"), and `daily_dose_ratio`.
- [x] **`FeedbackRequest.source: Source | None` and `.attribute: str | None`**,
  validated as required when `reason == "source_outdated"`. (Arnav, 25 Oct: both
  are required for `source_outdated`, and `attribute` is typed `TrustAttribute`.)
  - PLAN 5.7's `-0.20` lands on *that* `(source, attribute)` H-MEM record.
  - That's the demo's "reject a GP dose as outdated → patient B resolves
    differently".
- [x] Update `tests/fixtures/api/*.json` in the same PR — `test_api_fixtures.py`
  fails otherwise. (Regenerated against the 25 Oct data; the review example is now
  P0015, because P0002 no longer reaches review.)
  - While there: the fixtures were regenerated at 200 patients, so the
    hand-written row text and demographics have drifted from `Q1`/`Q2`.
    PLAN says regenerate them from real runs anyway.

Optional, if time: a structured `Task{id, kind, text, generic, row_ids,
high_risk_class}` instead of `tasks: list[str]`, so a dose-confirm task can
carry its rows and a "confirmed dose + source" on close. `list[str]` is fine for
the demo.

---

## 3. Two facts that will save you a debugging session

- **Zetaris at 200 patients is no slower than at 40**: Q1 1.99 s, Q2 1.92 s,
  Q3 2.95 s, because the tables are `CACHE`d. If yours is slow, it isn't the data
  size.
- **If you regenerate data, run `make refresh` then `make verify`.**
  `CACHE TABLE` on a cached table is a no-op, so Zetaris otherwise keeps serving
  the old generation.

---

## 4. Your critical path (unchanged from PLAN, in disqualification-risk order)

- [x] Meterless adapter (Nightshift) — rules 2 and 3. (Adapter done and verified live,
  25 Oct. The rules are only *met* once an agent calls it.)
- [x] (Arnav, 25 Oct: done; SAMPLE_MODE P0089/P0015/P0001 match `input_examples/README.md`;
  a fully live P0089 run went through Nightshift to Nemotron.) Orchestrator wired to the pack as in section 1, with the **Writer as the
  first real Nemotron call**. In `SAMPLE_MODE`, "replay" means the **Zetaris query
  results** from `tests/fixtures/medtrace/` only. Model steps run the offline
  reasoner on that data and **never replay saved model text** (CLAUDE.md rules 6
  and 8). Arnav's session read the earlier wording ("`SAMPLE_MODE` replay first")
  correctly, against the repo's rules; this line was ambiguous, not the rule.
- [x] API (`POST /run`, `GET /run/{id}`, `GET /status`, `GET /patients`) and
  `run.py` — rule 8. (Arnav, 25 Oct; plus `/run/{id}/identity` and `/feedback`. Docker
  still unverified.)
- [x] **World Model + its 8 conformance checks** (rule 2). Then swap
  `identity.decide`, Arpon's local copy, for yours: same thresholds, 0.85 / 0.82.
  (Arnav, 25 Oct: 8/8 green; `decide` delegates; tune scorecard identical before and after.)
- [ ] H-MEM + feedback (section 2 makes the feedback half possible).

Don't edit `app/domain/` except for the handed-over items in §5.

---

## 5. Handed over from Arpon (25 Oct): he is out of credits for the week

Arpon's open items from `docs/SCAN_2026-10-25.md` are yours now. **Order: World Model +
conformance first (rule 2), then S2, then these.** S2 (`output_examples/`) is a good one
to hand to Anshu if she has room after the Docker fix (S3).

1. **S8** `metadata.json`: mark run.py, POST /run, SAMPLE_MODE and the Zetaris adapter as
   working (it now under-claims). Five minutes.
2. **S7** `coverage.py:229`: a patient lay-term line ("my blue puffer") makes the patient
   column read ABSENT for that medicine.
3. **S19** example_3 (P0013) does not produce `bpmh_not_confirmable`: either fix
   `coverage.bpmh_confirmable` or correct `input_examples/README.md`. Check the ACSQHC
   two-source rule in `docs/PITCH_CLAIMS.md` first.
4. **S22** `identity.py:448`: the "held back because" guard text is false in both demo
   pauses (P0015, P0013), and judges see it.
5. **S21, S20, S32, S33**: range directions, the dead safety-gate rule, zero-trust fusion,
   anchor coverage state. Lower priority.

**Guardrails for `app/domain/` (the pack is scored, so changes can regress silently):**
- Run `.venv/bin/python scripts/eval.py --split tune` before and after, and paste both
  `ALL` lines into your HANDOFF entry.
- `tests/eval/test_scorecard.py` must stay green. Never lower a floor to pass.
- **Never tune on held-out.** Look at `--split heldout` only once, at the end, and
  report a fix found that way as post-hoc (DECISIONS 25 Oct).
- New helpers must be private (`_name`): `test_medtrace_skeleton.py` freezes the
  public surface.
- If you change a generator or fixture, CI's reproducibility step diffs them, so
  commit the regenerated fixtures in the same PR.
