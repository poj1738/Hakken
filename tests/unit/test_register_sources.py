"""`scripts/register_sources.py` SQL generation. Builds statements, sends nothing.

Every statement here will be executed against a live Zetaris with `--apply`, so
a malformed one costs a manual teardown -- and there is no SQL path to drop a
SchemaStore container (`REFERENCE_NOTES` 1.3). These tests check the statements
before a human ever sees them.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from app.domain.packs.medtrace.queries import (
    ALL_SOURCES_VIEW,
    CONTAINER,
    HARMONISED_COLUMNS,
    SOURCE_VIEWS,
)

SPEC = importlib.util.spec_from_file_location(
    "register_sources", pathlib.Path("scripts/register_sources.py")
)
assert SPEC and SPEC.loader
reg = importlib.util.module_from_spec(SPEC)
sys.modules["register_sources"] = reg
SPEC.loader.exec_module(reg)


@pytest.fixture(scope="module")
def statements() -> list[tuple[str, str]]:
    return reg.plan_statements()


def test_every_statement_is_one_statement_with_no_semicolon(statements) -> None:
    """The REST endpoint accepts exactly one statement per call."""
    assert statements
    for label, sql in statements:
        assert ";" not in sql, label
        assert sql == " ".join(sql.split()), label
        assert sql.split()[0] in {"CREATE", "CACHE"}, label


def test_the_rest_tables_point_at_the_zetaris_facing_url(statements) -> None:
    """`DATASVC_PUBLIC_URL` goes in verbatim and must resolve from inside the
    Zetaris containers. A compose-only hostname registers fine and then fails
    every query, which is why config rejects one."""
    from app.config import get_settings

    public = get_settings().datasvc_public_url.rstrip("/")
    endpoints = [sql for _l, sql in statements if "REST TABLE" in sql]
    assert len(endpoints) == 7, "4 silos + 3 reference tables"
    for sql in endpoints:
        assert f'endpoint "{public}/' in sql
        assert "datasvc:8100" not in sql


def test_every_silo_view_selects_all_harmonised_columns_in_order(statements) -> None:
    """`headers` is positional against every row, so a reordered or missing
    column silently shifts the whole result."""
    for source in ("emr", "gp", "pharmacy", "patient"):
        select = reg.harmonised_select(source)
        aliases = [part.rsplit(" AS ", 1)[1].strip() for part in select.split(", ")]
        assert aliases == list(HARMONISED_COLUMNS), source


def test_columns_a_source_does_not_have_are_typed_nulls(statements) -> None:
    """A null must arrive as a real NULL, not the string "None" -- otherwise it
    reads as a present, non-matching value in identity scoring."""
    select = reg.harmonised_select("patient")
    assert "CAST(NULL AS STRING) AS name_family" in select
    assert "CAST(NULL AS STRING) AS qty" in select
    assert "'None'" not in select


def test_literal_columns_are_quoted_with_the_right_escaping(statements) -> None:
    assert "'emr' AS source" in reg.harmonised_select("emr")
    assert "'dispense' AS record_kind" in reg.harmonised_select("pharmacy")


def test_all_sources_references_each_view_exactly_once(statements) -> None:
    """A second reference to a union-of-explode view fails outright with
    MISSING_ATTRIBUTES, confirmed live on 24 Oct."""
    sql = next(s for _l, s in statements if ALL_SOURCES_VIEW.split(".", 1)[1] in s
               and "UNION ALL" in s)
    for view in SOURCE_VIEWS.values():
        assert sql.count(view) == 1, view
    assert sql.count("UNION ALL") == 3


def test_the_union_selects_the_harmonised_columns(statements) -> None:
    sql = next(s for _l, s in statements if "UNION ALL" in s)
    assert sql.count(", ".join(HARMONISED_COLUMNS)) == 4


def test_every_raw_table_is_cached(statements) -> None:
    """A REST table may re-call its source on every query (`REFERENCE_NOTES` 1.3)."""
    cached = {sql.split()[-1] for _l, sql in statements if sql.startswith("CACHE TABLE")}
    assert cached == {"MT_EMR.emr_raw", "MT_GP.gp_raw", "MT_PHARMACY.pharmacy_raw",
                      "MT_PATIENT.patient_raw", "MT_REF.lexicon_raw",
                      "MT_REF.apinchs_raw", "MT_REF.nicknames_raw"}


def test_the_container_is_created_once_and_first(statements) -> None:
    """`CREATE SCHEMASTORE CONTAINER` has no `IF NOT EXISTS`, so a re-run fails
    on the duplicate -- hence `--skip-exists`."""
    containers = [i for i, (_l, sql) in enumerate(statements)
                  if sql.startswith("CREATE SCHEMASTORE CONTAINER")]
    assert containers == [0]
    assert statements[0][1] == f"CREATE SCHEMASTORE CONTAINER {CONTAINER}"


def test_databases_are_created_before_they_are_referenced(statements) -> None:
    """`CREATE LIGHTNING DATABASE <db>` must exist before any `FROM <db>`."""
    created: set[str] = set()
    for label, sql in statements:
        if sql.startswith("CREATE LIGHTNING DATABASE"):
            created.add(sql.split()[3])
        elif "FROM MT_" in sql or sql.startswith("CACHE TABLE"):
            referenced = [tok for tok in sql.replace("(", " ").split() if tok.startswith("MT_")]
            for token in referenced:
                assert token.split(".")[0] in created, f"{label} uses {token} before it exists"


def test_views_are_created_after_their_table(statements) -> None:
    order = [label for label, _sql in statements]
    for db, table, _p, view, _s in reg.SILOS:
        assert order.index(f"{db}.{table} REST table") < order.index(f"{view} view")


def test_all_sources_is_created_last(statements) -> None:
    assert statements[-1][0] == f"{ALL_SOURCES_VIEW} view"


def test_dry_run_is_the_default() -> None:
    """Applying by accident would create 28 objects in a shared Zetaris."""
    source = pathlib.Path("scripts/register_sources.py").read_text()
    assert '"--apply", action="store_true"' in source
    assert "if not args.apply:" in source


def test_expected_counts_come_from_the_served_files(statements) -> None:
    """Verification compares Zetaris against the same files datasvc serves; a
    successful CREATE does not prove a usable table (`REFERENCE_NOTES` 1.4)."""
    counts = reg.datasvc_counts()
    assert set(SOURCE_VIEWS.values()) <= set(counts)
    assert ALL_SOURCES_VIEW in counts
    if all(counts[v] >= 0 for v in SOURCE_VIEWS.values()):
        assert counts[ALL_SOURCES_VIEW] == sum(counts[v] for v in SOURCE_VIEWS.values())
