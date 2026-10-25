# Sample inputs

`RunRequest` bodies (`app/schemas.py`) for `POST /run` and `python run.py --input`.
All patients are synthetic. `patient_id` is the EMR MRN, never a ground-truth key.
Each has committed replay fixtures in `tests/fixtures/medtrace/`, so all five run
under `SAMPLE_MODE=true` with no Zetaris, no Nightshift and no network.

| File | Patient | What a correct run shows |
|---|---|---|
| `example_1.json` | MRN0000015 (P0015) | Stops at `needs_review`: one identity near-miss for a human. Once confirmed: warfarin and insulin aspart dose conflicts (APINCHS), an insulin omission, an empagliflozin omission, an aspirin/clopidogrel duplication. |
| `example_2.json` | MRN0000089 (P0089) | Straight through, no review: oxycodone/naloxone duplication and frequency error (APINCHS), gliclazide omission, esomeprazole frequency, a stale dapagliflozin listing. |
| `example_3.json` | MRN0000013 (P0013) | Stops at `needs_review`: is the bedside interview this patient? Once confirmed, only two of four sources exist (no GP, no pharmacy record), so: `bpmh_not_confirmable`, coverage gaps, and **no findings invented**. Missing sources stay *unknown*, never "not taking". |
| `example_4_learning_teach.json` | MRN0000003 (P0003) | **Learning demo, step 1.** Candesartan dose abstains: the GP list (16 mg, a year old) against a fill six days ago (8 mg). The pharmacist rejects the GP dose as outdated (`source_outdated`, `source="gp"`, `attribute="daily_dose"`). |
| `example_5_learning_learn.json` | MRN0000007 (P0007) | **Learning demo, step 2, run after step 1's feedback.** Rosuvastatin resolves to the pharmacy's 10 mg, and a dose finding appears: the chart says 20 mg, copied from the stale GP list. Before the feedback, the same run abstains and shows no finding. |

The learning pair is staged by `scripts/generate_synthetic.py` (`LEARNING_PAIR`) and
recorded in the ground truth as `learning_demo`. It is not presented as chance.
`tests/unit/test_learning_demo.py` pins both halves on these fixtures.

`output_examples/` must come from real runs of these inputs (`make examples`),
never written by hand.
