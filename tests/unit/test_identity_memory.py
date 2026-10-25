"""The World Model in a user-facing feature: identity state shared across runs, with provenance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.engines.world_model import WorldModel
from app.orchestrator import Orchestrator
from app.schemas import IdentityDecisionRequest, RunRequest


def _orch(make_settings: Callable[..., Any], tmp_path, world: WorldModel | None = None) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(lambda _r: (_ for _ in ()).throw(AssertionError("network")))
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path, world=world)


def _world_events(r) -> list[str]:
    return [e.message for e in r.trace if e.engine == "world_model"]


def test_linked_records_are_written_with_provenance(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    r = o.start(RunRequest(patient_id="MRN0000089"))
    graph = o.world.view("graph")
    anchor = graph.entity("patient:emr:MRN0000089")
    assert anchor is not None and anchor["source"]["kind"] == "zetaris" and anchor["source"]["runId"] == r.run_id
    linked = {e["id"] for e in graph.neighbors_of("patient:emr:MRN0000089", via="same-person-as")}
    assert linked == {"patient:gp:GPP000089", "patient:pharmacy:C000089", "patient:patient:INT00089"}
    assert any("recorded" in m and "provenance" in m for m in _world_events(r))
    seqs = [a["seq"] for a in o.world.audit()]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_medicines_are_read_for_the_linked_set_in_the_graph(make_settings, tmp_path) -> None:
    r = _orch(make_settings, tmp_path).start(RunRequest(patient_id="MRN0000089"))
    msg = next(m for m in _world_events(r) if m.startswith("Linked set read from the World Model graph"))
    for key in ("emr:MRN0000089", "gp:GPP000089", "pharmacy:C000089", "patient:INT00089"):
        assert key in msg


def test_a_confirmed_identity_is_not_asked_again(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    first = o.start(RunRequest(patient_id="MRN0000015"))
    assert first.status == "needs_review"
    done = o.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=True))
    assert any("decision recorded" in m for m in _world_events(done))
    second = o.start(RunRequest(patient_id="MRN0000015"))
    assert second.status == "success"  # no pause: the World Model remembered
    assert any("already confirmed" in m for m in _world_events(second))
    assert {(f.type, f.generic) for f in second.findings} == {(f.type, f.generic) for f in done.findings}


def test_a_rejected_identity_stays_rejected(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    first = o.start(RunRequest(patient_id="MRN0000015"))
    o.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=False))
    second = o.start(RunRequest(patient_id="MRN0000015"))
    assert second.status == "success"
    assert any("different person" in m for m in _world_events(second))
    assert not any(e.source == "patient" for f in second.findings for e in f.evidence)


def test_decisions_survive_a_restart_with_local_storage(make_settings, tmp_path) -> None:
    def world() -> WorldModel:
        return WorldModel(namespace="medtrace", storage="local", directory=tmp_path)

    o1 = _orch(make_settings, tmp_path, world())
    first = o1.start(RunRequest(patient_id="MRN0000015"))
    o1.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=True))
    assert (tmp_path / ".world" / "medtrace.json").exists()

    o2 = _orch(make_settings, tmp_path, world())  # a fresh process, same state file
    assert o2.start(RunRequest(patient_id="MRN0000015")).status == "success"


def test_sample_mode_default_world_is_in_memory(make_settings, tmp_path) -> None:
    o = _orch(make_settings, tmp_path)
    o.start(RunRequest(patient_id="MRN0000089"))
    assert o.world._store._file is None  # noqa: SLF001 -- SAMPLE_MODE writes no state
