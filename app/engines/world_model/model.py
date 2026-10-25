# Ported from Meterless World Model, reference/src/index.ts
# (github.com/Meterless/Meterless, engines/world-model), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""World Model facade: event-sourced, deterministic, single writer.

Every write carries provenance (`kind` + `at`) or is refused. Merges are never
destructive: the loser becomes an alias that still resolves. Relationships are
bitemporal: a superseding edge closes the previous one, and graph queries answer
"now" or "as of" a past instant. The reference is async; this port is synchronous,
and a lock gives the same single-writer discipline.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.engines.world_model.ingest import iso_from_ms, run_ingest_pipeline, world_state_shape
from app.engines.world_model.resolve import decide, name_similarity
from app.engines.world_model.stable_ids import (
    canonical_json,
    context_id_from_attrs,
    entity_id_from_name,
    external_id,
    fact_id,
    relationship_id,
)
from app.engines.world_model.store import EventStore

ConflictPolicy = Literal["most-recent-wins", "highest-confidence-wins", "source-priority"]


class ProvenanceError(ValueError):
    """No provenance, no write (conformance prov-001)."""


def _iso(at: Any) -> str:
    if isinstance(at, datetime):
        dt = at.astimezone(timezone.utc) if at.tzinfo else at.replace(tzinfo=timezone.utc)
        return iso_from_ms(int(dt.timestamp() * 1000))
    return str(at)


def _valid_at(rel: dict[str, Any], at: str) -> bool:
    if rel.get("validFrom") and at < rel["validFrom"]:
        return False
    if rel.get("validTo") and at >= rel["validTo"]:
        return False
    return True


class WorldModel:
    def __init__(self, *, namespace: str, storage: Literal["memory", "local"] = "memory",
                 directory: Path | str | None = None, clock: Callable[[], datetime] | None = None,
                 conflict_policy: ConflictPolicy = "most-recent-wins", source_priority: list[str] | None = None,
                 auto_merge_at: float = 0.85, review_lower: float = 0.82) -> None:
        if not namespace:
            raise ValueError("WorldModel: namespace is required")
        self._store = EventStore(namespace, storage, directory)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._policy = conflict_policy
        self._priority = source_priority or []
        self._auto_merge_at = auto_merge_at
        self._review_lower = review_lower
        self._lock = threading.RLock()

    # -- provenance ---------------------------------------------------------------

    @staticmethod
    def _provenance(source: dict[str, Any] | None) -> dict[str, Any]:
        if not source or not source.get("kind") or source.get("at") is None:
            raise ProvenanceError("World Model: every write carries provenance (kind + at). No provenance, no write.")
        return {**source, "at": _iso(source["at"])}

    # -- writes -------------------------------------------------------------------

    def upsert_entity(self, *, type: str, source: dict[str, Any] | None, name: str | None = None,
                      external_key: dict[str, str] | None = None, attrs: dict[str, Any] | None = None,
                      state: str = "active") -> dict[str, Any]:
        with self._lock:
            prov = self._provenance(source)
            name = name or (attrs or {}).get("name")
            if external_key:
                id_ = external_id(type, external_key["system"], external_key["id"])
            elif name:
                id_ = entity_id_from_name(type, name)
            else:
                raise ValueError("World Model: name-keyed entities need a name (or provide an external_key)")
            # Resolution pass for name-keyed entities: near-duplicates of the same type
            # auto-merge (alias event) or queue for operator review.
            if not external_key and name:
                for other in list(self._store.state.entities.values()):
                    if other["type"] != type or other["id"] == id_ or not other.get("name"):
                        continue
                    similarity = name_similarity(name, other["name"])
                    decision = decide(similarity, self._auto_merge_at, self._review_lower)
                    if decision == "auto-merge":
                        self._store.append("alias", {"aliasId": id_, "primaryId": other["id"], "mergedAt": prov["at"],
                                                     "mergedBy": "resolver", "reason": f"similarity {similarity:.3f}"},
                                           prov["at"])
                        self._store.log_audit("auto-merge", "resolver", f"{name} -> {other['name']} ({similarity:.3f})",
                                              at=prov["at"])
                        return self._fold_entity(other["id"], type, attrs, prov, name, state)
                    if decision == "review" and not any(
                            {p["leftId"], p["rightId"]} == {id_, other["id"]} for p in self._store.merge_queue):
                        self._store.merge_queue.append({
                            "id": f"merge_{len(self._store.merge_queue) + 1}", "leftId": id_, "rightId": other["id"],
                            "leftName": name, "rightName": other["name"], "similarity": similarity,
                            "reason": "name similarity in review band [0.82, 0.85)", "status": "pending",
                            "proposedAt": prov["at"]})
                        self._store.log_audit("merge-proposed", "resolver",
                                              f"{name} ~ {other['name']} ({similarity:.3f}) queued", at=prov["at"])
            return self._fold_entity(id_, type, attrs, prov, name, state)

    def _fold_entity(self, id_: str, type_: str, attrs: dict[str, Any] | None, prov: dict[str, Any],
                     name: str | None, state: str = "active") -> dict[str, Any]:
        resolved = self._store.resolve_alias(id_)
        entity = {"type": type_, "id": resolved, "attrs": dict(attrs or {}), "schemaVersion": 1, "source": prov,
                  "createdAt": prov["at"], "updatedAt": prov["at"], "name": name, "aliases": [name] if name else [],
                  "state": state}
        event = self._store.append("upsertEntity", entity, prov["at"])
        self._store.log_audit("upsertEntity", prov.get("by") or "system", f"{resolved} ({type_})", event["id"],
                              prov.get("runId"), prov["at"])
        return self._store.state.entities[resolved]

    def upsert_context(self, *, type: str, source: dict[str, Any] | None, external_key: dict[str, str] | None = None,
                       attrs: dict[str, Any] | None = None, parent: str | None = None) -> dict[str, Any]:
        with self._lock:
            prov = self._provenance(source)
            id_ = (external_id(type, external_key["system"], external_key["id"]) if external_key
                   else context_id_from_attrs(type, attrs or {}, parent))
            context = {"type": type, "id": id_, "attrs": dict(attrs or {}), "parent": parent, "schemaVersion": 1,
                       "source": prov, "createdAt": prov["at"], "updatedAt": prov["at"]}
            event = self._store.append("upsertContext", context, prov["at"])
            self._store.log_audit("upsertContext", prov.get("by") or "system", f"{id_} ({type})", event["id"],
                                  prov.get("runId"), prov["at"])
            return self._store.state.contexts[id_]

    def relate(self, *, from_: str, type: str, to: str, source: dict[str, Any] | None, context: str | None = None,
               attrs: dict[str, Any] | None = None, valid_from: str | None = None,
               valid_to: str | None = None) -> dict[str, Any]:
        with self._lock:
            prov = self._provenance(source)
            a, b = self._store.resolve_alias(from_), self._store.resolve_alias(to)
            id_ = relationship_id(a, type, b, context, valid_from)
            if id_ in self._store.state.relationships:
                return self._store.state.relationships[id_]  # content-addressed no-op
            rel = {"id": id_, "from": a, "type": type, "to": b, "context": context, "attrs": attrs,
                   "validFrom": valid_from or prov["at"], "validTo": valid_to, "schemaVersion": 1, "source": prov,
                   "createdAt": prov["at"]}
            event = self._store.append("relate", rel, prov["at"])
            self._store.log_audit("relate", prov.get("by") or "system", f"{a} -[{type}]-> {b}", event["id"],
                                  prov.get("runId"), prov["at"])
            return self._store.state.relationships[id_]

    def assert_fact(self, *, about: str, predicate: str, value: Any, source: dict[str, Any] | None,
                    confidence: float = 0.5, context: str | None = None) -> dict[str, Any]:
        with self._lock:
            prov = self._provenance(source)
            subject = self._store.resolve_alias(about)
            id_ = fact_id(subject, predicate, value, prov["at"], prov["kind"], prov.get("url"))
            if id_ in self._store.state.facts:
                return self._store.state.facts[id_]
            fact = {"id": id_, "about": subject, "predicate": predicate, "value": value, "confidence": confidence,
                    "context": context, "source": prov, "assertedAt": prov["at"]}
            rivals = [f for f in self._store.state.facts.values()
                      if f["about"] == subject and f["predicate"] == predicate and not f.get("supersededBy")]
            winner = fact
            for rival in rivals:
                if self._policy == "highest-confidence-wins":
                    wins = rival["confidence"] > winner["confidence"]
                elif self._policy == "source-priority":
                    wins = self._rank(rival["source"]["kind"]) < self._rank(winner["source"]["kind"])
                else:
                    wins = rival["assertedAt"] > winner["assertedAt"]
                if wins:
                    winner = rival
            event = self._store.append("assertFact", fact, prov["at"])
            for f in [fact, *rivals]:
                if f["id"] != winner["id"]:
                    self._store.state.facts[f["id"]]["supersededBy"] = winner["id"]
            if subject not in self._store.state.entities:
                self._store.append("upsertEntity", {
                    "type": subject.split(":")[0] if ":" in subject else "entity", "id": subject, "attrs": {},
                    "schemaVersion": 1, "source": prov, "createdAt": prov["at"], "updatedAt": prov["at"],
                    "aliases": [], "state": "emerging"}, prov["at"])
            entity = self._store.state.entities[subject]
            entity["attrs"][predicate] = winner["value"]
            entity["updatedAt"] = prov["at"]
            self._store.log_audit("assertFact", prov.get("by") or "system",
                                  f"{subject}.{predicate} = {canonical_json(winner['value'])} ({self._policy})",
                                  event["id"], prov.get("runId"), prov["at"])
            self._store.persist()
            return self._store.state.facts[id_]

    def _rank(self, kind: str) -> int:
        return self._priority.index(kind) if kind in self._priority else 1 << 53

    # -- ingest -------------------------------------------------------------------

    def ingest(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            def upsert(obs: dict[str, Any]) -> tuple[str, list[str]]:
                prov = self._provenance({**obs["source"], "at": obs["at"]})
                type_ = obs.get("type") or "item"
                entity = self._fold_entity(external_id(type_, "ingest", obs["externalId"]), type_,
                                           {"title": obs.get("title"), "text": obs.get("text")}, prov, obs.get("title"))
                ids: list[str] = []
                for mention in obs.get("entities") or []:
                    mid = entity_id_from_name(mention["type"], mention["name"])
                    self._fold_entity(mid, mention["type"], None, prov, mention["name"])
                    target = self._store.resolve_alias(mid)
                    ids.append(target)
                    rid = relationship_id(entity["id"], "mentions", target)
                    if rid not in self._store.state.relationships:
                        self._store.append("relate", {"id": rid, "from": entity["id"], "type": "mentions", "to": target,
                                                      "validFrom": prov["at"], "schemaVersion": 1, "source": prov,
                                                      "createdAt": prov["at"]}, prov["at"])
                return entity["id"], sorted(ids)

            return run_ingest_pipeline(self._store, observations, upsert, lambda: self._clock().timestamp() * 1000)

    # -- reads --------------------------------------------------------------------

    def view(self, name: str) -> GraphView:
        if name == "graph":
            return GraphView(self._store)
        raise ValueError(f'World Model: unknown view "{name}"')

    def entity_at(self, id_: str, at: str) -> dict[str, Any] | None:
        """Snapshot view: entity state as of a timestamp, by replaying events with at <= timestamp."""
        iso = f"{at}T23:59:59.999Z" if len(at) == 10 else at
        state = self._store.fold_until(iso)
        cur, seen = id_, set()
        while cur in state.aliases and cur not in seen:
            seen.add(cur)
            cur = state.aliases[cur]
        return state.entities.get(cur)

    def facts_about(self, id_: str) -> list[dict[str, Any]]:
        rid = self._store.resolve_alias(id_)
        return sorted((f for f in self._store.state.facts.values() if f["about"] == rid), key=lambda f: f["assertedAt"])

    # -- operator -----------------------------------------------------------------

    def merge_queue(self) -> list[dict[str, Any]]:
        return self._store.merge_queue

    def approve_merge(self, proposal_id: str, by: str) -> None:
        with self._lock:
            p = next((m for m in self._store.merge_queue if m["id"] == proposal_id and m["status"] == "pending"), None)
            if p is None:
                raise KeyError(f"World Model: no pending merge proposal {proposal_id}")
            at = _iso(self._clock())
            p.update(status="approved", resolvedAt=at, resolvedBy=by)
            self._store.append("alias", {"aliasId": p["leftId"], "primaryId": p["rightId"], "mergedAt": at,
                                         "mergedBy": by, "reason": p["reason"]}, at)
            self._store.log_audit("merge-approved", by, f"{p['leftName']} -> {p['rightName']}", at=at)

    def reject_merge(self, proposal_id: str, by: str) -> None:
        with self._lock:
            p = next((m for m in self._store.merge_queue if m["id"] == proposal_id and m["status"] == "pending"), None)
            if p is None:
                raise KeyError(f"World Model: no pending merge proposal {proposal_id}")
            p.update(status="rejected", resolvedAt=_iso(self._clock()), resolvedBy=by)
            self._store.log_audit("merge-rejected", by, f"{p['leftName']} stays separate from {p['rightName']}")
            self._store.persist()

    def audit(self) -> list[dict[str, Any]]:
        return self._store.audit

    def events(self) -> list[dict[str, Any]]:
        return self._store.events

    def state_shape(self) -> dict[str, Any]:
        return copy.deepcopy(world_state_shape(self._store))

    def state_shape_canonical(self) -> str:
        return canonical_json(world_state_shape(self._store))


class GraphView:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    def entity(self, id_: str) -> dict[str, Any] | None:
        return self._store.state.entities.get(self._store.resolve_alias(id_))

    def neighbors_of(self, id_: str, *, via: str | None = None, in_context: str | None = None,
                     at: str | None = None) -> list[dict[str, Any]]:
        rid = self._store.resolve_alias(id_)
        out = []
        for rel in self._store.state.relationships.values():
            if via and rel["type"] != via:
                continue
            if in_context and rel.get("context") != in_context:
                continue
            if at and not _valid_at(rel, at):
                continue
            if not at and rel.get("validTo"):
                continue  # closed edges are excluded from "now" queries
            other = rel["to"] if rel["from"] == rid else rel["from"] if rel["to"] == rid else None
            if other and other in self._store.state.entities:
                out.append(self._store.state.entities[other])
        return sorted(out, key=lambda e: e["id"])

    def incoming(self, id_: str, *, via: str | None = None) -> list[dict[str, Any]]:
        rid = self._store.resolve_alias(id_)
        out = [self._store.state.entities[r["from"]] for r in self._store.state.relationships.values()
               if r["to"] == rid and (not via or r["type"] == via) and not r.get("validTo")
               and r["from"] in self._store.state.entities]
        return sorted(out, key=lambda e: e["id"])
