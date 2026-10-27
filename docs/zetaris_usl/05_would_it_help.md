# 2b — Would the USL help us in our work?

## Where it helped MedTrace

- **One place for "is this the same medicine?"** Four silos, three coding systems and a brand
  fallback are reconciled once, in `medication_statement`'s activation query
  ([03](03_usl.md)). Every question after that — "which high-risk classes appear in which
  source", "which charted strengths don't exist" — is one `SELECT`.
- **Data quality as a property of the model, not a script.** The primary and foreign keys
  produced rules for free, and one `REGISTER DQ` line gave a clinically meaningful check whose
  violations Zetaris returns as rows (`SHOW DQ INVALID RECORD`). In our data it flags charted
  strengths that no product is made in — every one a real (planted) dose error ([03](03_usl.md)).
- **The model documents itself.** Typed columns, keys, the relationship to `medicine` and a
  description live in Zetaris, where a pharmacist-informaticist or another team can find them,
  rather than in our Python.

## Where it did not (yet)

- **Latency.** The USL answers in ~19 s on our data versus ~4 s for the cached views the
  agents use, so MedTrace's per-run queries stay on the views ([04](04_time_saved.md)).
  Materialisation might close the gap; we could not test it.
- **Identity is not solved by the USL.** Each silo has its own patient ID (MRN, GP practice ID,
  pharmacy customer number, interview ID). The USL unifies *medicines*, not *people*: linking
  the four records of one patient is MedTrace's World Model, which needs fuzzy matching and a
  human decision on near-misses.
- **Free text stays free text.** The patient's own words ("my blue puffer") cannot be resolved
  by a join; the foreign-key rule honestly reports those 1,552 lines as unresolved.

<!-- TEAM: rewrite in our own words -->
**Our own view.** _Placeholder for the team: would we reach for a USL on our next project,
and why? What surprised us? Keep it to what we actually think — e.g. whether the
declare-once mapping felt worth the setup, and how the 19 s latency affected our design._
<!-- /TEAM -->

## Bonus: a project that would benefit, with a forecast

**Project: a cross-LHD medication-safety audit.** A state health department wants a monthly
audit across several Local Health Districts: "for every admission, which high-risk medicines
(APINCHS) were dispensed in the community in the 90 days before admission but are missing
from the admission chart?" Each LHD runs a different EMR; GP and pharmacy data arrive through
different feeds with their own coding (AMT products, AMT packs, PBS items, free text).

**Why a USL fits:** the hard part is exactly what MedTrace's USL already does — resolve every
line to a medicine and a high-risk class across differently-coded sources, once, with data
quality rules that report bad rows — repeated per LHD and re-run every month.

**Forecast of time saved (assumptions stated, not measured):**

| Assumption | Value | Basis |
|---|---|---|
| Sources per LHD | 4 (EMR, GP feed, pharmacy feed, a reference set) | the shape of our project |
| LHDs | 5 | assumption for a mid-sized state audit |
| Mapping steps per new source if hand-coded | ~11 | measured for our 6 sources ([04](04_time_saved.md)) |
| Analyst time per mapping step, first time (find, implement, test) | 2 h | assumption |
| Re-checking mappings each month if hand-coded | 25% of the original effort | assumption: feeds change codes/fields |
| Audit questions asked per month | 10 | assumption |
| Time per extra question, hand-coded vs on a USL | 2 h vs 0.25 h | assumption, scaled from 51 lines of Python vs 1 `SELECT` ([04](04_time_saved.md)) |

- **Build:** hand-coded ≈ 5 LHDs × 11 steps × 2 h = **110 h**; on a USL the same mapping is
  written once per LHD in activation SQL — call it the same 110 h. *No saving on day one.*
- **Each month after:** hand-coded ≈ 27.5 h of re-checking + 10 × 2 h = **47.5 h**; on a USL ≈
  mappings re-checked by `RUN DQ` (~2 h) + 10 × 0.25 h = **4.5 h**.
- **Over the first year:** 43 h saved a month × the 11 months after the build ≈ **470 analyst
  hours saved**, none of it in the first month.

The forecast is only as good as its assumptions; the two that matter most are how often the
feeds change and how many questions get asked. If the audit asks two questions a year, a
hand-written script is the cheaper choice.
