"""The HTTP surface the UI calls (PLAN 5.6), on the replay set. No network."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.main import create_app
from app.orchestrator import Orchestrator
from app.schemas import RunResponse


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


def _client(make_settings: Callable[..., Any], tmp_path, *, background: bool) -> TestClient:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    orch = Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)
    return TestClient(create_app(orch, background=background))


@pytest.fixture
def api(make_settings, tmp_path):
    with _client(make_settings, tmp_path, background=False) as c:
        yield c


def test_status_reports_sample_mode_without_touching_a_service(api) -> None:
    body = api.get("/status").json()
    assert body["status"] == "ok" and body["sample_mode"] is True
    assert body["zetaris"] == "sample_mode" and body["meterless"] == "sample_mode"


def test_patients(api) -> None:
    pts = api.get("/patients").json()["patients"]
    assert len(pts) == 200 and pts[0]["patient_id"].startswith("MRN")


def test_post_run_wait_returns_the_final_response(api) -> None:
    r = api.post("/run?wait=true", json={"patient_id": "MRN0000089"})
    assert r.status_code == 200
    body = RunResponse.model_validate(r.json())
    assert body.status == "success" and len(body.findings) == 5
    assert api.get(f"/run/{body.run_id}").json()["status"] == "success"
    trace = api.get(f"/run/{body.run_id}/trace").json()
    assert trace and trace[-1]["step"] == "DONE"


def test_post_run_returns_running_then_the_ui_polls(make_settings, tmp_path) -> None:
    with _client(make_settings, tmp_path, background=True) as api:
        first = api.post("/run", json={"patient_id": "MRN0000089"}).json()
        assert first["status"] in ("running", "success") and first["run_id"]
        deadline = time.monotonic() + 30
        body = first
        while body["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
            body = api.get(f"/run/{first['run_id']}").json()
        assert body["status"] == "success" and body["findings"]


def test_identity_review_over_http(api) -> None:
    paused = api.post("/run?wait=true", json={"patient_id": "MRN0000015"}).json()
    assert paused["status"] == "needs_review"
    cand = paused["identity_review"]["candidates"][0]["candidate_id"]
    done = api.post(f"/run/{paused['run_id']}/identity?wait=true",
                    json={"candidate_id": cand, "same_person": True}).json()
    assert done["status"] == "success" and any(f["generic"] == "warfarin" for f in done["findings"])
    again = api.post(f"/run/{paused['run_id']}/identity", json={"candidate_id": cand, "same_person": True})
    assert again.status_code == 409  # no longer waiting


def test_learning_demo_over_http(api) -> None:
    """TODO_ARNAV: reject P0003's GP dose as outdated -> P0007 resolves differently."""
    before = api.post("/run?wait=true", json={"patient_id": "MRN0000007"}).json()
    assert not any(f["generic"] == "rosuvastatin" for f in before["findings"])
    teach = api.post("/run?wait=true", json={"patient_id": "MRN0000003"}).json()
    fb = api.post("/feedback", json={"run_id": teach["run_id"], "target_id": "grid:candesartan:daily_dose",
                                     "verdict": "reject", "reason": "source_outdated",
                                     "source": "gp", "attribute": "daily_dose"}).json()
    assert fb["trust_updates"] == [{"source": "gp", "attribute": "daily_dose", "hmem_record_id": "trust:gp:daily_dose",
                                    "kind": "wrong", "before": 0.7, "after": 0.5, "delta": -0.2}]
    after = api.post("/run?wait=true", json={"patient_id": "MRN0000007"}).json()
    assert any(f["type"] == "dose" and f["generic"] == "rosuvastatin" for f in after["findings"])


def test_feedback_on_a_finding_and_acceptance(api) -> None:
    run = api.post("/run?wait=true", json={"patient_id": "MRN0000089"}).json()
    target = next(f for f in run["findings"] if f["generic"] == "esomeprazole")
    fb = api.post("/feedback", json={"run_id": run["run_id"], "target_id": target["id"], "verdict": "reject",
                                     "reason": "intentional_change"}).json()
    assert fb["acceptance_updates"] and fb["acceptance_updates"][0]["after"] < fb["acceptance_updates"][0]["before"]
    assert all(u["kind"] == "not_helpful" for u in fb["trust_updates"])


@pytest.mark.parametrize("method,path,body,code", [
    ("post", "/run", {"patient_id": "MRN9999999"}, 404),
    ("get", "/run/run-nope", None, 404),
    ("post", "/run/run-nope/identity", {"candidate_id": "x", "same_person": True}, 404),
    ("post", "/feedback", {"run_id": "run-nope", "target_id": "F1", "verdict": "confirm"}, 404),
    ("post", "/feedback", {"run_id": "r", "target_id": "F1", "verdict": "reject"}, 422),
    ("post", "/run", {"patient_id": "MRN0000089", "surprise": 1}, 422),
])
def test_errors(api, method, path, body, code) -> None:
    r = getattr(api, method)(path, json=body) if body is not None else getattr(api, method)(path)
    assert r.status_code == code


def test_cors_allows_the_vite_dev_server(api) -> None:
    r = api.options("/status", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
