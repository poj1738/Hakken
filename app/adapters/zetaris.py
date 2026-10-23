"""Zetaris REST adapter -- the data layer. Agents get facts by sending SQL here.

PHASE 2 STUB -- but no longer blocked: the response envelope was observed on a
live instance on 2026-10-23 and recorded in tests/fixtures/zetaris/.

    {"headers": ["col", ...],       # column names, positional per row
     "data":    [["v", ...], ...],  # rows as positional lists
     "total":   <row count>,
     "timeUsed": <ms>}

Three confirmed behaviours the parser must honour:
  1. Zip `headers` with each row in `data` to get dicts.
  2. **Every value is a string** ("1", "2.5", "true"). Cast before comparing.
  3. An empty result is `data: []` with `total: 0` and populated `headers` -- not
     an error. SHOW and SELECT share this envelope, so one parser covers both.

Call shape, confirmed from the reference client and live:
    POST {ZETARIS_REST_URL}/sql-editor/sqls/run
    headers: Authorization: Bearer <key>, X-Org-ID, X-Request-ID (uuid4),
             Content-Type: application/json
    body:    {"queryId": uuid4, "sql": "<one statement, no trailing ;>",
              "source": "SqlEditor", "limit": n}
"""

from __future__ import annotations


class ZetarisError(RuntimeError):
    """Typed failure from the data layer, so agents can recover deliberately."""

    def __init__(self, message: str, *, status: int | None = None, recoverable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.recoverable = recoverable


class ZetarisClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "ZetarisClient is a Phase 2 stub. It must not be written until one real "
            "200 response has been inspected -- see the module docstring."
        )
