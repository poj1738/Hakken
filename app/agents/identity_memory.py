"""The World Model in the product: shared, provenance-carrying identity state.

Every patient record a run links is written to the World Model as
`patient:<source>:<id>` (PLAN 5.5), with mandatory provenance -- where it came from
(Zetaris, the view, the query), when, and which run. A confirmed link is a
`same-person-as` edge, and the Executor reads the patient's linked records back from
the World Model's graph to decide whose medicines to read.

A pharmacist's identity decision is written too, so **the next run for that patient
does not ask again**: a near-miss with a recorded decision is resolved from the World
Model, and the trace says which decision and its audit `seq`. That is the user-facing
feature: shared state across runs and agents, with every write traceable.

Each edge carries the candidate's source as its `context`: the reference store closes
an open edge when a new one with the same (from, type, context) arrives, which is
right for "this patient's GP record" (one GP record supersedes another) and wrong
across sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain.packs.medtrace.types import IdentityLink, SourceRow
from app.engines.world_model import WorldModel

SAME = "same-person-as"
DISTINCT = "distinct-from"


def entity_id(record_key: str) -> str:
    """`gp:GPP000015` -> `patient:gp:GPP000015`, the World Model id."""
    return f"patient:{record_key}"


def _now() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _upsert(world: WorldModel, row: SourceRow, source: dict[str, Any]) -> str:
    entity = world.upsert_entity(
        type="patient", external_key={"system": row.source, "id": row.source_patient_id}, source=source,
        attrs={"name": f"{row.name_given or ''} {row.name_family or ''}".strip() or None, "dob_raw": row.dob_raw,
               "record_key": row.record_key})
    return entity["id"]


def record_links(world: WorldModel, anchor: SourceRow, links: list[IdentityLink],
                 candidates: dict[str, SourceRow], *, run_id: str, query_id: str | None) -> dict[str, Any]:
    """Write the anchor, every candidate record and every auto-merge link. Returns a summary."""
    source = {"kind": "zetaris", "url": "medtrace.all_sources", "at": _now(), "by": "executor", "runId": run_id,
              "checksum": query_id}
    first_seq = len(world.audit()) + 1
    anchor_id = _upsert(world, anchor, source)
    already = {e["id"] for e in world.view("graph").neighbors_of(anchor_id, via=SAME)}
    edges = 0
    for link in links:
        row = candidates.get(link.candidate_id)
        if row is None:
            continue
        cid = _upsert(world, row, source)
        if link.band == "auto-merge" and cid not in already:  # an open edge needs no second copy
            world.relate(from_=anchor_id, type=SAME, to=cid, context=f"source:{row.source}", source=source,
                         attrs={"probability": link.probability, "tier": link.tier, "decided_by": "identity score"})
            edges += 1
    return {"anchor": anchor_id, "records": 1 + sum(1 for l in links if l.candidate_id in candidates),
            "edges": edges, "audit": (first_seq, len(world.audit()))}


def remembered(world: WorldModel, anchor: SourceRow, links: list[IdentityLink]) -> tuple[list[IdentityLink], list[str]]:
    """Resolve review-band links from decisions already in the World Model. Returns (links, explanations)."""
    graph = world.view("graph")
    anchor_id = entity_id(anchor.record_key)
    same = {e["id"] for e in graph.neighbors_of(anchor_id, via=SAME)}
    distinct = {e["id"] for e in graph.neighbors_of(anchor_id, via=DISTINCT)}
    out, notes = [], []
    for link in links:
        cid = entity_id(link.candidate_id)
        if link.band == "review" and cid in same:
            out.append(link.model_copy(update={"band": "auto-merge"}))
            notes.append(f"{link.candidate_id}: a pharmacist already confirmed this is the same person")
        elif link.band == "review" and cid in distinct:
            out.append(link.model_copy(update={"band": "new"}))
            notes.append(f"{link.candidate_id}: a pharmacist already decided this is a different person")
        else:
            out.append(link)
    return out, notes


def record_decision(world: WorldModel, anchor: SourceRow, candidate_id: str, same_person: bool, *,
                    run_id: str, source_name: str) -> int:
    """The pharmacist's decision, as an edge with provenance. Returns its audit seq."""
    source = {"kind": "pharmacist", "at": _now(), "by": "pharmacist", "runId": run_id}
    world.relate(from_=entity_id(anchor.record_key), type=SAME if same_person else DISTINCT,
                 to=entity_id(candidate_id), context=f"source:{source_name}", source=source,
                 attrs={"decided_by": "pharmacist"})
    return world.audit()[-1]["seq"]


def linked_record_keys(world: WorldModel, anchor: SourceRow) -> set[str]:
    """The anchor plus every record the World Model says is the same person, now."""
    graph = world.view("graph")
    keys = {anchor.record_key}
    for entity in graph.neighbors_of(entity_id(anchor.record_key), via=SAME):
        keys.add(entity["id"].removeprefix("patient:"))
    return keys
