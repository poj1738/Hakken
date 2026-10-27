"""27 Oct: Nightshift cuts any call at ~90 s, so the Writer and the critique run in batches of at
most MODEL_BATCH findings. Zetaris is the replay set; Nightshift is a mock that answers each
schema plausibly. No network."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents.evaluator import claim_problems
from app.orchestrator import MODEL_BATCH, Orchestrator
from app.schemas import RunRequest


def _nightshift(log: list[tuple[str, int]], fail_draft_call: int | None = None, unfaithful: bool = False):
    """A mock Runtime. Logs (kind, findings in the request); can fail one Writer draft batch with 499s."""
    drafts = {"n": 0}

    def answer(payload: dict) -> Any:
        text = payload["messages"][-1]["content"]
        brief = text.rsplit("\n", 1)[-1]
        if text.startswith("Write the explanation"):
            items = json.loads(brief)
            log.append(("draft", len(items)))
            return {"explanations": [{"id": f["id"], "text": f"Confirm {f['generic']} with the patient "
                                                             f"({next(iter(f['rows']))})."} for f in items]}
        if text.startswith("Write a 2-3 sentence summary"):
            log.append(("summary", len(json.loads(brief))))
            return {"summary": "Confirm the findings below with the patient."}
        if text.startswith("You check TEXT against DATA"):
            items = json.loads(brief)
            log.append(("critique", len(items)))
            return {"verdicts": [{"id": f["id"], "faithful": not unfaithful, "issue": "test objection"}
                                 for f in items]}
        if text.startswith("Map each free-text"):
            return {"items": []}
        return {"steps": [{"tool": t, "need": t} for t in ("find_identities", "fetch_meds", "verify")],
                "rationale": "core path"}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        text = payload["messages"][-1]["content"]
        if text.startswith("Write the explanation"):
            drafts["n"] += 1
            if fail_draft_call is not None and drafts["n"] in (fail_draft_call, fail_draft_call + 1):
                return httpx.Response(499, json={"error": "Fetch is aborted"})  # first try and its one retry
        body = {"id": "x", "model": "nvidia/nemotron-a", "usage": {"completion_tokens": 50},
                "choices": [{"message": {"content": json.dumps(answer(payload))}}]}
        return httpx.Response(200, json=body)
    return handler


def _orch(make_settings: Callable[..., Any], tmp_path, handler) -> Orchestrator:
    zs = make_settings(sample_mode=True)
    ls = make_settings(meterless_runtime_token="example-runtime-token", max_retries=0)
    o = Orchestrator(ls, llm=MeterlessClient(ls, transport=httpx.MockTransport(handler), sleep=lambda _s: None),
                     zetaris=ZetarisClient(zs), log_dir=tmp_path)
    o.settings = ls  # live model calls; Zetaris stays on the replay set
    return o


def test_writer_and_critique_calls_carry_at_most_two_findings(make_settings, tmp_path) -> None:
    log: list[tuple[str, int]] = []
    r = _orch(make_settings, tmp_path, _nightshift(log)).start(RunRequest(patient_id="MRN0000089"))
    assert r.status == "success" and len(r.findings) == 5
    drafts = [n for k, n in log if k == "draft"]
    critiques = [n for k, n in log if k == "critique"]
    assert drafts == [2, 2, 1] and critiques == [2, 2, 1]
    assert all(n <= MODEL_BATCH for n in drafts + critiques)
    assert [k for k, _ in log].count("summary") == 1
    assert all(f.explanation.startswith("Confirm ") for f in r.findings)
    assert r.output.summary == "Confirm the findings below with the patient."


def test_a_failed_batch_loses_only_its_own_explanations(make_settings, tmp_path) -> None:
    log: list[tuple[str, int]] = []
    r = _orch(make_settings, tmp_path, _nightshift(log, fail_draft_call=2)).start(RunRequest(patient_id="MRN0000089"))
    assert r.status == "partial" and len(r.findings) == 5
    model_written = [f for f in r.findings if f.explanation.startswith("Confirm ")]
    assert len(model_written) == 3  # batches 1 and 3; batch 2 (two findings) fell back to the template
    assert all(claim_problems(f) == [] for f in r.findings)
    assert sum("Nightshift unavailable for writer draft" in c for c in r.output.caveats) == 1
    failed = [c for c in r.model_calls if c.role == "Writer" and c.routed_model is None]
    assert len(failed) == 1  # the 499'd batch is still listed (S9)


def test_a_request_can_ask_for_fewer_critique_rounds(make_settings, tmp_path) -> None:
    """Scan S26: max_iterations=1 is honoured (capped by the server's setting, never raised).
    The critique objects to everything, so with one round nothing is revised: every
    explanation falls back to the grounded template, and no revise call is made."""
    log: list[tuple[str, int]] = []
    o = _orch(make_settings, tmp_path, _nightshift(log, unfaithful=True))
    r = o.start(RunRequest(patient_id="MRN0000089", max_iterations=1))
    assert [k for k, _ in log].count("draft") == 3  # the first drafts only; no revise round
    assert not any(f.explanation.startswith("Confirm ") for f in r.findings)
    log.clear()
    o.start(RunRequest(patient_id="MRN0000089"))  # the server default (2) does revise
    assert [k for k, _ in log].count("draft") > 3
