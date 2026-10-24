"""The UI's example API responses (PLAN 5.8) must always match app/schemas.py.

Anshu builds against these files in mock mode, so a schema change that breaks
them breaks the UI silently. This test makes it break CI instead: any schema
change must update `tests/fixtures/api/` in the same PR.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.packs.medtrace.types import DiscrepancyType, EvidenceState, NoticeType
from app.schemas import FeedbackResponse, HealthResponse, PatientsResponse, RunResponse

API = Path(__file__).resolve().parents[1] / "fixtures" / "api"

FILES = {
    "patients.json": PatientsResponse,
    "run_P0001_done.json": RunResponse,
    "run_P0001_gp_not_found.json": RunResponse,
    "run_P0001_trace_partial.json": RunResponse,
    "run_P0002_needs_review.json": RunResponse,
    "feedback_response.json": FeedbackResponse,
    "status.json": HealthResponse,
}
RUNS = [name for name, model in FILES.items() if model is RunResponse]


def _load(name: str):
    return FILES[name].model_validate_json((API / name).read_text())


@pytest.mark.parametrize("name", FILES)
def test_fixture_matches_schema(name: str) -> None:
    _load(name)


def test_no_unlisted_fixture_files() -> None:
    """A new example file must be added here, so it is validated too."""
    assert {p.name for p in API.glob("*.json")} == set(FILES)


@pytest.mark.parametrize("name", RUNS)
def test_runs_are_labelled_as_hand_written(name: str) -> None:
    """These are illustrations, not outputs (CLAUDE.md rule 6) -- and they say so."""
    caveats = " ".join(_load(name).output.caveats)
    assert "Hand-written example" in caveats and "Not medical advice" in caveats


@pytest.mark.parametrize("name", RUNS)
def test_every_cited_row_is_in_the_evidence_index(name: str) -> None:
    """The grid hover and the flags look rows up by id; a dangling id is a broken UI."""
    run = _load(name)
    for f in run.findings:
        assert f.evidence, f"{f.id} has no evidence"
        for e in f.evidence:
            assert e.row_id in run.evidence_index, f"{f.id} cites {e.row_id}"
    for med in run.grid:
        for rid in med.row_ids:
            assert rid in run.evidence_index, f"grid {med.generic} cites {rid}"


def test_done_run_covers_every_finding_and_notice_type() -> None:
    run = _load("run_P0001_done.json")
    assert {f.type for f in run.findings} == set(DiscrepancyType)
    shown = {n.type for n in run.notices} | {
        n.type for n in _load("run_P0001_gp_not_found.json").notices
    }
    assert shown == set(NoticeType)
    assert any(m.abstained for m in run.grid), "needs an abstained 'ask patient' conflict"


def test_coverage_states_and_banner_are_all_exercised() -> None:
    states = {c.state for n in RUNS for c in _load(n).coverage.values()}
    assert states == {"found", "near_miss_pending", "not_found"}
    gaps = _load("run_P0001_gp_not_found.json")
    assert gaps.banner and not gaps.bpmh_confirmable
    assert all(f.evidence_states["gp"] is EvidenceState.UNKNOWN for f in gaps.findings)


def test_statuses_cover_the_ui_states() -> None:
    assert {_load(n).status for n in RUNS} == {"success", "partial", "running", "needs_review"}
    review = _load("run_P0002_needs_review.json").identity_review
    assert review is not None and review.candidates
    assert all(c.band == "review" for c in review.candidates)
    assert all(c.candidate_id in review.records for c in review.candidates)


def test_patients_are_identified_by_mrn_not_ground_truth_keys() -> None:
    ids = [p.patient_id for p in _load("patients.json").patients]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("MRN") for i in ids)
    assert "P0001" not in json.dumps([json.loads((API / n).read_text()) for n in FILES])
