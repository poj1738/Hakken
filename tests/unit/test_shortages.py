"""Q4 `q_shortages` -- the matching rules, executed rather than eyeballed.

The generated SQL is run in SQLite against TGA-shaped rows, because the rules
are the clinical part: a Caduet shortage is not an amlodipine shortage, and a
resolved report is not a current one. SQLite and Lightning SQL agree on
`CASE`, `LIKE`, `lower` and `IN`, which is all the template uses. The live
syntax check against Zetaris is separate (`docs/DECISIONS.md`, 25 Oct).

The rows are hand-written in the export's shape -- no TGA data is committed.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.domain.packs.medtrace.queries import (
    TGA_COLUMNS,
    TGA_VIEW,
    QueryBuildError,
    q_shortages,
)

ROWS = [
    # (artg_id, ingredients, status)
    ("1", "amlodipine besilate", "Current"),
    ("2", "amlodipine besilate|atorvastatin calcium trihydrate", "Current"),
    ("3", "atorvastatin calcium trihydrate", "Resolved"),
    ("4", "Perindopril Arginine|amlodipine besilate", "Anticipated"),
    ("5", "amlodipine besilate|indapamide hemihydrate|perindopril arginine", "Current"),
    ("6", "metformin hydrochloride", "Discontinued"),
    ("7", "warfarin sodium", "Current"),
]


def run(generics: list[str]) -> list[tuple[str, str]]:
    db = sqlite3.connect(":memory:")
    db.execute(f"CREATE TABLE tga ({', '.join(TGA_COLUMNS)})")
    for artg, ingredients, status in ROWS:
        values = {c: "" for c in TGA_COLUMNS} | {"artg_id": artg, "ingredients": ingredients,
                                                 "status": status}
        db.execute(f"INSERT INTO tga VALUES ({', '.join('?' for _ in TGA_COLUMNS)})",
                   [values[c] for c in TGA_COLUMNS])
    sql = q_shortages(generics).replace(TGA_VIEW, "tga")
    return sorted((r[0], r[1]) for r in db.execute(sql).fetchall())


def test_a_single_agent_matches_its_salt() -> None:
    assert run(["amlodipine"]) == [("amlodipine", "1")]


def test_a_combination_shortage_is_not_a_single_agent_shortage() -> None:
    """Caduet (row 2) and Coveram (row 4) both contain amlodipine; neither says
    plain amlodipine is short."""
    assert ("amlodipine", "2") not in run(["amlodipine"])
    assert ("amlodipine", "4") not in run(["amlodipine"])


def test_a_combination_matches_exactly_its_ingredients_in_any_order() -> None:
    assert run(["perindopril/amlodipine"]) == [("perindopril/amlodipine", "4")]
    assert run(["amlodipine/atorvastatin"]) == [("amlodipine/atorvastatin", "2")]


def test_a_three_ingredient_product_does_not_match_a_two_ingredient_one() -> None:
    assert ("perindopril/amlodipine", "5") not in run(["perindopril/amlodipine"])
    assert run(["perindopril/indapamide/amlodipine"]) == [("perindopril/indapamide/amlodipine", "5")]


def test_resolved_and_discontinued_reports_are_not_shortages() -> None:
    assert run(["atorvastatin", "metformin"]) == []


def test_several_generics_each_get_their_own_rows() -> None:
    assert run(["warfarin", "amlodipine", "Warfarin "]) == [("amlodipine", "1"), ("warfarin", "7")]


def test_asking_about_nothing_is_refused() -> None:
    with pytest.raises(QueryBuildError):
        q_shortages(["", "  "])


def test_one_statement_and_escaped() -> None:
    sql = q_shortages(["o'brien-ase"])
    assert ";" not in sql and "\\'" in sql
