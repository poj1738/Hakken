"""Scan S36: dose findings say what each source wrote (`detail.by_source`) and lead with one
line (`detail.statement`), for the finding card (Anshu's S37). No network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents import writer
from app.agents.evaluator import _source_words, claim_problems
from app.orchestrator import Orchestrator
from app.schemas import IdentityDecisionRequest, RunRequest


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


@pytest.fixture
def orch(make_settings: Callable[..., Any], tmp_path) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)


@pytest.fixture
def p0015(orch):
    first = orch.start(RunRequest(patient_id="MRN0000015"))
    return orch.resume(first.run_id, IdentityDecisionRequest(candidate_id="patient:INT00015", same_person=True))


def test_warfarin_says_what_each_source_wrote(p0015) -> None:
    f = next(f for f in p0015.findings if f.id == "dose_unconfirmable:warfarin")
    assert f.detail["by_source"] == {
        "gp": "variable per INR",
        "pharmacy": "3 fills, latest 5 mg, 50 per 50 days, no dose stated",
        "patient": "not sure how much now, the clinic changes it",
        "emr": "5 mg variable per INR",
    }
    assert f.detail["statement"].startswith("No source confirms the current dose: GP variable per INR")
    assert "patient 'not sure how much now" in f.detail["statement"]


def test_insulin_aspart_card_names_the_gap(p0015) -> None:
    f = next(f for f in p0015.findings if f.id == "dose_unconfirmable:insulin aspart")
    assert f.detail["by_source"]["gp"] == "as directed"
    assert f.detail["by_source"]["patient"] == "up 2 units every three days"
    assert f.detail["by_source"]["pharmacy"].endswith("no dose stated")


def test_chart_comparisons_keep_their_statement_and_gain_by_source(orch) -> None:
    r = orch.start(RunRequest(patient_id="MRN0000089"))
    f = next(f for f in r.findings if f.id == "frequency:esomeprazole")
    assert f.detail["statement"] == "charted 80 mg/day against 40 mg/day before admission"
    assert f.detail["by_source"]["gp"] == "one a day" and f.detail["by_source"]["emr"] == "40 mg 1 bd"
    others = [f for f in r.findings if f.type.value in ("omission", "stale_listing", "duplication")]
    assert others and all("by_source" not in f.detail for f in others)


def test_every_template_with_a_statement_still_passes_the_verifier(p0015) -> None:
    for f in p0015.findings:
        assert claim_problems(f.model_copy(update={"explanation": writer.template(f)})) == [], f.id


@pytest.mark.parametrize("source,rows,words", [
    ("emr", [{"record_kind": "admission_chart", "dose_text": "11", "strength_text": "100 units/mL",
              "freq_text": "tds with meals"}], "11 units tds with meals"),
    ("emr", [{"record_kind": "prior_discharge", "dose_text": "10.0", "strength_text": "10 mg", "freq_text": "1 daily"},
             {"record_kind": "admission_chart", "dose_text": "20.0", "strength_text": "20 mg", "freq_text": "1 daily"}],
     "20 mg 1 daily"),
    ("pharmacy", [{"strength_text": "5 mg", "qty": "50", "days_supply": "50"}], "5 mg, 50 per 50 days, no dose stated"),
    ("gp", [{"freq_text": "as directed"}], "as directed"),
    ("patient", [{"med_text": "my blue puffer"}], "my blue puffer"),
    ("gp", [], None),
])
def test_source_words(source, rows, words) -> None:
    assert _source_words(source, rows) == words
