# Ported from Meterless H-MEM, conformance/runner.ts
# (github.com/Meterless/Meterless, engines/hmem, commit 1742dec), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25. Consumes the official vectors verbatim
# (tests/engines/vectors/hmem_vectors.json). Each runner section is one parametrised
# test; every assertion and message is the runner's. None is weakened.
"""H-MEM conformance: the engine is done when all 13 vectors pass (conformance/README.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engines.hmem import HMEM

VECTORS = json.loads((Path(__file__).parent / "vectors" / "hmem_vectors.json").read_text())
T0: int = VECTORS["clock"]
DAY = 24 * 60 * 60 * 1000
S = VECTORS["sections"]


def approx(a: float | None, b: float, eps: float = 1e-9) -> bool:
    return a is not None and abs(a - b) < eps


def _ids(section: str) -> list[str]:
    return [c["id"] for c in S[section]]


@pytest.mark.parametrize("c", S["record-validation"], ids=_ids("record-validation"))
def test_record_validation(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    rejected = False
    try:
        hmem.add(content=c["input"]["content"], source=c["input"]["source"])
    except Exception:
        rejected = True
    assert rejected == (c["expect"] == "reject"), f"expected {c['expect']}, got {'reject' if rejected else 'accept'}"


@pytest.mark.parametrize("c", S["feedback-deltas"], ids=_ids("feedback-deltas"))
def test_feedback_deltas(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    m = hmem.add(content="feedback target record", confidence=c["start"], source="conformance")
    access_before = m.access_count
    hmem.feedback(m.id, c["kind"])
    after = hmem.store.get(m.id)
    assert approx(after.confidence, c["expectConfidence"]), f"confidence {after.confidence}, expected {c['expectConfidence']}"
    if "expectAccessDelta" in c:
        delta = after.access_count - access_before
        assert delta == c["expectAccessDelta"], f"accessCount delta {delta}, expected {c['expectAccessDelta']}"
    if c.get("expectTag"):
        assert c["expectTag"] in after.tags, f"missing tag {c['expectTag']}"


@pytest.mark.parametrize("c", S["ranking-order"], ids=_ids("ranking-order"))
def test_ranking_order(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    by_key = {r["key"]: hmem.add(content=r["content"], confidence=r["confidence"], layer=r["layer"],
                                 source="conformance") for r in c["records"]}
    for r in c["records"]:
        if r.get("supersededByKey"):
            by_key[r["key"]].superseded_by = by_key[r["supersededByKey"]].id
    result = hmem.query(c["query"], threshold=0, top_n=10)
    order = [rm.memory.id for rm in result.memories]
    expected = [by_key[k].id for k in c["expectOrder"]]
    for i in range(len(expected) - 1):
        assert order.index(expected[i]) < order.index(expected[i + 1]), \
            f"expected {c['expectOrder'][i]} before {c['expectOrder'][i + 1]}, got {order}"


@pytest.mark.parametrize("c", S["sleep-guardrails"], ids=_ids("sleep-guardrails"))
def test_sleep_guardrails(c: dict) -> None:
    now = {"t": T0}
    hmem = HMEM(clock=lambda: now["t"])
    by_key = {r["key"]: hmem.add(content=r["content"], source=r["source"], derived_from=r.get("derivedFrom"))
              for r in c["records"]}
    now["t"] = T0 + c["ageDays"] * DAY
    before = sorted(m.id for m in hmem.store.all())
    preview = hmem.sleep.preview()
    assert sorted(m.id for m in hmem.store.all()) == before, "preview mutated the store"
    for k in c["expectArchived"]:
        assert by_key[k].id in preview.to_archive, f"{k} should be archivable"
    for k in c["expectProtected"]:
        assert by_key[k].id not in preview.to_archive, f"{k} is guardrail-protected and must not archive"
    report = hmem.sleep.execute(preview)
    for k in c["expectProtected"]:
        assert hmem.store.get(by_key[k].id) is not None, f"{k} was deleted despite guardrails"
    assert isinstance(report.backup_id, str) and report.backup_id, "execute must return a backupId"


@pytest.mark.parametrize("c", S["conflict-gate"], ids=_ids("conflict-gate"))
def test_conflict_gate(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    a = hmem.add(content=c["a"]["content"], confidence=c["a"]["confidence"], source="conformance")
    b = hmem.add(content=c["b"]["content"], confidence=c["b"]["confidence"], source="conformance")
    found = hmem.conflicts.scan()
    assert found, "opposing always/never pair on similar content must be detected"
    outcome = hmem.conflicts.auto_resolve(found[0])
    assert outcome in ("resolved", "queued"), f"outcome must be resolved or queued, got {outcome}"
    if outcome == "resolved":
        loser = next((m for m in (hmem.store.get(a.id), hmem.store.get(b.id)) if m and m.superseded_by), None)
        assert loser is not None, "resolved conflicts must mark the loser supersededBy"
    assert hmem.store.get(a.id) and hmem.store.get(b.id), "conflict resolution must never delete records"


@pytest.mark.parametrize("c", S["ledger-audit"], ids=_ids("ledger-audit"))
def test_ledger_audit(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    m = hmem.add(content="audited record", confidence=c["start"], source="conformance")
    hmem.feedback(m.id, c["kind"])
    history = hmem.ledger.history(m.id)
    actions = [h["action"] for h in history]
    assert actions == c["expectActions"], f"actions {actions}, expected {c['expectActions']}"
    fb = history[-1]
    prev = (fb.get("previousState") or {}).get("confidence")
    new = (fb.get("newState") or {}).get("confidence")
    assert approx(prev, c["expectPrev"]), f"previousState.confidence {prev}, expected {c['expectPrev']}"
    assert approx(new, c["expectNew"]), f"newState.confidence {new}, expected {c['expectNew']}"


@pytest.mark.parametrize("c", S["dream-boundary"], ids=_ids("dream-boundary"))
def test_dream_boundary(c: dict) -> None:
    hmem = HMEM(clock=lambda: T0)
    for r in c["records"]:
        hmem.add(content=r["content"], type=r["type"], source="conformance")
    count_before = len(hmem.store.all())
    proposals = hmem.dreaming.dream()
    assert proposals, "two related preferences must produce at least one proposal"
    assert len(hmem.store.all()) == count_before, "dreaming must not materialize anything before approval"
    created = hmem.dreaming.approve(proposals[0].id)
    if created:
        assert created.layer == "long_term", "approved proposals materialize as long_term"
        assert created.derived_from, "approved proposals carry derivedFrom lineage"


def test_the_suite_has_all_13_vectors() -> None:
    """A dropped vector would pass silently; the count is the runner's scorecard denominator."""
    assert sum(len(v) for v in S.values()) == 13
