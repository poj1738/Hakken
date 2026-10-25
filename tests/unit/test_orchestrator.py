"""The whole run, end to end, on the committed replay set (SAMPLE_MODE). No network.

What a correct run shows for each patient is written down in
`input_examples/README.md`; these tests hold the orchestrator to it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import app.orchestrator as orch_mod
from app.adapters.meterless import OFFLINE_MODEL, MeterlessClient
from app.adapters.zetaris import RunQueries, ZetarisClient
from app.agents.evaluator import claim_problems
from app.domain.packs.medtrace.types import DiscrepancyType as DT
from app.orchestrator import Orchestrator, UnknownPatient
from app.schemas import Evidence, Finding, IdentityDecisionRequest, RunRequest, RunResponse
from app.tracing import Tracer, read_trace


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


@pytest.fixture
def orch(make_settings: Callable[..., Any], tmp_path) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)


def run(orch: Orchestrator, mrn: str) -> RunResponse:
    return orch.start(RunRequest(patient_id=mrn))


# -- straight through ----------------------------------------------------------------


def test_p0089_straight_through_matches_input_examples(orch) -> None:
    """example_2: oxycodone/naloxone duplication and frequency error (APINCHS), gliclazide omission,
    esomeprazole frequency, a stale dapagliflozin listing."""
    r = run(orch, "MRN0000089")
    assert r.status == "success" and r.error is None
    got = {(f.type, f.generic) for f in r.findings}
    assert got == {(DT.DUPLICATION, "oxycodone/naloxone"), (DT.OMISSION, "gliclazide"),
                   (DT.FREQUENCY, "oxycodone/naloxone"), (DT.FREQUENCY, "esomeprazole"),
                   (DT.STALE_LISTING, "dapagliflozin")}
    assert all(f.needs_pharmacist for f in r.findings if f.generic == "oxycodone/naloxone")


def test_every_finding_is_cited_explained_and_verified(orch) -> None:
    r = run(orch, "MRN0000089")
    for f in r.findings:
        assert f.evidence and f.explanation
        assert claim_problems(f) == []
        assert all(e.row_id in r.evidence_index for e in f.evidence)
    assert r.output.evidence and all(item.verified and item.sql for item in r.output.evidence)


def test_sample_mode_never_calls_a_model_and_says_so(orch) -> None:
    r = run(orch, "MRN0000089")
    assert r.model_calls and {c.routed_model for c in r.model_calls} == {OFFLINE_MODEL}
    assert r.sample_mode and any("SAMPLE_MODE" in c for c in r.output.caveats)
    assert any("Not medical advice" in c for c in r.output.caveats)


def test_budget_and_query_records(orch) -> None:
    r = run(orch, "MRN0000089")
    assert r.query_count == 3  # Q1, Q2, Q3 -- Q0 and Q_REF are per process, not per run
    sqls = [e.sql for e in r.trace if e.sql]
    assert len(sqls) == 3 and all("medtrace." in s for s in sqls)


def test_trace_is_written_and_matches_the_response(orch, tmp_path) -> None:
    r = run(orch, "MRN0000089")
    steps = [e.step for e in r.trace]
    for a, b in [("PLAN", "FIND_IDENTITY"), ("FIND_IDENTITY", "FETCH_MEDS"), ("FETCH_MEDS", "FUSE"),
                 ("DRAFT", "VERIFY"), ("VERIFY", "DONE")]:
        assert steps.index(a) < steps.index(b)
    on_disk = read_trace(tmp_path / f"trace-{r.run_id}.jsonl")
    assert [e["step"] for e in on_disk] == steps
    assert all(e.message for e in r.trace)


def test_response_round_trips_through_json(orch) -> None:
    r = run(orch, "MRN0000089")
    assert RunResponse.model_validate_json(r.model_dump_json()) == r


def test_outputs_change_with_inputs(orch) -> None:
    a, b = run(orch, "MRN0000089"), run(orch, "MRN0000001")
    assert {(f.type, f.generic) for f in a.findings} != {(f.type, f.generic) for f in b.findings}
    assert {(f.type, f.generic) for f in b.findings} == {(DT.OMISSION, "famotidine"),
                                                         (DT.OMISSION, "empagliflozin/metformin")}


def test_grid_risk_class_is_filled_and_dose_lane_tasks_exist(orch) -> None:
    r = orch.resume(run(orch, "MRN0000015").run_id,
                    IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=True))
    warfarin = next(m for m in r.grid if m.generic == "warfarin")
    assert warfarin.high_risk_class == "H"
    assert any("warfarin" in t.lower() and "dose" in t.lower() for t in r.tasks)


# -- identity review -----------------------------------------------------------------


def test_p0015_pauses_for_review_with_honest_coverage(orch) -> None:
    r = run(orch, "MRN0000015")
    assert r.status == "needs_review" and r.findings == [] and r.grid == []
    assert {k: v.state for k, v in r.coverage.items()} == {
        "emr": "found", "gp": "found", "pharmacy": "found", "patient": "near_miss_pending"}
    review = r.identity_review
    assert review is not None and [c.candidate_id for c in review.candidates] == ["patient:INT00015"]
    assert all(c.candidate_id in review.records for c in review.candidates)
    assert r.query_count == 1  # paused before any medicine was read


def test_p0015_confirmed_shows_example_1(orch) -> None:
    """example_1, once confirmed: warfarin and insulin aspart dose conflicts (APINCHS), an insulin
    omission, an empagliflozin omission, an aspirin/clopidogrel duplication."""
    first = run(orch, "MRN0000015")
    r = orch.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=True))
    got = {(f.type, f.generic) for f in r.findings}
    assert got == {(DT.DOSE_UNCONFIRMABLE, "warfarin"), (DT.DOSE_UNCONFIRMABLE, "insulin aspart"),
                   (DT.OMISSION, "insulin aspart"), (DT.OMISSION, "empagliflozin"),
                   (DT.DUPLICATION, "aspirin/clopidogrel")}
    assert r.status == "success" and orch.get(first.run_id) is r
    assert any(e.message and "same person" in e.message for e in r.trace)


def test_p0015_rejected_reads_no_interview_rows(orch) -> None:
    first = run(orch, "MRN0000015")
    r = orch.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=False))
    assert r.status == "success"
    assert not any(e.source == "patient" for f in r.findings for e in f.evidence)
    assert r.coverage["patient"].state != "found"


def test_resume_rejects_an_unknown_candidate(orch) -> None:
    first = run(orch, "MRN0000015")
    with pytest.raises(ValueError):
        orch.resume(first.run_id, IdentityDecisionRequest(candidate_id="gp:NOPE", same_person=True))


def test_unknown_patient(orch) -> None:
    with pytest.raises(UnknownPatient):
        run(orch, "MRN9999999")


def test_patients_list_comes_from_q0(orch) -> None:
    pts = orch.patients()
    assert len(pts) == 200 and len({p.patient_id for p in pts}) == 200
    assert pts[0].patient_id.startswith("MRN")


# -- bounded and honest under failure ------------------------------------------------


def test_budget_exhaustion_returns_partial(orch, monkeypatch) -> None:
    monkeypatch.setattr(orch_mod, "RunQueries", lambda client: RunQueries(client, budget=2))
    r = run(orch, "MRN0000089")
    assert r.status == "partial" and r.error and r.error.type == "QueryBudgetExceeded"
    assert r.query_count == 2


def test_timeout_returns_partial(make_settings, tmp_path) -> None:
    s = make_settings(sample_mode=True, run_timeout_s=0.000001)
    r = Orchestrator(s, log_dir=tmp_path).start(RunRequest(patient_id="MRN0000089"))
    assert r.status == "partial" and r.error and r.error.type == "RunTimeout"


def test_live_nightshift_failure_degrades_visibly(make_settings, tmp_path) -> None:
    """Zetaris replayed, Nightshift returning 502 every time: the run still finishes, labelled."""
    zs = make_settings(sample_mode=True)
    ls = make_settings(meterless_runtime_token="example-runtime-token", max_retries=0)
    down = httpx.MockTransport(lambda _r: httpx.Response(502, json={"error": {"meterless_detail": "x_empty_response"}}))
    o = Orchestrator(ls, llm=MeterlessClient(ls, transport=down, sleep=lambda _s: None),
                     zetaris=ZetarisClient(zs), log_dir=tmp_path)
    o.settings = ls  # live LLM settings; Zetaris stays on the replay set
    r = o.start(RunRequest(patient_id="MRN0000089"))
    assert r.status == "partial" and r.findings
    assert any("Nightshift unavailable" in c for c in r.output.caveats)
    assert any(e.status == "degraded" for e in r.trace) and r.model_calls == []
    assert all(claim_problems(f) == [] for f in r.findings)


# -- Option A: the Planner's needs drive the templates -------------------------------


def test_each_planned_need_is_traced_to_its_template(orch) -> None:
    r = run(orch, "MRN0000089")
    routes = [e for e in r.trace if e.action == "route"]
    assert [e.step for e in routes] == ["FIND_IDENTITY", "FETCH_MEDS", "RESOLVE_FREE_TEXT", "VERIFY"]
    assert all('Planner need "' in e.message for e in routes)
    assert "template Q1" in routes[0].message and "template Q3" in routes[-1].message
    assert "no SQL" in routes[2].message
    sent = [e for e in r.trace if e.sql]
    assert [e.sql_template_id for e in sent] == ["Q1", "Q2", "Q3"] and all(e.query_id for e in sent)


def test_an_optional_step_runs_only_when_planned(orch, monkeypatch) -> None:
    from app.agents import planner

    no_shortage = run(orch, "MRN0000089")
    assert not any(e.step == "CHECK_SHORTAGES" for e in no_shortage.trace)

    original = planner._offline_plan

    def with_shortages(anchor, budget_left):
        p = original(anchor, budget_left)
        return p.model_copy(update={"steps": [*p.steps, planner.PlanStep(tool="check_shortages", need="any shortages?")]})

    monkeypatch.setattr(planner, "_offline_plan", with_shortages)
    r = run(orch, "MRN0000089")
    checks = [e for e in r.trace if e.step == "CHECK_SHORTAGES"]
    assert any('"any shortages?"' in (e.message or "") for e in checks)
    # SAMPLE_MODE has no recorded Q4: the step says so and the run still succeeds.
    assert any(e.status == "skipped" for e in checks) and r.status == "success"


def test_core_steps_are_added_when_the_model_leaves_them_out(orch, monkeypatch) -> None:
    from app.agents import planner

    def thin(anchor, budget_left):
        return planner.Plan(steps=[planner.PlanStep(tool="fetch_meds", need="just the meds")], rationale="thin")

    monkeypatch.setattr(planner, "_offline_plan", thin)
    r = run(orch, "MRN0000089")
    plan_msg = next(e.message for e in r.trace if e.step == "PLAN")
    assert "Core steps added by code: find_identities, verify" in plan_msg
    assert '"just the meds"' in plan_msg and r.status == "success"


# -- the verifier and the trace ------------------------------------------------------


def _finding(text: str) -> Finding:
    return Finding(id="F1", type=DT.DOSE, generic="bisoprolol", explanation=text,
                   evidence=[Evidence(source="gp", row_id="GP-000001", sql_template_id="Q2",
                                      fields={"med_text": "bisoprolol 5 mg", "freq_text": "one a day"})],
                   evidence_states={"patient": "unknown"})


def test_verifier_blocks_an_invented_number_a_foreign_row_and_not_taking() -> None:
    assert claim_problems(_finding("GP lists bisoprolol 5 mg daily (GP-000001).")) == []
    assert any("numbers" in p for p in claim_problems(_finding("GP lists 10 mg daily (GP-000001).")))
    assert any("not its evidence" in p for p in claim_problems(_finding("See GP-000001 and PHM-000009.")))
    assert any("cites none" in p for p in claim_problems(_finding("GP lists bisoprolol 5 mg.")))
    assert any("not taking" in p for p in claim_problems(_finding("Patient is not taking it (GP-000001).")))


def _critique_with(make_settings, verdicts: list[dict]) -> dict[str, list[str]]:
    import time
    from datetime import date

    from app.agents.base import AgentContext
    from app.agents.evaluator import critique
    from app.domain.packs.medtrace.types import Lexicon

    body = {"model": "nvidia/x", "usage": {"completion_tokens": 100},
            "choices": [{"message": {"content": json.dumps({"verdicts": verdicts})}}]}
    s = make_settings(meterless_runtime_token="example-runtime-token")
    llm = MeterlessClient(s, transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=body)))
    ctx = AgentContext(llm=llm, zetaris=RunQueries(ZetarisClient(make_settings(sample_mode=True))), lex=Lexicon(),
                       tracer=Tracer("r1", settings=s, log_dir=None), as_of=date(2026, 10, 24),
                       deadline=time.monotonic() + 60)
    return critique(ctx, [_finding("GP lists bisoprolol 5 mg daily (GP-000001).")])


def test_a_faithful_verdict_with_commentary_is_not_a_problem(make_settings) -> None:
    """Live, 25 Oct: asked for 'problems', the model listed the clinical findings themselves."""
    assert _critique_with(make_settings, [{"id": "F1", "faithful": True,
                                           "issue": "Potential dose discrepancy; prescriber should confirm."}]) == {}


def test_an_unfaithful_verdict_is_a_problem(make_settings) -> None:
    got = _critique_with(make_settings, [{"id": "F1", "faithful": False, "issue": "'daily' is not in the rows"}])
    assert got == {"F1": ["'daily' is not in the rows"]}


def test_tracer_masks_secrets(make_settings, tmp_path) -> None:
    s = make_settings(meterless_runtime_token="example-secret-value-123")
    t = Tracer("r1", settings=s, log_dir=tmp_path)
    t.emit("Writer", "x", message="token example-secret-value-123 and Bearer abcdefghijkl")
    line = (tmp_path / "trace-r1.jsonl").read_text()
    assert "example-secret-value-123" not in line and "abcdefghijkl" not in line
    assert json.loads(line)["message"].count("***") == 2
