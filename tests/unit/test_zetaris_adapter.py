"""The Zetaris adapter against REFERENCE_NOTES 1.1-1.2 and PLAN 5.2. No network: MockTransport."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.adapters.zetaris import (
    REPLAY_DIR,
    QueryBudgetExceeded,
    ReplayMiss,
    RunQueries,
    ZetarisClient,
    ZetarisError,
    _replay_index,
    check_read_only,
    load_lexicon,
)
from app.domain.packs.medtrace import queries

KEY = "example-zetaris-key"  # a dummy; "example" is on the secret scan's allowlist
ENVELOPE = {"headers": ["source", "name_previous", "qty"],
            "data": [["gp", None, "60"], ["pharmacy", "SMITH", "30"]], "total": 2, "timeUsed": 812}


class Recorder:
    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def client(make_settings: Callable[..., Any], rec: Recorder, **overrides: Any) -> ZetarisClient:
    return ZetarisClient(make_settings(zetaris_api_key=KEY, **overrides), transport=httpx.MockTransport(rec),
                         sleep=lambda _s: None)


SQL = "SELECT source FROM medtrace.all_sources"


# -- call shape and envelope ------------------------------------------------------


def test_request_follows_the_binding_call_shape(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=ENVELOPE))
    client(make_settings, rec, zetaris_org_id="1").run(SQL, template_id="Q2", limit=500)
    req = rec.requests[0]
    body = json.loads(req.content)
    assert str(req.url) == "http://localhost:8888/api/v1.0/sql-editor/sqls/run"
    assert req.headers["Authorization"] == f"Bearer {KEY}" and req.headers["X-Org-ID"] == "1"
    uuid.UUID(req.headers["X-Request-ID"])
    uuid.UUID(body["queryId"])
    assert body == {"queryId": body["queryId"], "sql": SQL, "source": "SqlEditor", "limit": 500}


def test_envelope_is_passed_on_untouched(make_settings) -> None:
    """Strings stay strings and NULL stays None -- casting is parse.py's job."""
    result, record = client(make_settings, Recorder(httpx.Response(200, json=ENVELOPE))).run(SQL, template_id="Q2")
    assert result["data"] == [["gp", None, "60"], ["pharmacy", "SMITH", "30"]]
    assert result["data"][0][1] is None and result["data"][0][2] == "60"
    assert (record.template_id, record.rows, record.sql) == ("Q2", 2, SQL) and not record.replayed


def test_empty_result_is_not_an_error(make_settings) -> None:
    empty = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "zetaris" / "empty_result.json").read_text())
    result, record = client(make_settings, Recorder(httpx.Response(200, json=empty))).run(SQL, template_id="Q3")
    assert result["data"] == [] and record.rows == 0


def test_a_malformed_envelope_is_refused(make_settings) -> None:
    bad = {"headers": ["a", "b"], "data": [["only-one"]]}
    with pytest.raises(ZetarisError, match="width"):
        client(make_settings, Recorder(httpx.Response(200, json=bad))).run(SQL, template_id="Q2")


def test_hitting_the_row_limit_is_refused_not_silently_truncated(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=ENVELOPE))
    with pytest.raises(ZetarisError, match="limit"):
        client(make_settings, rec).run(SQL, template_id="Q2", limit=2)


# -- read-only guard --------------------------------------------------------------


@pytest.mark.parametrize("sql", [
    SQL, "  select 1", "SHOW LIGHTNING DATABASES", "SHOW TABLES IN medtrace", "DESCRIBE medtrace.gp",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT * FROM t WHERE note = 'stop; then DROP it'",  # quoted text is data, not code
    "SELECT * FROM t WHERE name LIKE 'O\\'BR%'",           # the backslash escape (REFERENCE_NOTES 1.2)
])
def test_guard_allows_one_read_only_statement(sql: str) -> None:
    assert check_read_only(sql) == sql


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (1)", "DROP VIEW medtrace.gp", "CREATE SCHEMASTORE CONTAINER x",
    "SELECT 1;", "SELECT 1; SELECT 2", "SELECT * FROM t; DROP TABLE t",
    "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "CACHE TABLE medtrace.gp",
])
def test_guard_refuses_writes_and_multiple_statements(sql: str) -> None:
    with pytest.raises(ZetarisError):
        check_read_only(sql)


def test_guard_runs_before_any_network(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=ENVELOPE))
    with pytest.raises(ZetarisError):
        client(make_settings, rec).run("DROP VIEW medtrace.gp", template_id="free_sql")
    assert rec.requests == []


def test_every_real_template_passes_the_guard() -> None:
    from app.domain.packs.medtrace.types import SourceRow
    anchor = SourceRow(source="emr", row_id="EMR-1", source_patient_id="MRN0000001",
                       name_given="Christine", name_family="O'Brien", dob_raw="1955-01-25")
    for sql in (queries.q_admissions(), queries.q_identity_candidates(anchor),
                queries.q_verify_rows(["GP-000003", "PHM-000007"]),
                *(queries.q_reference(n) for n in ("lexicon", "apinchs", "nicknames"))):
        check_read_only(sql)


# -- errors and retries -----------------------------------------------------------


def test_missing_key_never_reaches_the_network(make_settings) -> None:
    rec = Recorder(httpx.Response(200, json=ENVELOPE))
    c = ZetarisClient(make_settings(), transport=httpx.MockTransport(rec))
    with pytest.raises(ZetarisError, match="ZETARIS_API_KEY"):
        c.run(SQL, template_id="Q2")
    assert rec.requests == []


@pytest.mark.parametrize("status", [400, 401, 404])
def test_client_errors_are_not_retried(make_settings, status: int) -> None:
    rec = Recorder(httpx.Response(status, json={"message": "Not Allowed"}))
    with pytest.raises(ZetarisError) as exc:
        client(make_settings, rec, max_retries=2).run(SQL, template_id="Q2")
    assert exc.value.status == status and len(rec.requests) == 1


def test_server_errors_are_retried_a_bounded_number_of_times(make_settings) -> None:
    rec = Recorder(httpx.Response(502, json={"message": "bad gateway"}))
    with pytest.raises(ZetarisError) as exc:
        client(make_settings, rec, max_retries=2).run(SQL, template_id="Q2")
    assert exc.value.recoverable and len(rec.requests) == 3


def test_a_blip_then_success(make_settings) -> None:
    rec = Recorder(httpx.ConnectError("refused"), httpx.Response(200, json=ENVELOPE))
    assert client(make_settings, rec).run(SQL, template_id="Q2")[1].rows == 2


def test_a_timeout_is_not_retried(make_settings) -> None:
    """A 91 s join that timed out once would cost 9 minutes if retried twice."""
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(ZetarisError, match="no answer") as exc:
        client(make_settings, rec, max_retries=2).run(SQL, template_id="Q2")
    assert exc.value.recoverable and len(rec.requests) == 1


def test_errors_never_contain_the_key(make_settings) -> None:
    rec = Recorder(httpx.Response(500, json={"message": "boom"}))
    with pytest.raises(ZetarisError) as exc:
        client(make_settings, rec, max_retries=0).run(SQL, template_id="Q2")
    assert KEY not in str(exc.value)


# -- the per-run budget -----------------------------------------------------------


def test_budget_allows_exactly_max_queries(make_settings) -> None:
    run = RunQueries(client(make_settings, Recorder(httpx.Response(200, json=ENVELOPE))))
    for _ in range(queries.MAX_ZETARIS_QUERIES_PER_RUN):
        run.run(SQL, template_id="Q2")
    with pytest.raises(QueryBudgetExceeded) as exc:
        run.run(SQL, template_id="Q2")
    assert exc.value.used == 8 and run.used == 8


def test_a_failed_query_still_spends_budget_and_is_recorded(make_settings) -> None:
    run = RunQueries(client(make_settings, Recorder(httpx.Response(400, json={"message": "bad sql"}))), budget=2)
    with pytest.raises(ZetarisError):
        run.run(SQL, template_id="Q1")
    assert run.used == 1 and run.records[0].error and run.records[0].rows is None


def test_records_carry_what_the_trace_needs(make_settings) -> None:
    run = RunQueries(client(make_settings, Recorder(httpx.Response(200, json=ENVELOPE))))
    run.run(SQL, template_id="Q2")
    fields = run.records[0].trace_fields()
    assert fields["sql"] == SQL and fields["row_count"] == 2 and fields["sql_template_id"] == "Q2"
    assert run.zetaris_ms >= 0


# -- SAMPLE_MODE replay -----------------------------------------------------------


def sample(make_settings) -> ZetarisClient:
    rec = Recorder(AssertionError("network used in SAMPLE_MODE"))
    return ZetarisClient(make_settings(sample_mode=True), transport=httpx.MockTransport(rec))


def test_replay_returns_the_recorded_envelope_by_mrn(make_settings) -> None:
    result, record = sample(make_settings).run(SQL, template_id="Q1", replay_key="MRN0000015")
    assert result == json.loads((REPLAY_DIR / "Q1__P0015.json").read_text())
    assert record.replayed and record.rows == len(result["data"])


def test_replay_of_q0_and_q_ref(make_settings) -> None:
    c = sample(make_settings)
    assert c.run(queries.q_admissions(), template_id="Q0", replay_key="admissions")[0]["data"]
    assert c.run(queries.q_reference("nicknames"), template_id="Q_REF", replay_key="nicknames")[0]["data"]


@pytest.mark.parametrize("key", ["MRN9999999", None])
def test_replay_miss_refuses_rather_than_guessing(make_settings, key) -> None:
    with pytest.raises(ReplayMiss):
        sample(make_settings).run(SQL, template_id="Q2", replay_key=key)


def test_replay_still_enforces_the_guard(make_settings) -> None:
    with pytest.raises(ZetarisError):
        sample(make_settings).run("DROP VIEW medtrace.gp", template_id="Q1", replay_key="MRN0000001")


def test_replay_index_covers_every_fixture_and_verifies_contents(tmp_path) -> None:
    index = _replay_index(REPLAY_DIR)
    assert len(index) == len(list(REPLAY_DIR.glob("Q1__P*.json")))
    assert index["MRN0000015"] == "P0015"
    # A fixture whose rows do not contain its own MRN is not indexed.
    (tmp_path / "Q1__P0042.json").write_text(json.dumps(
        {"headers": ["source", "row_id", "source_patient_id"], "data": [["emr", "EMR-9", "MRN0000007"]],
         "total": 1}))
    assert _replay_index(tmp_path) == {}


def test_load_lexicon_reads_q_ref_through_the_adapter(make_settings) -> None:
    lex = load_lexicon(sample(make_settings))
    assert lex.entries and lex.apinchs and lex.nicknames
    assert "warfarin" in lex.by_generic
