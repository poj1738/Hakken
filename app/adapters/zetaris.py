"""Zetaris REST adapter -- the data layer. Agents get facts by sending SQL here.

PHASE 2 STUB, deliberately not guessed. Two things must be learned from a live
instance before this can be written honestly:

  1. Where column names live in a 200 response. The reference client
     (.refs/zetaris/scripts/zetaris_sql.py) keeps only `response["data"]`, which
     is a list of positional lists, and discards everything else. We inspect one
     real response and write the parser against it, with a recorded fixture.
  2. Whether SHOW/DESCRIBE return the same envelope as SELECT.

Call shape, already confirmed from the reference client:
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
