"""`datasvc`, the service Zetaris registers as REST tables.

The contract is narrow but unforgiving: a Lightning REST table binds one fixed
URL and explodes one array field, so every endpoint must return the whole table
as `{"records": [...]}` with no paging (`REFERENCE_NOTES` 1.3).
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from datasvc.main import REFERENCES, SILOS, app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_healthz_reports_both_urls_and_what_is_present(client: TestClient) -> None:
    """Two URLs reach this service from two networks, and getting them the wrong
    way round makes registration succeed and every query fail -- so both are
    visible here rather than only in the registration SQL."""
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["public_url"] and body["internal_url"]
    assert set(body["silos"]) == set(SILOS)
    assert set(body["references"]) == set(REFERENCES)


@pytest.mark.parametrize("name", sorted(SILOS))
def test_each_silo_serves_a_records_array(client: TestClient, name: str) -> None:
    if not (pathlib.Path("data/synthetic/silos") / SILOS[name]).exists():
        pytest.skip("run `make synth` first")
    body = client.get(f"/silos/{name}").json()
    assert isinstance(body["records"], list) and body["records"]
    assert set(body) == {"records"}, "a REST table explodes one array field; keep the body minimal"


@pytest.mark.parametrize("name", sorted(REFERENCES))
def test_each_reference_table_serves_a_records_array(client: TestClient, name: str) -> None:
    if not (pathlib.Path("data/reference") / REFERENCES[name]).exists():
        pytest.skip("run `make lexicon` first")
    body = client.get(f"/ref/{name}").json()
    assert isinstance(body["records"], list) and body["records"]


def test_every_served_value_is_a_string(client: TestClient) -> None:
    """Zetaris returns strings. If the source serves an int, the replayed fixture
    and the live view disagree about types and `parse.py` is tested against the
    wrong thing."""
    if not pathlib.Path("data/reference/lexicon.json").exists():
        pytest.skip("run `make lexicon` first")
    for record in client.get("/ref/lexicon").json()["records"][:50]:
        for key, value in record.items():
            assert isinstance(value, str), f"lexicon.{key} is {type(value).__name__}"


def test_an_unknown_name_is_a_404_naming_the_valid_ones(client: TestClient) -> None:
    for path in ("/silos/nope", "/ref/nope"):
        response = client.get(path)
        assert response.status_code == 404
        assert "known" in response.json()["detail"]


def test_tga_is_deliberately_not_served(client: TestClient) -> None:
    """Q4 is Monday and optional. Serving a view over data we have not licensed
    would be worse than shipping without it."""
    assert "tga" not in REFERENCES
    assert client.get("/ref/tga").status_code == 404


def test_a_missing_file_is_503_with_the_command_to_fix_it(client: TestClient, tmp_path) -> None:
    """`data/synthetic/silos/` is gitignored, so a fresh clone has no silos. That
    must say what to run, not 500."""
    import datasvc.main as mod

    original = mod.SILO_DIR
    mod.SILO_DIR = tmp_path / "missing"
    mod._cache.clear()
    try:
        response = client.get("/silos/emr")
        assert response.status_code == 503
        assert "make synth" in response.json()["detail"]
    finally:
        mod.SILO_DIR = original
        mod._cache.clear()


def test_a_body_without_records_is_rejected(client: TestClient, tmp_path) -> None:
    """A REST table needs one array field to explode; without it, registration
    succeeds and every query fails."""
    import datasvc.main as mod

    bad = tmp_path / "silos"
    bad.mkdir()
    (bad / "emr.json").write_text(json.dumps({"rows": []}))
    original = mod.SILO_DIR
    mod.SILO_DIR = bad
    mod._cache.clear()
    try:
        response = client.get("/silos/emr")
        assert response.status_code == 500
        assert "records" in response.json()["detail"]
    finally:
        mod.SILO_DIR = original
        mod._cache.clear()
