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

| Mode | Example | Patient | Status | Findings | Models | Zetaris queries | Seconds |
|---|---|---|---|---|---|---|---|
| sample_mode | `example_1` | MRN0000015 | success | dose_unconfirmable insulin aspart; omission insulin aspart; dose_unconfirmable warfarin; omission empagliflozin; duplication aspirin/clopidogrel | offline-heuristic | 3 | 0.08 |
| sample_mode | `example_2` | MRN0000089 | success | duplication oxycodone/naloxone; omission gliclazide; frequency oxycodone/naloxone; frequency esomeprazole; stale_listing dapagliflozin | offline-heuristic | 3 | 0.04 |
| sample_mode | `example_3` | MRN0000013 | success | none | offline-heuristic | 2 | 0.02 |
| sample_mode | `example_4_learning_teach` | MRN0000003 | success | omission amlodipine | offline-heuristic | 3 | 0.03 |
| sample_mode | `example_5_learning_learn` | MRN0000007 | success | dose rosuvastatin | offline-heuristic | 3 | 0.02 |
