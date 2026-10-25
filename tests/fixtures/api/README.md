# Example API responses (PLAN 5.8)

**Hand-written examples for the UI's mock mode, not the output of a real run.** Every
run file says so in `output.caveats`. They will be regenerated from real runs once the
pipeline works, and until then they must never be shown as results, used as
`output_examples/`, or scored against ground truth.

| File | Endpoint | What it shows |
|---|---|---|
| `status.json` | `GET /status` | Zetaris connected, Nightshift online, last model that answered |
| `patients.json` | `GET /patients` | The 13 patients with replay fixtures, from the real Q0 rows (`Q0__admissions.json`, deduped) |
| `run_P0001_trace_partial.json` | `GET /run/{id}` mid-run | `status: running`, timeline up to NORMALISE |
| `run_P0001_done.json` | `GET /run/{id}` finished | Every finding type, six notices, an abstained conflict, grid, trust, trace, model calls |
| `run_P0001_gp_not_found.json` | `GET /run/{id}` | GP and interview `not_found`: UNKNOWN cells, the BPMH banner, `bpmh_not_confirmable` |
| `run_P0002_needs_review.json` | `GET /run/{id}` paused | `status: needs_review`, side-by-side identity review — **for MRN0000015 (P0015, `input_examples/example_1`)**: since the 25 Oct data P0002 no longer goes to review. The filename is kept because `web/src/api.ts` imports it; the UI keys on `patient_id` |
| `feedback_response.json` | `POST /feedback` | A reject as `source_outdated` on `("gp", "daily_dose")`, trust 0.70 → 0.50 — the learning demo's record |

**What is real and what is invented:**
- **Real:** patient demographics; the row ids and text of every row whose id has no
  `-EX`; P0001's two planted omissions (famotidine, empagliflozin/metformin); the
  trust priors (`trust.py`); and **every identity link in
  `run_P0002_needs_review.json`**, which is the actual output of
  `identity.link_identity()` on `Q1__P0015.json`.
- `Finding.detail` values (`atc_class`, `statement`, `conflict`, …) follow the shape
  `detect` writes; on invented findings the values are illustrative.
- **Invented**, to exercise every UI state: every row id containing `-EX` (for
  example `GP-EX0001`), the findings built on them, scores, timings, token counts,
  `req-ex-*` request ids. `run_P0001_gp_not_found.json` deliberately contradicts
  ground truth (P0001's GP record does exist).

Patients are identified by EMR number (`MRN0000001`). The `P0001` in the filenames
is only the fixture naming from PLAN 2.9; the ground-truth key never appears inside
the files.

`tests/unit/test_api_fixtures.py` validates every file against `app/schemas.py`, so
**a schema change must update these files in the same PR** or CI fails.
