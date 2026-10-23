#!/usr/bin/env python3
"""Programmatic entry point.

    python run.py --input input_examples/example_1.json   # one run, JSON to stdout
    python run.py serve                                   # uvicorn on 0.0.0.0:$PORT

PHASE 5 STUB: the CLI shape is fixed so judges and scripts can rely on it, but
the orchestrator behind it is not written yet. It exits non-zero and says so
rather than printing a plausible-looking fake result.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Hakken agent")
    parser.add_argument("command", nargs="?", choices=["serve"], help="start the API server")
    parser.add_argument("--input", help="path to a JSON run request")
    args = parser.parse_args()

    if args.command == "serve":
        print("not implemented yet: `serve` arrives in Phase 5", file=sys.stderr)
        return 2
    if args.input:
        print("not implemented yet: the agent loop arrives in Phase 4", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
