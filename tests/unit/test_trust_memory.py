"""H-MEM in a user-facing feature: the trust the pharmacist teaches, durable and recalled."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.engines.hmem import HMEM
from app.feedback import apply_feedback
from app.orchestrator import Orchestrator
from app.schemas import FeedbackRequest, RunRequest

def _teach_request(run_id: str) -> FeedbackRequest:
    return FeedbackRequest(run_id=run_id, target_id="grid:candesartan:daily_dose", verdict="reject",
                           reason="source_outdated", source="gp", attribute="daily_dose")


def _orch(make_settings: Callable[..., Any], tmp_path, hmem: HMEM | None = None) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(lambda _r: (_ for _ in ()).throw(AssertionError("network")))
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path, hmem=hmem)


def _teach(o: Orchestrator) -> None:
    run = o.start(RunRequest(patient_id="MRN0000003"))
    apply_feedback(o, _teach_request(run.run_id))


def test_trust_is_seeded_from_the_priors_as_hmem_records(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    assert o.trust == {k: round(v, 4) for k, v in SOURCE_TRUST_PRIORS.items()}
    rec = o.memory.hmem.store.get(o.memory.record_id("gp", "daily_dose"))
    assert rec.source == "trust.SOURCE_TRUST_PRIORS" and rec.layer == "long_term" and "trust:gp:daily_dose" in rec.tags


def test_a_verdict_is_hmem_feedback_with_a_ledger_entry(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    _teach(o)
    mid = o.memory.record_id("gp", "daily_dose")
    rec = o.memory.hmem.store.get(mid)
    assert round(rec.confidence, 4) == 0.5 and "review" in rec.tags  # wrong: -0.20 and the review tag
    fb = o.memory.hmem.ledger.history(mid)[-1]
    assert fb["action"] == "feedback" and fb["details"]["kind"] == "wrong"
    assert round(fb["previousState"]["confidence"], 4) == 0.7 and round(fb["newState"]["confidence"], 4) == 0.5


def test_the_learning_demo_survives_a_restart(make_settings, tmp_path) -> None:
    """Reject P0003's GP dose in one process; P0007 resolves differently in the next."""
    state = tmp_path / "hmem"
    o1 = _orch(make_settings, tmp_path, HMEM(persist_dir=state))
    before = o1.start(RunRequest(patient_id="MRN0000007"))
    assert not any(f.generic == "rosuvastatin" for f in before.findings)
    _teach(o1)
    count = len(o1.memory.hmem.store.all())

    o2 = _orch(make_settings, tmp_path, HMEM(persist_dir=state))  # a fresh process
    assert o2.trust[("gp", "daily_dose")] == 0.5
    assert len(o2.memory.hmem.store.all()) == count  # priors are not seeded twice
    after = o2.start(RunRequest(patient_id="MRN0000007"))
    assert any(f.type.value == "dose" and f.generic == "rosuvastatin" for f in after.findings)


def test_the_next_run_recalls_the_verdict_for_the_planner(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    first = o.start(RunRequest(patient_id="MRN0000007"))
    assert first.memory_used == []  # nothing taught yet: generic trust records do not surface
    _teach(o)
    second = o.start(RunRequest(patient_id="MRN0000007"))
    assert second.memory_used and "Pharmacist rejected (source_outdated)" in second.memory_used[0].content
    recall = next(e for e in second.trace if e.engine == "hmem")
    assert recall.step == "PLAN" and second.memory_used[0].memory_id in recall.memory_ids
    assert "threshold" in second.memory_used[0].retrieval_reason


def test_findings_cite_real_hmem_trust_records(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    r = o.start(RunRequest(patient_id="MRN0000089"))
    ids = {i for f in r.findings for i in f.hmem_record_ids}
    assert ids and all(o.memory.hmem.store.get(i) for i in ids)
    assert all(t.hmem_record_id and o.memory.hmem.store.get(t.hmem_record_id) for t in r.trust)


def test_sample_mode_default_hmem_writes_no_state(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    assert o.memory.hmem.store._file is None  # noqa: SLF001
