# For Arnav's next session — read this first

**Written 25 Oct by Arpon's session, for Arnav's Claude Code session.** Nobody is
reading PRs, so everything you need from Arpon's side is here. Work top to bottom.
Tick items off by editing this file in your PR, and say what you did in your
`docs/HANDOFF.md` entry.

Before you start: `git pull origin main`, `make setup`, `make test`. Then
`make synth` — `data/synthetic/silos/` is gitignored, and the generator tests and
the scorecard **skip** without it. A skip there is a missing build, not a pass.

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

- [ ] **`Finding.detail: dict[str, Any] = {}`**, passed through from
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
- [ ] **`FeedbackRequest.source: Source | None` and `.attribute: str | None`**,
  validated as required when `reason == "source_outdated"`.
  - PLAN 5.7's `-0.20` lands on *that* `(source, attribute)` H-MEM record.
  - That's the demo's "reject a GP dose as outdated → patient B resolves
    differently".
- [ ] Update `tests/fixtures/api/*.json` in the same PR — `test_api_fixtures.py`
  fails otherwise.
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

- [ ] Meterless adapter (Nightshift) — rules 2 and 3.
- [ ] Orchestrator wired to the pack as in section 1, with the **Writer as the
  first real Nemotron call** — `SAMPLE_MODE` replay first, then live.
- [ ] API (`POST /run`, `GET /run/{id}`, `GET /status`, `GET /patients`) and
  `run.py` — rule 8.
- [ ] **World Model + its 8 conformance checks** (rule 2). Then swap
  `identity.decide`, Arpon's local copy, for yours: same thresholds, 0.85 / 0.82.
- [ ] H-MEM + feedback (section 2 makes the feedback half possible).

Don't edit `app/domain/` — if the pack needs a change, write it in your
HANDOFF entry for Arpon's session.
