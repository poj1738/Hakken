"""Data map catalogue and endpoints, on the recorded envelopes. No network, no writes."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import REPLAY_DIR, ZetarisClient, check_read_only
from app.data_map import CATALOGUE
from app.main import create_app
from app.orchestrator import Orchestrator

_FORBIDDEN = ("RUN DQ", "LIST DQ", "REGISTER", "CACHE", "REFRESH")


def test_every_catalogue_statement_is_read_only() -> None:
    assert CATALOGUE, "the catalogue is empty"
    ids = [query.id for query in CATALOGUE]
    assert ids == list(dict.fromkeys(ids))
    for query in CATALOGUE:
        assert check_read_only(query.sql) == query.sql
        folded = query.sql.upper()
        for word in _FORBIDDEN:
            assert word not in folded, query.id
        assert query.template_id.startswith("MAP_")
        assert query.sql.startswith("SELECT ")


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


@pytest.fixture
def dm_api(make_settings: Callable[..., Any], tmp_path):
    settings = make_settings(sample_mode=True)
    transport = httpx.MockTransport(_no_network)
    orch = Orchestrator(
        settings,
        llm=MeterlessClient(settings, transport=transport),
        zetaris=ZetarisClient(settings, transport=transport),
        log_dir=tmp_path,
    )
    with TestClient(create_app(orch, background=False)) as client:
        yield client


def test_queries_lists_every_id_in_catalogue_order(dm_api: TestClient) -> None:
    body = dm_api.get("/data-map/queries").json()
    listed = body["queries"]
    assert [item["id"] for item in listed] == [query.id for query in CATALOGUE]
    for item, query in zip(listed, CATALOGUE, strict=True):
        assert item["label"] == query.label
        assert item["sql"] == query.sql
        assert "data" not in item
        assert "latency_ms" not in item


def test_each_query_returns_the_recorded_envelope(dm_api: TestClient) -> None:
    for query in CATALOGUE:
        response = dm_api.get(f"/data-map/query/{query.id}")
        assert response.status_code == 200, response.text
        body = response.json()
        recorded = json.loads((REPLAY_DIR / f"{query.template_id}__{query.replay_key}.json").read_text())
        assert body["headers"] == recorded["headers"]
        assert body["data"] == recorded["data"]
        assert body["sql"] == query.sql
        assert body["label"] == query.label
        assert body["row_count"] == len(recorded["data"])
        assert body["replayed"] is True
        assert body["error"] is None
        assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
        assert isinstance(body["executed_at"], str) and body["executed_at"]


def test_examples_are_read_after_the_quality_count() -> None:
    ids = [query.id for query in CATALOGUE]
    assert ids[-1] == "dq_examples"
    query = CATALOGUE[-1]
    assert query.label == "Data-quality examples"
    assert query.sql.startswith("SELECT med_text, strength_text, source_system ")
    assert "LIMIT 3" in query.sql
    assert ids.index("dq") < ids.index("spellings") < ids.index("dq_examples")
    spellings = next(query for query in CATALOGUE if query.id == "spellings")
    assert spellings.label == "Same medicine, many ways"
    assert "COUNT(DISTINCT med_text)" in spellings.sql
    assert "GROUP BY generic" in spellings.sql


def test_unknown_query_is_404(dm_api: TestClient) -> None:
    response = dm_api.get("/data-map/query/not-a-query")
    assert response.status_code == 404
    assert "not-a-query" in response.json()["detail"]


def test_missing_replay_is_503_and_names_the_file(dm_api: TestClient, tmp_path) -> None:
    empty = tmp_path / "empty-replay"
    empty.mkdir()
    dm_api.app.state.orchestrator.zetaris._replay_dir = empty
    query = CATALOGUE[0]
    response = dm_api.get(f"/data-map/query/{query.id}")
    assert response.status_code == 503
    assert f"{query.template_id}__{query.replay_key}.json" in response.json()["detail"]
