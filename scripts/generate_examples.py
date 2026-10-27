#!/usr/bin/env python3
"""Write output_examples/ from real runs of input_examples/ (CLAUDE.md rule 6, scan S2).

    python3 scripts/generate_examples.py                 # SAMPLE_MODE (no services)
    python3 scripts/generate_examples.py --mode live     # live Zetaris + Nightshift
    python3 scripts/generate_examples.py --mode both

Every file is a real `Orchestrator` run -- nothing is written by hand. Each mode gets a
fresh, in-memory World Model and H-MEM, so a run never inherits a decision or a trust
change from an earlier session (the World Model would otherwise remember example 1's
identity decision and skip the pause the example exists to show).

The human steps a run needs are the ones `input_examples/README.md` documents, applied
through the same calls the API uses:
  example_1, example_3  pause at needs_review; the paused response is saved, then the
                        documented candidate is confirmed (POST /run/{id}/identity)
  example_4 -> 5        the teach run, then the documented verdict -- reject the GP daily
                        dose as source_outdated (POST /feedback) -- then the learn run

Output per run: `<mode>/<example>.json` (RunResponse), `<example>.needs_review.json`
where it paused, `<example>.trace.jsonl`, and `example_4_learning_teach.feedback.json`.
`output_examples/README.md` summarises what each run produced, from the files themselves.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.engines.hmem import HMEM  # noqa: E402
from app.engines.world_model import WorldModel  # noqa: E402
from app.feedback import apply_feedback  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.schemas import FeedbackRequest, IdentityDecisionRequest, RunRequest, RunResponse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "input_examples"
OUT = ROOT / "output_examples"
ORDER = ["example_1", "example_2", "example_3", "example_4_learning_teach", "example_5_learning_learn"]
#: The identity decisions input_examples/README.md documents ("once confirmed").
CONFIRM = {"example_1": "patient:INT00015", "example_3": "patient:INT00013"}


def _write(path: Path, model) -> None:
    path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")


def run_mode(mode: str, out_root: Path = OUT, settings=None, only: list[str] | None = None) -> list[dict]:
    settings = (settings or get_settings()).model_copy(update={"sample_mode": mode == "sample_mode"})
    out = out_root / mode
    out.mkdir(parents=True, exist_ok=True)
    traces = Path(tempfile.mkdtemp(prefix="hakken-traces-"))
    orch = Orchestrator(settings, log_dir=traces, world=WorldModel(namespace="examples"), hmem=HMEM())
    summary = []
    for name in (n for n in ORDER if not only or n in only):
        req = RunRequest.model_validate_json((INPUTS / f"{name}.json").read_text())
        t0 = time.monotonic()
        print(f"[{mode}] {name} ({req.patient_id}) ...", flush=True)
        resp: RunResponse = orch.start(req)
        if resp.status == "needs_review" and name in CONFIRM:
            _write(out / f"{name}.needs_review.json", resp)
            resp = orch.resume(resp.run_id, IdentityDecisionRequest(candidate_id=CONFIRM[name], same_person=True))
        _write(out / f"{name}.json", resp)
        shutil.copy(traces / f"trace-{resp.run_id}.jsonl", out / f"{name}.trace.jsonl")
        if name == "example_4_learning_teach":
            fb = apply_feedback(orch, FeedbackRequest(
                run_id=resp.run_id, target_id="grid:candesartan:daily_dose", verdict="reject",
                reason="source_outdated", source="gp", attribute="daily_dose"))
            _write(out / f"{name}.feedback.json", fb)
        summary.append({"mode": mode, "name": name, "patient": req.patient_id, "status": resp.status,
                        "findings": [f"{f.type.value} {f.generic}" for f in resp.findings],
                        "models": sorted({c.routed_model for c in resp.model_calls if c.routed_model}),
                        "queries": resp.query_count, "seconds": round(time.monotonic() - t0, 1)})
        print(f"[{mode}] {name}: {resp.status}, {len(resp.findings)} findings, "
              f"{summary[-1]['seconds']}s, models {summary[-1]['models']}", flush=True)
    shutil.rmtree(traces, ignore_errors=True)
    return summary


def write_readme() -> None:
    lines = [
        "# Output examples",
        "",
        "**Real runs of `input_examples/`, written by `scripts/generate_examples.py`** (`make examples`).",
        "Nothing here is written by hand: each file is a `RunResponse` from the orchestrator, with its",
        "JSONL trace beside it. The human steps (an identity confirmation for examples 1 and 3, a",
        "pharmacist's verdict between examples 4 and 5) are the ones `input_examples/README.md`",
        "documents, applied through the same calls as `POST /run/{id}/identity` and `POST /feedback`.",
        "",
        "- `sample_mode/` — `SAMPLE_MODE=true`: recorded Zetaris results, offline agents",
        "  (`offline-heuristic`), no network.",
        "- `live/` — live Zetaris and Nightshift; `model_calls[].routed_model` names the Nemotron that",
        "  answered each call. Synthetic data. Not medical advice.",
        "",
        "`partial` means a step degraded rather than failed: a Nightshift call timed out or returned an",
        "upstream error, that step used the grounded template, and the run's `output.caveats` say which.",
        "Findings are still verified against Zetaris. Clinical findings match between modes because",
        "detection is deterministic; the model plans and explains.",
        "",
        "| Mode | Example | Patient | Status | Findings | Models | Zetaris queries | Seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mode in ("sample_mode", "live"):
        for name in ORDER:
            path = OUT / mode / f"{name}.json"
            if not path.exists():
                continue
            r = RunResponse.model_validate_json(path.read_text())
            findings = "; ".join(f"{f.type.value} {f.generic}" for f in r.findings) or "none"
            models = ", ".join(sorted({c.routed_model for c in r.model_calls if c.routed_model})) or "—"
            lines.append(f"| {mode} | `{name}` | {r.patient_id} | {r.status} | {findings} | {models} | "
                         f"{r.query_count} | {r.execution_time_seconds} |")
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=["sample", "live", "both"], default="sample")
    # Re-record some examples only (a live run takes minutes each). example_5 learns from the
    # verdict applied after example_4, so the generator refuses to run 5 without 4.
    ap.add_argument("--only", nargs="+", choices=ORDER, metavar="EXAMPLE")
    args = ap.parse_args()
    if args.only and "example_5_learning_learn" in args.only and "example_4_learning_teach" not in args.only:
        ap.error("example_5_learning_learn needs example_4_learning_teach in the same run")
    modes = {"sample": ["sample_mode"], "live": ["live"], "both": ["sample_mode", "live"]}[args.mode]
    for mode in modes:
        run_mode(mode, only=args.only)
    write_readme()
    print(f"wrote {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
