#!/usr/bin/env python3
"""Record the Data map envelopes from live Zetaris, for SAMPLE_MODE replay.

    python3 scripts/record_data_map.py

Writes ``tests/fixtures/medtrace/<template_id>__<replay_key>.json`` — the
adapter's envelope (``headers``, ``data``, ``total``) and not ``timeUsed``.
Refuses to run when SAMPLE_MODE is on. Prints each file with the adapter's
row count and latency. Does not print settings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.zetaris import REPLAY_DIR, ZetarisClient, ZetarisError  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.data_map import CATALOGUE  # noqa: E402


def main() -> int:
    settings = get_settings()
    if settings.sample_mode:
        print("SAMPLE_MODE is on; refusing to record live envelopes.", file=sys.stderr)
        return 2
    client = ZetarisClient(settings)
    for query in CATALOGUE:
        name = f"{query.template_id}__{query.replay_key}.json"
        try:
            result, record = client.run(
                query.sql, template_id=query.template_id, replay_key=query.replay_key
            )
        except ZetarisError as exc:
            print(f"{name}: {exc}", file=sys.stderr)
            return 1
        envelope = {
            "headers": list(result["headers"]),
            "data": result["data"],
            "total": result.get("total", len(result["data"])),
        }
        path = REPLAY_DIR / name
        path.write_text(json.dumps(envelope, indent=1) + "\n")
        print(f"wrote {path.name}  rows={record.rows}  latency_ms={record.ms}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
