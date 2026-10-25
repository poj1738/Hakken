"""The learning demo, pinned on the committed replay fixtures.

PLAN's 2:15 beat: the pharmacist rejects patient A's GP dose as outdated
(`source_outdated`, PLAN 5.7: GP `daily_dose` 0.70 -> 0.50), then runs patient
B, and B resolves differently. Before 25 Oct nothing in the replay set changed
under one rejection, so the beat would have shown nothing. The pair is staged by
`scripts/generate_synthetic.py` (`LEARNING_PAIR`); this holds it.

Runs on `tests/fixtures/medtrace/` alone -- exactly what `SAMPLE_MODE` replays --
so it needs no `make synth` and runs in CI.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from app.domain.packs.medtrace.coverage import coverage, evidence_state
from app.domain.packs.medtrace.detect import detect_discrepancies
from app.domain.packs.medtrace.fuse import fuse
from app.domain.packs.medtrace.normalise import normalise_med
from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql, rows_from_sql
from app.domain.packs.medtrace.triage import prioritise
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.domain.packs.medtrace.types import SOURCES

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "medtrace"
AS_OF = date(2026, 10, 24)
#: PLAN 5.7: one `source_outdated` rejection.
ONE_REJECTION = -0.20

TEACH = ("P0003", "candesartan", 8.0)    # A: the pharmacist rejects the GP dose here
LEARN = ("P0007", "rosuvastatin", 10.0)  # B: run afterwards


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def lex():
    return build_lexicon(*(dicts_from_sql(_load(f"Q_REF__{n}"))
                           for n in ("lexicon", "apinchs", "nicknames")))


def _run(key: str, lex, gp_dose_delta: float):
    rows = rows_from_sql(_load(f"Q2__{key}"))
    cov = coverage([], rows)
    stmts = [normalise_med(r, lex) for r in rows if r.has_med]
    evidence = {g: {s: evidence_state(g, s, cov[s], stmts) for s in SOURCES}
                for g in sorted({s.generic for s in stmts if s.generic})}
    trust = dict(SOURCE_TRUST_PRIORS)
    trust[("gp", "daily_dose")] += gp_dose_delta
    fused = fuse(stmts, evidence, trust, AS_OF)
    findings = prioritise(detect_discrepancies(fused, stmts, cov, AS_OF, lex), {})
    return {m.generic: m for m in fused}, findings


@pytest.mark.parametrize("key,generic,_", [TEACH, LEARN])
def test_before_any_feedback_the_dose_abstains(lex, key, generic, _) -> None:
    """A year-old GP list against a fill six days ago: neither wins by the margin."""
    fused, findings = _run(key, lex, 0.0)
    assert "daily_dose" in fused[generic].abstained
    assert not any(f.generic == generic for f in findings)


@pytest.mark.parametrize("key,generic,dose", [TEACH, LEARN])
def test_one_rejection_resolves_to_the_pharmacy_dose(lex, key, generic, dose) -> None:
    fused, _ = _run(key, lex, ONE_REJECTION)
    resolved = fused[generic].attributes["daily_dose"]
    assert "daily_dose" not in fused[generic].abstained
    assert resolved.value == pytest.approx(dose)


def test_patient_b_then_surfaces_the_chart_error(lex) -> None:
    """The visible half: B's chart copied the stale GP dose, which the abstention
    hid. Once B's dose resolves, the chart-vs-BPMH comparison catches it."""
    key, generic, _ = LEARN
    _, findings = _run(key, lex, ONE_REJECTION)
    dose = [f for f in findings if f.generic == generic and f.type.value == "dose"]
    assert len(dose) == 1
    assert "EMR-000060" in dose[0].row_ids


def test_patient_a_gains_no_finding_from_the_lesson(lex) -> None:
    """A's chart was right; the lesson must not invent a finding on A."""
    key, generic, _ = TEACH
    _, findings = _run(key, lex, ONE_REJECTION)
    assert not any(f.generic == generic for f in findings)
