# Ported from Meterless World Model, reference/src/store.ts
# (github.com/Meterless/Meterless, engines/world-model), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""Event-sourced canonical store. State is a fold over an append-only event log;
views are projections of the fold. `storage="local"` persists one JSON file per
namespace (`<directory>/.world/<namespace>.json`) and replays it on load. Every
mutation writes an audit entry with a strictly increasing `seq`.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

EPOCH = "1970-01-01T00:00:00.000Z"


@dataclass
class FoldedState:
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    relationships: dict[str, dict[str, Any]] = field(default_factory=dict)
    facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # aliasId -> primaryId


class EventStore:
    def __init__(self, namespace: str, storage: Literal["memory", "local"] = "memory",
                 directory: Path | str | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.observations: dict[str, dict[str, Any]] = {}
        self.stories: dict[str, dict[str, Any]] = {}
        self.scores: list[dict[str, Any]] = []
        self.merge_queue: list[dict[str, Any]] = []
        self.state = FoldedState()
        self._seq = 0
        self._audit_seq = 0
        self._file: Path | None = None
        if storage == "local":
            folder = Path(directory or Path.cwd()) / ".world"
            folder.mkdir(parents=True, exist_ok=True)
            self._file = folder / f"{namespace}.json"
            if self._file.exists():
                saved = json.loads(self._file.read_text(encoding="utf-8"))
                self.audit = saved.get("audit", [])
                self._audit_seq = self.audit[-1]["seq"] if self.audit else 0
                self.observations = dict(saved.get("observations", []))
                self.stories = dict(saved.get("stories", []))
                self.scores = saved.get("scores", [])
                self.merge_queue = saved.get("mergeQueue", [])
                for event in saved.get("events", []):
                    self._apply(event, new=False)

    def append(self, kind: str, payload: dict[str, Any], at: str) -> dict[str, Any]:
        event = {"id": f"evt_{self._seq + 1}", "seq": self._seq + 1, "kind": kind, "payload": payload,
                 "schemaVersion": 1, "at": at}
        self._apply(event, new=True)
        return event

    def _apply(self, event: dict[str, Any], *, new: bool) -> None:
        self._seq = max(self._seq, event["seq"])
        self.events.append(event)
        self._fold(event)
        if new:
            self.persist()

    def _fold(self, event: dict[str, Any]) -> None:
        kind, p = event["kind"], event["payload"]
        st = self.state
        if kind == "upsertEntity":
            existing = st.entities.get(p["id"])
            if existing is not None:
                existing["attrs"] = {**existing.get("attrs", {}), **p.get("attrs", {})}
                existing["updatedAt"] = p.get("updatedAt")
                existing["source"] = p.get("source")
                name = p.get("name")
                if name and name not in existing.setdefault("aliases", []):
                    existing["aliases"].append(name)
                if name:
                    existing["name"] = name
            else:
                st.entities[p["id"]] = copy.deepcopy(p)
        elif kind == "upsertContext":
            existing = st.contexts.get(p["id"])
            if existing is not None:
                existing["attrs"] = {**existing.get("attrs", {}), **p.get("attrs", {})}
                existing["updatedAt"] = p.get("updatedAt")
            else:
                st.contexts[p["id"]] = copy.deepcopy(p)
        elif kind == "relate":
            # Superseding: a new open edge with the same (from, type, context) but a
            # different target CLOSES the previous open edge.
            for other in st.relationships.values():
                if (other["from"] == p["from"] and other["type"] == p["type"]
                        and (other.get("context") or "") == (p.get("context") or "")
                        and other["to"] != p["to"] and not other.get("validTo") and not other.get("supersededBy")):
                    other["validTo"] = p.get("validFrom") or p.get("createdAt")
                    other["supersededBy"] = p["id"]
            if p["id"] not in st.relationships:
                st.relationships[p["id"]] = copy.deepcopy(p)
        elif kind == "assertFact":
            if p["id"] not in st.facts:
                st.facts[p["id"]] = copy.deepcopy(p)
        elif kind == "alias":
            st.aliases[p["aliasId"]] = p["primaryId"]
        # snapshot / tombstone / view-rebuild: no state change

    def fold_until(self, at: str) -> FoldedState:
        """Replay the log up to and including a timestamp: the snapshot view."""
        scratch = EventStore("scratch")
        for event in self.events:
            if event["at"] <= at:
                scratch._fold(event)
        return scratch.state

    def resolve_alias(self, id_: str) -> str:
        cur, seen = id_, set()
        while cur in self.state.aliases and cur not in seen:
            seen.add(cur)
            cur = self.state.aliases[cur]
        return cur

    def log_audit(self, kind: str, actor: str, summary: str, event_id: str | None = None,
                  run_id: str | None = None, at: str | None = None) -> None:
        self._audit_seq += 1
        entry = {"seq": self._audit_seq, "at": at or EPOCH, "kind": kind, "actor": actor, "summary": summary}
        if event_id:
            entry["eventId"] = event_id
        if run_id:
            entry["runId"] = run_id
        self.audit.append(entry)
        self.persist()

    def persist(self) -> None:
        if self._file is None:
            return
        data = {"events": self.events, "audit": self.audit, "observations": list(self.observations.items()),
                "stories": list(self.stories.items()), "scores": self.scores, "mergeQueue": self.merge_queue}
        self._file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
