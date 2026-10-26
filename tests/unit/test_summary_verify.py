"""Scan S10: the Writer's summary gets the same code checks as an explanation, and neither
may instruct a therapy change. No network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents import writer
from app.agents.evaluator import claim_problems, summary_problems
from app.orchestrator import Orchestrator
from app.schemas import RunRequest


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


@pytest.fixture
def orch(make_settings: Callable[..., Any], tmp_path) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)


@pytest.fixture
def p0089(orch):
    r = orch.start(RunRequest(patient_id="MRN0000089"))
    return r, orch._load_anchors()["MRN0000089"]


@pytest.mark.parametrize("text", [
    "Stop oxycodone/naloxone.",
    "Gliclazide is missing. Restart it on the ward.",
    "Esomeprazole should be reduced to once daily.",
    "We recommend switching to the GP dose.",
    "Consider withholding gliclazide.",
])
def test_an_instruction_is_a_problem_in_an_explanation(p0089, text) -> None:
    r, _ = p0089
    f = r.findings[0]
    rows = " ".join(f"({e.row_id})" for e in f.evidence)
    bad = f.model_copy(update={"explanation": f"{text} {rows}"})
    assert any("instructs a therapy change" in p for p in claim_problems(bad))


@pytest.mark.parametrize("text", [
    "Ask first; do not stop it on this evidence alone.",
    "The GP stopped it at the last review; confirm with the patient.",
    "Confirm whether the dose was changed at discharge.",
])
def test_confirming_language_is_not_an_instruction(p0089, text) -> None:
    r, anchor = p0089
    assert not [p for p in summary_problems(text, r.findings, anchor, None) if "instructs" in p]


def test_every_template_and_the_grounded_summary_pass(p0089) -> None:
    r, anchor = p0089
    for f in r.findings:
        assert claim_problems(f.model_copy(update={"explanation": writer.template(f)})) == []
    assert summary_problems(writer._offline_summary(r.findings, anchor, None), r.findings, anchor, None) == []


def test_the_summary_checks(p0089) -> None:
    r, anchor = p0089
    rows = sorted(e.row_id for f in r.findings for e in f.evidence)
    assert summary_problems(f"Confirm gliclazide with the patient ({rows[0]}).", r.findings, anchor, None) == []
    assert any("cites rows no finding rests on" in p
               for p in summary_problems("See GP-999999.", r.findings, anchor, None))
    assert any("numbers not in the evidence" in p
               for p in summary_problems("Gliclazide 987 mg is missing.", r.findings, anchor, None))
    assert any("instructs" in p for p in summary_problems("Stop gliclazide.", r.findings, anchor, None))


def test_a_bad_summary_is_replaced_and_traced(orch, monkeypatch) -> None:
    real = writer.draft

    def draft(ctx, findings, anchor, banner, *, problems=None):
        texts, summary = real(ctx, findings, anchor, banner, problems=problems)
        return texts, (None if problems else "Stop oxycodone/naloxone now (GP-999999); 987 mg.")

    monkeypatch.setattr(writer, "draft", draft)
    r = orch.start(RunRequest(patient_id="MRN0000089"))
    assert "Stop" not in r.output.summary and r.output.summary.startswith("5 finding(s)")
    blocked = [e for e in r.trace if e.status == "blocked" and "summary" in e.message]
    assert len(blocked) == 1 and "instructs a therapy change" in blocked[0].message
