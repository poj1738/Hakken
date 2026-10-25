# Ported from Meterless World Model, conformance/runner.ts
# (github.com/Meterless/Meterless, engines/world-model, commit 1742dec), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25. The 8 inline cases are translated one for
# one: same ids, same inputs, same assertions and messages. None is weakened.
"""World Model conformance: the engine is done when all 8 pass (conformance/README.md).

Boundary rulings the runner asserts: similarity 0.85 EXACTLY auto-merges; 0.82
EXACTLY queues for review -- against the 0.92 band in docs/ingest-pipeline.md
(docs/DECISIONS.md, 23 Oct: the runner wins).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.engines.world_model import WorldModel, decide, entityIdFromName, normalizeName

OBSERVATIONS = [
    {"externalId": "a1", "title": "Fed holds rates", "at": "2026-05-17T14:00:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T14:00:00.000Z"},
     "entities": [{"type": "person", "name": "Jerome Powell"}]},
    {"externalId": "a2", "title": "Powell signals patience", "at": "2026-05-17T16:30:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T16:30:00.000Z"},
     "entities": [{"type": "person", "name": "Jerome Powell"}]},
]


def clock() -> datetime:
    return datetime(2026, 5, 18, tzinfo=timezone.utc)


def test_sid_001_diacritics_and_nbsp_normalize_identically() -> None:
    """stable ids: diacritics and NBSP normalize identically (NFKD + strip marks)"""
    assert normalizeName("José  García") == normalizeName("Jose Garcia"), \
        "accented + NBSP name must normalize to the plain form"
    assert entityIdFromName("person", "José García") == entityIdFromName("person", "jose garcia"), \
        "same normalized name must produce the same id"


def test_sid_002_distinct_names_stay_distinct() -> None:
    """stable ids: distinct names stay distinct (no over-normalization)"""
    assert entityIdFromName("org", "Acme Corp") != entityIdFromName("org", "Acme Corporation"), \
        "different names must produce different ids"
    assert entityIdFromName("person", "x") != entityIdFromName("org", "x"), "type participates in the key"


def test_band_001_merge_bands_at_the_boundaries() -> None:
    """merge bands at the boundaries: 0.85 auto, 0.84 review, 0.82 review, 0.81 new"""
    assert decide(0.85) == "auto-merge", "0.85 exactly is auto-merge (>= reading)"
    assert decide(0.84) == "review", "0.84 queues for review"
    assert decide(0.82) == "review", "0.82 exactly queues"
    assert decide(0.81) == "new", "0.81 is a new entity"


def test_prov_001_writes_without_provenance_are_rejected() -> None:
    """writes without provenance are rejected"""
    world = WorldModel(storage="memory", namespace="conf")
    with pytest.raises(Exception):
        world.upsert_entity(type="person", name="No Provenance", source=None)
    assert world.audit() == [], "no provenance, no write"


def test_idem_001_same_batch_twice_produces_an_empty_diff() -> None:
    """ingest idempotency: same batch twice produces an empty diff"""
    world = WorldModel(storage="memory", namespace="conf", clock=clock)
    world.ingest(OBSERVATIONS)
    shape1 = world.state_shape_canonical()
    second = world.ingest(OBSERVATIONS)
    assert second["changed"] is False, "second run must report changed=false"
    assert world.state_shape_canonical() == shape1, "canonical state must be identical after re-ingest"


def test_idem_002_a_mutated_batch_changes_the_shape() -> None:
    """the idempotency check can fail: a mutated batch changes the shape"""
    world = WorldModel(storage="memory", namespace="conf", clock=clock)
    world.ingest(OBSERVATIONS)
    shape1 = world.state_shape_canonical()
    mutated = [{**OBSERVATIONS[0], "title": OBSERVATIONS[0]["title"] + " (edited)"}, OBSERVATIONS[1]]
    run = world.ingest(mutated)
    assert run["changed"] is True, "an edited observation must report changed=true"
    assert world.state_shape_canonical() != shape1, "canonical state must differ after a real edit"


def test_bitemp_001_superseding_edge_closes_the_old_one() -> None:
    """bitemporal edges: a superseding edge closes the old one; point-in-time queries respect validity"""
    world = WorldModel(storage="memory", namespace="conf")

    def at(s: str) -> dict:
        return {"kind": "manual", "at": s}

    world.upsert_entity(type="player", external_key={"system": "g", "id": "p1"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
    world.upsert_entity(type="team", external_key={"system": "g", "id": "a"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
    world.upsert_entity(type="team", external_key={"system": "g", "id": "b"}, attrs={}, source=at("2088-03-01T00:00:00.000Z"))
    world.relate(from_="player:g:p1", type="plays-for", to="team:g:a", valid_from="2087-01-01T00:00:00.000Z",
                 source=at("2087-01-01T00:00:00.000Z"))
    world.relate(from_="player:g:p1", type="plays-for", to="team:g:b", valid_from="2088-03-01T00:00:00.000Z",
                 source=at("2088-03-01T00:00:00.000Z"))
    now = world.view("graph").neighbors_of("player:g:p1", via="plays-for")
    assert len(now) == 1 and now[0]["id"] == "team:g:b", \
        f"open edge should point at team b; got {[e['id'] for e in now]}"
    then = world.view("graph").neighbors_of("player:g:p1", via="plays-for", at="2087-06-01T00:00:00.000Z")
    assert len(then) == 1 and then[0]["id"] == "team:g:a", \
        f"2087 query should return team a; got {[e['id'] for e in then]}"


def test_audit_001_every_mutation_writes_an_audit_entry_in_order() -> None:
    """every mutation writes an audit entry in order"""
    world = WorldModel(storage="memory", namespace="conf")
    world.upsert_entity(type="x", name="Audit One", source={"kind": "manual", "at": "2026-01-01T00:00:00.000Z"})
    world.upsert_entity(type="x", name="Audit Two", source={"kind": "manual", "at": "2026-01-02T00:00:00.000Z"})
    audit = world.audit()
    assert len(audit) >= 2, f"expected >= 2 audit entries, got {len(audit)}"
    for i in range(1, len(audit)):
        assert audit[i]["seq"] > audit[i - 1]["seq"], "audit seq must be strictly increasing"
