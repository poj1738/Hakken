"""The API wire contract (PLAN 2.8): additive, round-trippable, strict where it matters."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.packs.medtrace.types import (
    Coverage,
    DiscrepancyType,
    EvidenceState,
    FusedMed,
    FusedValue,
    IdentityLink,
    Notice,
    NoticeType,
    SourceRow,
)
from app.schemas import (
    Evidence,
    FeedbackRequest,
    FeedbackResponse,
    Finding,
    HealthResponse,
    IdentityDecisionRequest,
    IdentityReview,
    ModelCall,
    RunOutput,
    RunRequest,
    RunResponse,
    TraceEvent,
    TrustEntry,
    TrustUpdate,
)

OFFICIAL = {
    "run_id": "r1",
    "status": "success",
    "output": {"summary": "done"},
    "trace_id": "t1",
    "log_file": "logs/trace-r1.jsonl",
    "execution_time_seconds": 1.5,
}


def test_official_shape_alone_still_validates() -> None:
    """A response with only the official fields is still valid: MedTrace is additive."""
    r = RunResponse(**OFFICIAL)
    assert r.findings == [] and r.grid == [] and r.coverage == {}
    assert r.identity_review is None and r.query_count == 0
    assert r.bpmh_confirmable is False


@pytest.mark.parametrize("status", ["success", "partial", "error", "running", "needs_review"])
def test_run_status_values(status: str) -> None:
    assert RunResponse(**{**OFFICIAL, "status": status}).status == status


def test_unknown_status_rejected() -> None:
    with pytest.raises(ValidationError):
        RunResponse(**{**OFFICIAL, "status": "done"})


def _anchor() -> SourceRow:
    return SourceRow(
        source="emr",
        row_id="EMR-000001",
        source_patient_id="MRN0000001",
        name_given="Margaret",
        name_family="Smyth",
        dob_raw="1951-02-24",
    )


def _full_response() -> RunResponse:
    ev = Evidence(
        source="gp",
        row_id="GP-002210",
        sql_template_id="Q2",
        query_id="q-2",
        fields={"med_text": "Warfarin 5mg", "note_text": None},
    )
    finding = Finding(
        id="F1",
        type=DiscrepancyType.DOSE_UNCONFIRMABLE,
        generic="warfarin",
        high_risk_class="H",
        severity="high",
        priority=0.97,
        explanation="GP lists 5 mg daily (GP-002210); pharmacy dispenses 1 mg and 5 mg tablets.",
        evidence=[ev],
        evidence_states={"gp": EvidenceState.PRESENT, "patient": EvidenceState.UNKNOWN},
        tasks=["Confirm current warfarin dose with patient or INR book"],
        needs_pharmacist=True,
        hmem_record_ids=["hm-1"],
    )
    link = IdentityLink(
        anchor_id="emr:MRN0000001",
        candidate_id="pharmacy:C77812",
        match_weight=7.2,
        probability=0.83,
        band="review",
        tier="probabilistic",
        field_evidence={"given": "nickname Peggy~Margaret"},
    )
    return RunResponse(
        **OFFICIAL,
        patient_id="MRN0000001",
        coverage={"gp": Coverage(source="gp", state="not_found")},
        banner="Fewer than 2 sources found: BPMH cannot be confirmed.",
        grid=[
            FusedMed(
                generic="warfarin",
                per_source={"gp": EvidenceState.PRESENT},
                attributes={"daily_dose": FusedValue(attribute="daily_dose", value=5.0)},
            )
        ],
        findings=[finding],
        notices=[Notice(type=NoticeType.COVERAGE_GAP, detail="GP: no record found", source="gp")],
        tasks=["Call GP practice"],
        identity_review=IdentityReview(anchor=_anchor(), candidates=[link]),
        evidence_index={ev.row_id: ev},
        trust=[TrustEntry(source="gp", attribute="intended_dose", value=0.75)],
        trace=[TraceEvent(run_id="r1", agent_name="Executor", action="link", step="FIND_IDENTITY")],
        query_count=3,
        zetaris_ms=4200,
        model_calls=[
            ModelCall(
                role="Writer",
                requested_route="meterless/deep",
                routed_model="nvidia/nemotron-3.5-super-vl-120b-a12b",
                tokens={"prompt_tokens": 900, "completion_tokens": 300},
            )
        ],
    )


def test_full_response_round_trips_through_json() -> None:
    """What the API serialises is exactly what the UI fixtures will parse back."""
    r = _full_response()
    back = RunResponse.model_validate_json(r.model_dump_json())
    assert back == r
    assert back.findings[0].evidence_states["patient"] is EvidenceState.UNKNOWN


def test_evidence_keeps_null_as_none() -> None:
    """A SQL NULL must not become the string "None" on the wire."""
    dumped = _full_response().model_dump(mode="json")
    assert dumped["findings"][0]["evidence"][0]["fields"]["note_text"] is None


def test_finding_rejects_unknown_type_and_fields() -> None:
    with pytest.raises(ValidationError):
        Finding(id="F1", type="brand_only", generic="x")
    with pytest.raises(ValidationError):
        Finding(id="F1", type="dose", generic="x", made_up=True)


def test_model_call_defaults_to_not_truncated() -> None:
    c = ModelCall(role="Planner", requested_route="meterless/fast")
    assert c.truncated is False and c.routed_model is None


@pytest.mark.parametrize(
    "reason",
    ["wrong_patient", "source_outdated", "intentional_change",
     "not_clinically_relevant", "already_known", "other"],
)
def test_reject_accepts_each_of_the_six_reasons(reason: str) -> None:
    named = {"source": "gp", "attribute": "daily_dose"} if reason == "source_outdated" else {}
    f = FeedbackRequest(run_id="r1", target_id="F1", verdict="reject", reason=reason, **named)
    assert f.reason == reason


def test_source_outdated_names_the_trust_record() -> None:
    """The learning demo's -0.20 must land on ("gp", "daily_dose"), so both are required."""
    f = FeedbackRequest(run_id="r1", target_id="F1", verdict="reject", reason="source_outdated",
                        source="gp", attribute="daily_dose")
    assert (f.source, f.attribute) == ("gp", "daily_dose")
    for missing in ({"source": "gp"}, {"attribute": "daily_dose"}, {}):
        with pytest.raises(ValidationError, match="source and attribute"):
            FeedbackRequest(run_id="r1", target_id="F1", verdict="reject",
                            reason="source_outdated", **missing)


def test_feedback_source_and_attribute_are_vocabulary_checked() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="reject", reason="source_outdated",
                        source="hospital", attribute="daily_dose")
    with pytest.raises(ValidationError):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="reject", reason="source_outdated",
                        source="gp", attribute="colour")


def test_finding_detail_passes_through_and_round_trips() -> None:
    detail = {"atc_class": "C09A", "conflict": "confirm", "bpmh_single_source": "gp",
              "subtype": "dose", "statement": "charted 150 mg/day against 75 mg/day", "daily_dose_ratio": 2.0}
    f = Finding(id="F1", type="dose", generic="irbesartan", detail=detail)
    assert Finding.model_validate_json(f.model_dump_json()).detail == detail
    assert Finding(id="F2", type="dose", generic="x").detail == {}


def test_reject_without_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="needs a reason"):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="reject")


def test_confirm_with_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="carries no reason"):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="confirm", reason="other")


def test_feedback_rejects_unknown_reason_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="reject", reason="because")
    with pytest.raises(ValidationError):
        FeedbackRequest(run_id="r1", target_id="F1", verdict="confirm", memory_id="m")


def test_feedback_response_carries_before_and_after() -> None:
    resp = FeedbackResponse(
        run_id="r1",
        target_id="F1",
        verdict="reject",
        reason="source_outdated",
        trust_updates=[
            TrustUpdate(source="gp", attribute="intended_dose", hmem_record_id="hm-1",
                        kind="wrong", before=0.75, after=0.55, delta=-0.20)
        ],
    )
    assert resp.trust_updates[0].after < resp.trust_updates[0].before


def test_run_request_takes_a_patient_and_defaults_the_question() -> None:
    r = RunRequest(patient_id="MRN0000001")
    assert r.question
    with pytest.raises(ValidationError):
        RunRequest(patient_id="MRN0000001", unexpected=1)


def test_identity_decision_and_status_shapes() -> None:
    assert IdentityDecisionRequest(candidate_id="pharmacy:C77812", same_person=True).same_person
    h = HealthResponse(status="ok", sample_mode=True, domain_pack="medtrace",
                       zetaris="connected", meterless="online")
    assert h.last_routed_model is None


def test_run_output_unchanged() -> None:
    """The official `output` block keeps its shape."""
    assert set(RunOutput.model_fields) == {"summary", "recommendations", "evidence", "caveats", "artifacts"}
