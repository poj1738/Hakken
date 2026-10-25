"""Regression tests for the scan items handed over from Arpon (docs/SCAN_2026-10-25.md)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.domain.packs.medtrace import coverage, identity, parse
from app.domain.packs.medtrace.types import Coverage, EvidenceState, MedStatement

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "medtrace"


def _stmt(source: str, row: str, raw: str, *, generic: str | None = None, atc: str | None = None,
          resolution: str = "lexicon") -> MedStatement:
    return MedStatement(source=source, row_id=row, raw_text=raw, generic=generic, atc=atc, resolution=resolution,
                        status="active", doc_date=date(2026, 10, 1))


@pytest.mark.parametrize("phrase,generic,atc", [
    ("spray under the tongue", "glyceryl trinitrate", "C01DA02"),
    ("my blue puffer", "salbutamol", "R03AC02"),
    ("the cholesterol tablet", "rosuvastatin", "C10AA07"),
])
def test_s7_an_unmapped_lay_term_line_is_unknown_not_absent(phrase, generic, atc) -> None:
    stmts = [_stmt("gp", "GP-1", generic, generic=generic, atc=atc),
             _stmt("patient", "PAT-1", phrase, resolution="unmapped")]
    found = Coverage(source="patient", state="found")
    assert coverage.evidence_state(generic, "patient", found, stmts) is EvidenceState.UNKNOWN


def test_s7_an_unrelated_lay_term_still_leaves_absent() -> None:
    """A thyroid tablet says nothing about a statin: absence still counts."""
    stmts = [_stmt("gp", "GP-1", "rosuvastatin", generic="rosuvastatin", atc="C10AA07"),
             _stmt("patient", "PAT-1", "my thyroid tablet", resolution="unmapped")]
    found = Coverage(source="patient", state="found")
    assert coverage.evidence_state("rosuvastatin", "patient", found, stmts) is EvidenceState.ABSENT_IN_SCOPE


def test_s19_the_admission_chart_is_not_one_of_the_two_sources() -> None:
    cov = {"emr": Coverage(source="emr", state="found"), "gp": Coverage(source="gp", state="not_found"),
           "pharmacy": Coverage(source="pharmacy", state="not_found"),
           "patient": Coverage(source="patient", state="found")}
    ok, banner = coverage.bpmh_confirmable(cov)
    assert ok is False and "1 of 3 pre-admission sources" in banner
    cov["pharmacy"] = Coverage(source="pharmacy", state="found")
    assert coverage.bpmh_confirmable(cov) == (True, "")


@pytest.mark.parametrize("key,mrn,other", [("P0015", "MRN0000015", "Malcolm Walker"),
                                           ("P0013", "MRN0000013", "Joseph Young")])
def test_s22_the_review_reason_names_the_real_other_person(key, mrn, other) -> None:
    def d(n: str):
        return parse.dicts_from_sql(json.loads((FIX / f"Q_REF__{n}.json").read_text()))
    lex = parse.build_lexicon(d("lexicon"), d("apinchs"), d("nicknames"))
    rows = parse.rows_from_sql(json.loads((FIX / f"Q1__{key}.json").read_text()))
    anchor = next(r for r in rows if r.source_patient_id == mrn)
    review = [l for l in identity.link_identity(anchor, [r for r in rows if r.record_key != anchor.record_key], lex)
              if l.band == "review"]
    assert review
    reason = review[0].field_evidence["guard"]
    assert reason.startswith("held: ") and other in reason
    assert "same name and date of birth" not in reason  # false in both demo pauses
