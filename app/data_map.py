"""Live data map: one ordered catalogue of read-only Zetaris queries.

The screen asks for each entry on its own, through ``ZetarisClient.run``.
Nothing here stores a row count, a schema, or a column list. Those come back
in the envelope. ``RunQueries`` is the patient-run budget (8); the map does
not use it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.adapters.zetaris import ZetarisClient

__all__ = [
    "CATALOGUE",
    "DataMapCatalogueResponse",
    "DataMapQueryResult",
    "MapQuery",
    "catalogue_response",
    "execute_query",
]


class MapQuery(BaseModel):
    """One catalogue entry. ``node`` is the diagram node this query lights."""

    model_config = ConfigDict(frozen=True)

    id: str
    template_id: str
    replay_key: str
    sql: str
    label: str
    node: str


#: Order is the order the screen runs them: the fast counts, then the union,
#: then the three semantic-layer scans, one at a time.
CATALOGUE: tuple[MapQuery, ...] = (
    MapQuery(
        id="emr",
        template_id="MAP_COUNT",
        replay_key="emr",
        sql="SELECT COUNT(*) FROM medtrace.emr",
        label="Hospital EMR",
        node="emr",
    ),
    MapQuery(
        id="gp",
        template_id="MAP_COUNT",
        replay_key="gp",
        sql="SELECT COUNT(*) FROM medtrace.gp",
        label="GP",
        node="gp",
    ),
    MapQuery(
        id="pharmacy",
        template_id="MAP_COUNT",
        replay_key="pharmacy",
        sql="SELECT COUNT(*) FROM medtrace.pharmacy",
        label="Pharmacy",
        node="pharmacy",
    ),
    MapQuery(
        id="patient",
        template_id="MAP_COUNT",
        replay_key="patient",
        sql="SELECT COUNT(*) FROM medtrace.patient_report",
        label="Patient interview",
        node="patient",
    ),
    MapQuery(
        id="lexicon",
        template_id="MAP_COUNT",
        replay_key="lexicon",
        sql="SELECT COUNT(*) FROM medtrace.med_lexicon",
        label="PBS medicines",
        node="lexicon",
    ),
    MapQuery(
        id="apinchs",
        template_id="MAP_COUNT",
        replay_key="apinchs",
        sql="SELECT COUNT(*) FROM medtrace.apinchs",
        label="High-risk classes (ACSQHC)",
        node="apinchs",
    ),
    MapQuery(
        id="tga",
        template_id="MAP_COUNT",
        replay_key="tga",
        sql="SELECT COUNT(*) FROM medtrace.tga_shortages",
        label="TGA shortages",
        node="tga",
    ),
    MapQuery(
        id="all_sources",
        template_id="MAP_COUNT",
        replay_key="all_sources",
        sql="SELECT COUNT(*) FROM medtrace.all_sources",
        label="Four systems combined",
        node="merge",
    ),
    MapQuery(
        id="rows",
        template_id="MAP_USL",
        replay_key="rows",
        sql="SELECT COUNT(*) FROM lightning.metastore.medtrace.medtrace_usl.medication_statement",
        label="Zetaris · semantic layer (medtrace_usl)",
        node="usl",
    ),
    MapQuery(
        id="high_risk",
        template_id="MAP_USL",
        replay_key="high_risk",
        sql=(
            "SELECT source_system, COUNT(*) FROM "
            "lightning.metastore.medtrace.medtrace_usl.medication_statement "
            "WHERE high_risk_class IS NOT NULL GROUP BY source_system"
        ),
        label="High-risk medicine lines by source",
        node="high_risk",
    ),
    MapQuery(
        id="dq",
        template_id="MAP_USL",
        replay_key="dq",
        sql=(
            "SELECT COUNT(*) FROM "
            "lightning.metastore.medtrace.medtrace_usl.medication_statement "
            "WHERE NOT COALESCE(strength_listed, true)"
        ),
        label="Data quality",
        node="dq",
    ),
)

_BY_ID = {query.id: query for query in CATALOGUE}


class DataMapCatalogueResponse(BaseModel):
    """The catalogue only. This response is not the result of any SQL."""

    queries: list[MapQuery]


class DataMapQueryResult(BaseModel):
    """One query, as the adapter returned it. ``error`` is null on success."""

    id: str
    label: str
    sql: str
    headers: list[str]
    data: list[list[Any]]
    row_count: int
    latency_ms: int
    executed_at: str
    replayed: bool
    error: str | None = None


def catalogue_response() -> DataMapCatalogueResponse:
    return DataMapCatalogueResponse(queries=list(CATALOGUE))


def execute_query(client: ZetarisClient, query_id: str) -> DataMapQueryResult:
    """Run exactly one catalogue query. Unknown ids raise ``KeyError``."""
    query = _BY_ID.get(query_id)
    if query is None:
        raise KeyError(query_id)
    result, record = client.run(query.sql, template_id=query.template_id, replay_key=query.replay_key)
    rows = record.rows if record.rows is not None else len(result["data"])
    return DataMapQueryResult(
        id=query.id,
        label=query.label,
        sql=record.sql,
        headers=list(result["headers"]),
        data=list(result["data"]),
        row_count=rows,
        latency_ms=record.ms,
        executed_at=datetime.now(timezone.utc).isoformat(),
        replayed=record.replayed,
        error=record.error,
    )
