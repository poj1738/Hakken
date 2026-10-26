# Output examples

**Real runs of `input_examples/`, written by `scripts/generate_examples.py`** (`make examples`).
Nothing here is written by hand: each file is a `RunResponse` from the orchestrator, with its
JSONL trace beside it. The human steps (an identity confirmation for examples 1 and 3, a
pharmacist's verdict between examples 4 and 5) are the ones `input_examples/README.md`
documents, applied through the same calls as `POST /run/{id}/identity` and `POST /feedback`.

- `sample_mode/` — `SAMPLE_MODE=true`: recorded Zetaris results, offline agents
  (`offline-heuristic`), no network.
- `live/` — live Zetaris and Nightshift; `model_calls[].routed_model` names the Nemotron that
  answered each call. Synthetic data. Not medical advice.

`partial` means a step degraded rather than failed: a Nightshift call timed out or returned an
upstream error, that step used the grounded template, and the run's `output.caveats` say which.
Findings are still verified against Zetaris. Clinical findings match between modes because
detection is deterministic; the model plans and explains.

| Mode | Example | Patient | Status | Findings | Models | Zetaris queries | Seconds |
|---|---|---|---|---|---|---|---|
| sample_mode | `example_1` | MRN0000015 | success | dose_unconfirmable insulin aspart; omission insulin aspart; dose_unconfirmable warfarin; omission empagliflozin; duplication aspirin/clopidogrel | offline-heuristic | 3 | 0.12 |
| sample_mode | `example_2` | MRN0000089 | success | duplication oxycodone/naloxone; omission gliclazide; frequency oxycodone/naloxone; frequency esomeprazole; stale_listing dapagliflozin | offline-heuristic | 3 | 0.05 |
| sample_mode | `example_3` | MRN0000013 | success | none | offline-heuristic | 2 | 0.03 |
| sample_mode | `example_4_learning_teach` | MRN0000003 | success | omission amlodipine | offline-heuristic | 3 | 0.04 |
| sample_mode | `example_5_learning_learn` | MRN0000007 | success | dose rosuvastatin | offline-heuristic | 3 | 0.03 |
| live | `example_1` | MRN0000015 | success | dose_unconfirmable insulin aspart; omission insulin aspart; dose_unconfirmable warfarin; omission empagliflozin; duplication aspirin/clopidogrel | nvidia/nemotron-3.5-lightning-30b-a3b | 4 | 304.77 |
| live | `example_2` | MRN0000089 | partial | duplication oxycodone/naloxone; omission gliclazide; frequency oxycodone/naloxone; frequency esomeprazole; stale_listing dapagliflozin | nvidia/nemotron-3.5-lightning-30b-a3b | 4 | 526.58 |
| live | `example_3` | MRN0000013 | success | none | nvidia/nemotron-3.5-lightning-30b-a3b | 2 | 32.49 |
| live | `example_4_learning_teach` | MRN0000003 | success | omission amlodipine | nvidia/nemotron-3.5-lightning-30b-a3b | 4 | 281.98 |
| live | `example_5_learning_learn` | MRN0000007 | success | dose rosuvastatin | nvidia/nemotron-3.5-lightning-30b-a3b | 3 | 90.52 |
