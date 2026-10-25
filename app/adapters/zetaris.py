"""Zetaris REST adapter -- the data layer. Agents get facts by sending SQL here.

CLAUDE.md rule 1: every fact an agent uses comes back through this module.

The call shape (`REFERENCE_NOTES` 1.1, confirmed live):

    POST {ZETARIS_REST_URL}/sql-editor/sqls/run
    headers: Authorization: Bearer <key>, X-Org-ID, X-Request-ID (uuid4)
    body:    {"queryId": uuid4, "sql": "<one statement, no trailing ;>",
              "source": "SqlEditor", "limit": n}

and the envelope it returns, `{headers, data, total, timeUsed}`, is passed on
**untouched** as a `SqlResult`: every present value stays a string and a SQL
NULL stays `None`. Casting is `parse.py`'s job and nobody else's.

What this module adds on top of the call:
  - A read-only guard: SELECT / SHOW / DESCRIBE / WITH only, one statement.
  - A per-run query budget (`RunQueries`), raising `QueryBudgetExceeded` at
    `queries.MAX_ZETARIS_QUERIES_PER_RUN`, and a record of every query
    (template id, SQL, ms, rows) for the trace.
  - Bounded retries on connection errors and 5xx; never on 4xx or a timeout.
  - `SAMPLE_MODE` replay of the recorded envelopes in `tests/fixtures/medtrace/`,
    which Arpon diffed against live Zetaris (identical). That is cached *data*,
    not model output, so it is what the README means by "real work on cached data".
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.config import REPO_ROOT, Settings, get_settings
from app.domain.packs.medtrace import queries
from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql
from app.domain.packs.medtrace.types import Lexicon, SqlResult

__all__ = [
    "REPLAY_DIR",
    "QueryBudgetExceeded",
    "QueryRecord",
    "ReplayMiss",
    "RunQueries",
    "ZetarisClient",
    "ZetarisError",
    "check_read_only",
    "load_lexicon",
]

#: The replay set. The Docker image copies this directory (Dockerfile).
REPLAY_DIR = REPO_ROOT / "tests" / "fixtures" / "medtrace"
_RETRYABLE_STATUS = {500, 502, 503, 504}
_READ_ONLY = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|WITH)\b", re.IGNORECASE)
_WRITE_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CACHE|UNCACHE|REFRESH)\b",
    re.IGNORECASE,
)
_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'")


class ZetarisError(RuntimeError):
    """Typed failure from the data layer, so agents can recover deliberately."""

    def __init__(self, message: str, *, status: int | None = None, recoverable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.recoverable = recoverable


class QueryBudgetExceeded(ZetarisError):
    """The run has used its `MAX_ZETARIS_QUERIES_PER_RUN`. The orchestrator returns `partial`."""

    def __init__(self, used: int, budget: int) -> None:
        super().__init__(f"query budget exhausted: {used} of {budget} used", recoverable=False)
        self.used = used
        self.budget = budget


class ReplayMiss(ZetarisError):
    """SAMPLE_MODE has no recorded envelope for this query. Never answered by guessing."""

    def __init__(self, name: str) -> None:
        super().__init__(f"SAMPLE_MODE: no recorded result {name}.json in {REPLAY_DIR}", recoverable=False)
        self.name = name


def _strip_literals(sql: str) -> str:
    """The SQL with its string literals blanked, so a quoted ';' or 'DROP' is not mistaken for code."""
    return _STRING_LITERAL.sub("''", sql)


def check_read_only(sql: str) -> str:
    """Refuse anything but one read-only statement. Returns the SQL unchanged."""
    if not _READ_ONLY.match(sql):
        raise ZetarisError("only SELECT, SHOW, DESCRIBE or WITH may be sent", recoverable=False)
    code = _strip_literals(sql)
    if ";" in code:
        raise ZetarisError("one statement per call, and no trailing semicolon (REFERENCE_NOTES 1.2)")
    if _WRITE_WORDS.search(code):
        raise ZetarisError("statement contains a write keyword; agents are read-only")
    return sql


@dataclass
class QueryRecord:
    """One query, as the trace shows it. `error` is set instead of `rows` on failure."""

    template_id: str
    sql: str
    ms: int
    rows: int | None
    query_id: str
    replayed: bool = False
    error: str | None = None

    def trace_fields(self) -> dict[str, Any]:
        return {"sql": self.sql, "row_count": self.rows, "latency_ms": self.ms, "error": self.error,
                "sql_template_id": self.template_id, "query_id": self.query_id, "replayed": self.replayed}


@lru_cache(maxsize=4)
def _replay_index(replay_dir: Path) -> dict[str, str]:
    """EMR MRN -> fixture key ("MRN0000015" -> "P0015"), from the fixtures alone.

    The generator numbers MRNs and fixture keys alike, but the convention is not
    trusted blindly: a Q1 fixture is indexed only if it really contains an EMR row
    for that MRN. No ground truth is read -- it is gitignored and absent in Docker.
    """
    index: dict[str, str] = {}
    for path in sorted(replay_dir.glob("Q1__P*.json")):
        key = path.stem.split("__", 1)[1]
        mrn = f"MRN{int(key[1:]):07d}"
        doc = json.loads(path.read_text())
        ids = {dict(zip(doc["headers"], row)).get("source_patient_id")
               for row in doc["data"] if row and row[0] == "emr"}
        if mrn in ids:
            index[mrn] = key
    return index


class ZetarisClient:
    """REST client for Lightning SQL. One instance per process; one `RunQueries` per run.

    Pass `transport` (an `httpx.MockTransport`) in tests. `sleep` is injectable so
    retry backoff is not waited out.
    """

    def __init__(self, settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None,
                 replay_dir: Path = REPLAY_DIR, sleep: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings or get_settings()
        self._transport = transport
        self._replay_dir = replay_dir
        self._sleep = sleep

    @property
    def sample_mode(self) -> bool:
        return self.settings.sample_mode

    def run(self, sql: str, *, template_id: str, replay_key: str | None = None,
            limit: int = queries.DEFAULT_ROW_LIMIT) -> tuple[SqlResult, QueryRecord]:
        """Send one read-only statement. Returns the raw envelope and its trace record.

        `replay_key` names the recorded result in SAMPLE_MODE: an EMR MRN for the
        per-patient templates (Q1-Q3), the fixture suffix otherwise ("admissions",
        "lexicon"). It is ignored live.
        """
        check_read_only(sql)
        query_id = str(uuid.uuid4())
        start = time.monotonic()
        if self.sample_mode:
            result = self._replay(template_id, replay_key)
            replayed = True
        else:
            result = self._post(sql, query_id, limit)
            replayed = False
        record = QueryRecord(template_id=template_id, sql=sql, ms=int((time.monotonic() - start) * 1000),
                             rows=len(result["data"]), query_id=query_id, replayed=replayed)
        if not replayed and record.rows is not None and record.rows >= limit:
            raise ZetarisError(f"{template_id}: {record.rows} rows hit the limit of {limit}; the result may be "
                               "truncated, so it is refused rather than used", recoverable=False)
        return result, record

    # -- live -----------------------------------------------------------------

    def _post(self, sql: str, query_id: str, limit: int) -> SqlResult:
        key = self.settings.require_zetaris_key() if self.settings.has_zetaris_key else None
        if key is None:
            raise ZetarisError("ZETARIS_API_KEY is unset or a placeholder", recoverable=False)
        url = self.settings.zetaris_rest_url.rstrip("/") + "/sql-editor/sqls/run"
        body = {"queryId": query_id, "sql": sql, "source": "SqlEditor", "limit": limit}
        attempts = 1 + self.settings.max_retries
        last: ZetarisError | None = None
        for attempt in range(attempts):
            if attempt:
                self._sleep(min(2.0 * attempt, 5.0))
            headers = {"Authorization": f"Bearer {key}", "X-Org-ID": str(self.settings.zetaris_org_id),
                       "X-Request-ID": str(uuid.uuid4()), "Content-Type": "application/json"}
            try:
                with httpx.Client(timeout=self.settings.zetaris_timeout_s, transport=self._transport) as client:
                    response = client.post(url, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise ZetarisError(f"no answer within {self.settings.zetaris_timeout_s:.0f}s", recoverable=True) from exc
            except httpx.TransportError as exc:
                last = ZetarisError(f"cannot reach Zetaris at {self.settings.zetaris_rest_url} "
                                    f"({type(exc).__name__})", recoverable=True)
                continue
            if response.status_code in _RETRYABLE_STATUS:
                last = ZetarisError(f"HTTP {response.status_code}: {_message(response)}",
                                    status=response.status_code, recoverable=True)
                continue
            if response.status_code == 401:
                raise ZetarisError("401: ZETARIS_API_KEY rejected; create a new one in the Zetaris UI",
                                   status=401)
            if response.status_code != 200:
                raise ZetarisError(f"HTTP {response.status_code}: {_message(response)}", status=response.status_code)
            return _envelope(response)
        assert last is not None
        raise last

    # -- replay ---------------------------------------------------------------

    def _replay(self, template_id: str, replay_key: str | None) -> SqlResult:
        if replay_key is None:
            raise ReplayMiss(f"{template_id}__<no key>")
        suffix = _replay_index(self._replay_dir).get(replay_key, replay_key)
        name = f"{template_id}__{suffix}"
        path = self._replay_dir / f"{name}.json"
        if not path.is_file():
            raise ReplayMiss(name)
        doc = _validate(json.loads(path.read_text()), name)
        if template_id == "Q3":
            doc = self._with_recorded_q2(doc, suffix)
        return doc

    def _with_recorded_q2(self, q3: SqlResult, suffix: str) -> SqlResult:
        """Q3 replay = the patient's recorded Q3 rows plus their recorded Q2 rows.

        The committed Q3 fixtures were recorded for the ground truth's planted rows,
        not for whatever a run cites; every row a finding cites came from Q2. Both
        envelopes were recorded from live Zetaris with the harmonised columns, so
        the union is still recorded data, and the Evaluator still keeps only the
        rows it asked for. Live mode always runs the real Q3.
        """
        q2_path = self._replay_dir / f"Q2__{suffix}.json"
        if not q2_path.is_file():
            return q3
        q2 = _validate(json.loads(q2_path.read_text()), f"Q2__{suffix}")
        headers = list(q3["headers"])
        index = {h: i for i, h in enumerate(q2["headers"])}
        if not all(h in index for h in headers):
            return q3
        rid = headers.index("row_id") if "row_id" in headers else None
        seen = {row[rid] for row in q3["data"]} if rid is not None else set()
        extra = [[row[index[h]] for h in headers] for row in q2["data"]
                 if rid is None or row[index["row_id"]] not in seen]
        data = [*q3["data"], *extra]
        return {"headers": headers, "data": data, "total": len(data)}  # type: ignore[return-value]


class RunQueries:
    """One run's view of Zetaris: the budget, and the record of every query sent."""

    def __init__(self, client: ZetarisClient, budget: int = queries.MAX_ZETARIS_QUERIES_PER_RUN) -> None:
        self.client = client
        self.budget = budget
        self.records: list[QueryRecord] = []

    @property
    def used(self) -> int:
        return len(self.records)

    @property
    def zetaris_ms(self) -> int:
        return sum(r.ms for r in self.records)

    def run(self, sql: str, *, template_id: str, replay_key: str | None = None,
            limit: int = queries.DEFAULT_ROW_LIMIT) -> tuple[SqlResult, QueryRecord]:
        if self.used >= self.budget:
            raise QueryBudgetExceeded(self.used, self.budget)
        try:
            result, record = self.client.run(sql, template_id=template_id, replay_key=replay_key, limit=limit)
        except ZetarisError as exc:
            # A failed query still spent budget and still belongs in the trace.
            self.records.append(QueryRecord(template_id=template_id, sql=sql, ms=0, rows=None,
                                            query_id="-", replayed=self.client.sample_mode, error=str(exc)))
            raise
        self.records.append(record)
        return result, record


def load_lexicon(client: ZetarisClient) -> Lexicon:
    """Q_REF at startup: the three reference views, read through Zetaris, never from files.

    Not counted against any run's budget -- it is paid once per process.
    """
    results = [client.run(queries.q_reference(name), template_id="Q_REF", replay_key=name)[0]
               for name in ("lexicon", "apinchs", "nicknames")]
    return build_lexicon(*(dicts_from_sql(r) for r in results))


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            if body.get(key):
                return str(body[key])[:200]
    return str(body)[:200]


def _validate(doc: Any, where: str) -> SqlResult:
    if not (isinstance(doc, dict) and isinstance(doc.get("headers"), list) and isinstance(doc.get("data"), list)):
        raise ZetarisError(f"{where}: not a Zetaris envelope (headers + data)")
    width = len(doc["headers"])
    if any(not isinstance(row, list) or len(row) != width for row in doc["data"]):
        raise ZetarisError(f"{where}: a row's width does not match headers")
    doc.setdefault("total", len(doc["data"]))
    return doc  # type: ignore[return-value]


def _envelope(response: httpx.Response) -> SqlResult:
    try:
        doc = response.json()
    except ValueError as exc:
        raise ZetarisError("response body is not JSON") from exc
    return _validate(doc, "Zetaris response")
