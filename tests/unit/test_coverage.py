"""`coverage.evidence_state` -- the three-valued core.

Until 25 Oct this module had no tests of its own, only the signature smoke test,
although `EvidenceState` is the one value that decides whether absence means
anything and Arnav's API shows it per finding.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.packs.medtrace.coverage import SCOPE_DISPENSING_INCOMPLETE, evidence_state
from app.domain.packs.medtrace.types import Coverage, EvidenceState, MedStatement

ADMITTED = date(2026, 10, 24)
FOUND = Coverage(source="gp", state="found")


def stmt(source="gp", generic="amlodipine", status="active", doc_date=ADMITTED,
         ingredients=None, row_id="R-1") -> MedStatement:
    return MedStatement(source=source, row_id=row_id, raw_text=generic or "",
                        generic=generic, status=status, doc_date=doc_date,
                        ingredients=ingredients if ingredients is not None
                        else [(generic, None)])


def test_a_source_asserting_the_medicine_is_present() -> None:
    assert evidence_state("amlodipine", "gp", FOUND, [stmt()]) is EvidenceState.PRESENT


@pytest.mark.parametrize("source", ["gp", "patient"])
def test_asserted_as_stopped_counts_against_the_medicine(source) -> None:
    """A GP line marked ceased, or a patient's "no", mentions the medicine -- and
    used to read as PRESENT because of it. It is evidence *against* current use,
    which is what ABSENT_IN_SCOPE means."""
    cov = Coverage(source=source, state="found")
    assert evidence_state("amlodipine", source, cov,
                          [stmt(source=source, status="ceased")]) is EvidenceState.ABSENT_IN_SCOPE


def test_one_current_line_outweighs_a_stopped_one() -> None:
    lines = [stmt(status="ceased", row_id="R-1"), stmt(status="active", row_id="R-2")]
    assert evidence_state("amlodipine", "gp", FOUND, lines) is EvidenceState.PRESENT


def test_a_source_never_found_is_unknown_not_absent() -> None:
    """The failure this whole type exists to prevent: rendering "never reached
    the GP" as "the GP says not taking"."""
    missing = Coverage(source="gp", state="not_found")
    assert evidence_state("amlodipine", "gp", missing, []) is EvidenceState.UNKNOWN


def test_a_near_miss_link_is_unknown() -> None:
    pending = Coverage(source="gp", state="near_miss_pending")
    assert evidence_state("amlodipine", "gp", pending, []) is EvidenceState.UNKNOWN


def test_found_and_not_listed_is_absent_in_scope() -> None:
    assert evidence_state("warfarin", "gp", FOUND, [stmt()]) is EvidenceState.ABSENT_IN_SCOPE


def test_incomplete_dispensing_makes_absence_unknown() -> None:
    """A second pharmacy or a private script would not appear in the slice we
    can see, so not finding a dispensing proves nothing."""
    cov = Coverage(source="pharmacy", state="found",
                   scope_notes=[f"{SCOPE_DISPENSING_INCOMPLETE} second pharmacy suspected"])
    assert evidence_state("warfarin", "pharmacy", cov, []) is EvidenceState.UNKNOWN


def test_another_sources_statement_never_counts() -> None:
    assert evidence_state("amlodipine", "gp", FOUND,
                          [stmt(source="pharmacy")]) is EvidenceState.ABSENT_IN_SCOPE


def test_the_emr_column_is_the_current_admission_chart() -> None:
    """EMR rows include older discharge summaries. A medicine started at a June
    discharge and missing from today's chart is absent *from the chart* -- that
    is precisely what an omission is."""
    cov = Coverage(source="emr", state="found")
    june = stmt(source="emr", generic="levothyroxine", doc_date=date(2026, 6, 12), row_id="E-1")
    chart = stmt(source="emr", generic="amlodipine", doc_date=ADMITTED, row_id="E-2")
    assert evidence_state("levothyroxine", "emr", cov, [june, chart]) is EvidenceState.ABSENT_IN_SCOPE
    assert evidence_state("amlodipine", "emr", cov, [june, chart]) is EvidenceState.PRESENT


def test_a_combination_asserts_each_of_its_ingredients() -> None:
    caduet = stmt(generic="amlodipine/atorvastatin",
                  ingredients=[("amlodipine", 5.0), ("atorvastatin", 10.0)])
    assert evidence_state("atorvastatin", "gp", FOUND, [caduet]) is EvidenceState.PRESENT


def test_a_combination_is_present_where_all_its_components_are() -> None:
    """Coversyl Plus on one list and perindopril + indapamide charted separately
    is the same therapy (brief 8, section 4) -- not an omission of the
    combination."""
    cov = Coverage(source="emr", state="found")
    parts = [stmt(source="emr", generic="perindopril", row_id="E-1"),
             stmt(source="emr", generic="indapamide", row_id="E-2")]
    assert evidence_state("perindopril/indapamide", "emr", cov, parts) is EvidenceState.PRESENT


def test_a_combination_is_not_present_on_one_component_alone() -> None:
    cov = Coverage(source="emr", state="found")
    assert evidence_state("perindopril/indapamide", "emr", cov,
                          [stmt(source="emr", generic="perindopril")]) is EvidenceState.ABSENT_IN_SCOPE
