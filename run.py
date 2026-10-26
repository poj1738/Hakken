#!/usr/bin/env python3
"""Programmatic entry point.

    python3 run.py --input input_examples/example_2.json   # one run, RunResponse JSON to stdout
    python3 run.py --input input_examples/example_1.json --confirm patient:INT00015
    python3 run.py serve                                   # the API on $HOST:$PORT (127.0.0.1)

`SAMPLE_MODE=true` runs the real agent logic on the recorded Zetaris data with offline
agents: no Zetaris, no Nightshift, no network.

A run that stops at `needs_review` is printed as such: a human decides identity. Pass
`--confirm <candidate_id>` (or `--reject`) to record that decision and continue -- the
same call as `POST /run/{id}/identity`.

Exit codes: 0 success / partial / needs_review, 1 error, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MedTrace (Team Hakken)")
    parser.add_argument("command", nargs="?", choices=["serve"], help="start the API server")
    parser.add_argument("--input", help="path to a JSON RunRequest, e.g. input_examples/example_2.json")
    parser.add_argument("--confirm", action="append", default=[], metavar="CANDIDATE",
                        help="identity near-miss to confirm as the same person (repeatable)")
    parser.add_argument("--reject", action="append", default=[], metavar="CANDIDATE",
                        help="identity near-miss to reject as a different person (repeatable)")
    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        from app.config import get_settings
        # Loopback by default: the API has no auth, so it should not answer the venue's
        # Wi-Fi (scan S30). The Docker image sets HOST=0.0.0.0 inside the container.
        uvicorn.run("app.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=get_settings().port)
        return 0
    if not args.input:
        parser.print_help()
        return 2

    from app.orchestrator import Orchestrator, UnknownPatient
    from app.schemas import IdentityDecisionRequest, RunRequest

    try:
        request = RunRequest.model_validate_json(Path(args.input).read_text())
    except (OSError, ValueError) as exc:
        print(f"bad input {args.input}: {exc}", file=sys.stderr)
        return 2
    orch = Orchestrator()
    try:
        response = orch.start(request)
    except UnknownPatient as exc:
        print(str(exc), file=sys.stderr)
        return 2
    decisions = [(c, True) for c in args.confirm] + [(c, False) for c in args.reject]
    for candidate, same in decisions:
        if response.status != "needs_review":
            break
        response = orch.resume(response.run_id, IdentityDecisionRequest(candidate_id=candidate, same_person=same))
    print(json.dumps(response.model_dump(mode="json"), indent=2))
    return 1 if response.status == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
