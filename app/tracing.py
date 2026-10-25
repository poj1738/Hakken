"""JSONL trace writer with secret masking.

One file per run at `logs/trace-<run_id>.jsonl`, one `TraceEvent` per line: the
hackathon's official field set plus our extensions (step, plain-English
message, SQL, row count, the meterless receipt summary). The same events are
returned in `RunResponse.trace`, so the UI timeline and the file never disagree.

Masking is belt and braces: no code path puts a secret into an event, but every
event is scrubbed before it is written anyway -- the configured secret values
themselves, and anything shaped like a bearer token.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT, Settings, get_settings
from app.schemas import TraceEvent

LOG_DIR = REPO_ROOT / "logs"
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}")
MASK = "***"


class Tracer:
    """Collects one run's events, in order, and appends each to the run's JSONL file."""

    def __init__(self, run_id: str, *, settings: Settings | None = None, log_dir: Path | None = LOG_DIR) -> None:
        self.run_id = run_id
        self.events: list[TraceEvent] = []
        settings = settings or get_settings()
        self._secrets = [s for s in (settings.meterless_runtime_token.get_secret_value(),
                                     settings.zetaris_api_key.get_secret_value()) if len(s.strip()) >= 6]
        self.path: Path | None = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            self.path = log_dir / f"trace-{run_id}.jsonl"

    def mask(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        return _BEARER.sub(f"Bearer {MASK}", text)

    def emit(self, agent_name: str, action: str, *, step: str | None = None, message: str | None = None,
             **fields: Any) -> TraceEvent:
        event = TraceEvent(run_id=self.run_id, agent_name=agent_name, action=action, step=step,
                           message=message, **fields)
        line = self.mask(event.model_dump_json())
        event = TraceEvent.model_validate_json(line)
        self.events.append(event)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return event

    @property
    def log_file(self) -> str:
        if self.path is None:
            return ""
        try:
            return str(self.path.relative_to(REPO_ROOT))
        except ValueError:
            return str(self.path)


def read_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
