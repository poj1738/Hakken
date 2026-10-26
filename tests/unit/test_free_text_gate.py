"""Scan S15: free text resolves only when the text names a medicine and the model is sure.
Nightshift is a mock transport; no network."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents import executor
from app.domain.packs.medtrace.types import MedStatement
from app.orchestrator import Orchestrator
from app.schemas import RunRequest

CANDIDATES = {
    "a little white one": {"ingredients": ["calcitriol", "dapagliflozin", "eplerenone", "carvedilol",
                                           "amlodipine"], "atc_classes": []},
    "my fluid tablet": {"ingredients": ["furosemide", "indapamide"], "atc_classes": []},
}


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used")


def _stmt(row: str, raw: str) -> MedStatement:
    return MedStatement(source="patient", row_id=row, raw_text=raw, resolution="unmapped", status="active",
                        doc_date=date(2026, 10, 1))


@pytest.fixture
def ctx(make_settings: Callable[..., Any], tmp_path, monkeypatch):
    """A real run context (lexicon, tracer) whose model is a mock Nightshift."""
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    orch = Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)
    ctx = orch.runs[orch.create(RunRequest(patient_id="MRN0000089"))].ctx
    monkeypatch.setattr(executor, "llm_candidates", lambda text, _lex: CANDIDATES[text])
    sent: list[dict] = []

    def answer(items: list[dict]) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            body = {"id": "x", "model": "nvidia/nemotron-a", "usage": {"completion_tokens": 40},
                    "choices": [{"message": {"content": json.dumps({"items": items})}}]}
            return httpx.Response(200, json=body)
        live = make_settings(meterless_runtime_token="example-runtime-token")
        ctx.llm = MeterlessClient(live, transport=httpx.MockTransport(handler), sleep=lambda _s: None)

    ctx.answer, ctx.sent = answer, sent
    return ctx


def test_text_that_names_no_medicine_is_never_sent_to_the_model(ctx) -> None:
    ctx.answer([])
    out, tasks = executor.resolve_free_text(ctx, [_stmt("PAT-1", "a little white one")])
    assert ctx.sent == [] and out[0].resolution == "unmapped" and out[0].generic is None and tasks == []
    skipped = [e for e in ctx.tracer.events if e.status == "skipped"]
    assert skipped and "names no medicine" in skipped[-1].message and "calcitriol" in skipped[-1].message


def test_a_low_confidence_answer_stays_unmapped(ctx) -> None:
    ctx.answer([{"row_id": "PAT-2", "choice": "furosemide", "confidence": 0.55}])
    out, _ = executor.resolve_free_text(ctx, [_stmt("PAT-2", "my fluid tablet")])
    assert len(ctx.sent) == 1 and out[0].resolution == "unmapped" and out[0].generic is None
    assert "below confidence 0.8" in ctx.tracer.events[-1].message


def test_a_confident_answer_from_the_list_resolves(ctx) -> None:
    ctx.answer([{"row_id": "PAT-2", "choice": "furosemide", "confidence": 0.9}])
    out, _ = executor.resolve_free_text(ctx, [_stmt("PAT-2", "my fluid tablet")])
    assert out[0].resolution == "llm" and out[0].generic == "furosemide"
    assert ctx.model_calls[-1].routed_model == "nvidia/nemotron-a"


def test_only_identifiable_lines_reach_the_model(ctx) -> None:
    ctx.answer([{"row_id": "PAT-2", "choice": "furosemide", "confidence": 0.95}])
    out, _ = executor.resolve_free_text(ctx, [_stmt("PAT-1", "a little white one"), _stmt("PAT-2", "my fluid tablet")])
    prompt = ctx.sent[0]["messages"][-1]["content"]
    assert "PAT-2" in prompt and "PAT-1" not in prompt
    assert [s.resolution for s in out] == ["unmapped", "llm"]
