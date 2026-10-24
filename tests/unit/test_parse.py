"""`parse.py`, the one place in the codebase that casts.

Tested against the **committed fixtures**, which were verified byte-identical to
the live Zetaris views on 24 Oct (`register_sources.py --diff-fixtures`). So
these are not tests against a guess about the wire format -- they are tests
against the wire format.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from app.domain.packs.medtrace.parse import (
    build_lexicon,
    dicts_from_sql,
    normalise_text,
    parse_date,
    parse_int,
    rows_from_sql,
)

FIXTURES = pathlib.Path("tests/fixtures/medtrace")

pytestmark = pytest.mark.skipif(
    not (FIXTURES / "Q2__P0001.json").exists(), reason="run `make synth` first"
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# --------------------------------------------------------------------------- #
# Casting primitives
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("raw", "expected"), [
    ("1948-07-03", date(1948, 7, 3)),
    ("03/07/1948", date(1948, 7, 3)),       # day-first: every source here is Australian
    ("03-07-1948", date(1948, 7, 3)),
    ("", None),
    (None, None),
    ("3 July 1948", None),                   # unparseable -> None, never a guess
    ("1948-13-45", None),
])
def test_parse_date(raw: str | None, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_day_first_is_not_month_first() -> None:
    """`03/07/1948` is 3 July. Reading it month-first would silently shift most
    dates and quietly invent valid-looking wrong ones -- and a DOB is the field
    identity matching leans on hardest."""
    assert parse_date("03/07/1948") == date(1948, 7, 3)
    assert parse_date("13/07/1948") == date(1948, 7, 13)


@pytest.mark.parametrize(("raw", "expected"), [
    ("60", 60), ("0", 0), ("-5", -5),
    ("60.0", 60),            # a numeric column can come back with a decimal point
    ("6E1", 60),             # decimals may use exponent notation (REFERENCE_NOTES 1.2)
    ("", None), (None, None), ("many", None),
])
def test_parse_int(raw: str | None, expected: int | None) -> None:
    assert parse_int(raw) == expected


def test_normalise_text_is_for_keys_not_for_storage() -> None:
    assert normalise_text("  Atorvastatin   Calcium ") == "atorvastatin calcium"
    assert normalise_text("Coversyl Plus") == "coversyl plus"
    assert normalise_text(None) == ""
    # Accents are stripped for lookup only; stored names keep theirs.
    assert normalise_text("Zoë") == "zoe"


# --------------------------------------------------------------------------- #
# The envelope
# --------------------------------------------------------------------------- #


def test_dicts_from_sql_zips_headers_positionally() -> None:
    result = {"headers": ["a", "b"], "data": [["1", "2"], ["3", "4"]], "total": 2}
    assert dicts_from_sql(result) == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_an_empty_result_is_an_answer_not_an_error() -> None:
    """`data: []` with populated headers and `total: 0` is what a WHERE matching
    nothing returns. It must not raise -- "no rows" is a finding."""
    assert dicts_from_sql({"headers": ["a"], "data": [], "total": 0}) == []


def test_a_null_becomes_an_empty_string() -> None:
    """Live Zetaris returns JSON null for a column the source does not have, and
    `""` for a column it has whose value is blank. Both mean absent downstream,
    so they collapse here -- that is what lets the rest of the pack take `str`."""
    rows = dicts_from_sql({"headers": ["a", "b"], "data": [[None, "x"]], "total": 1})
    assert rows == [{"a": "", "b": "x"}]


def test_a_malformed_row_raises_rather_than_shifting_every_column() -> None:
    with pytest.raises(ValueError, match="malformed"):
        dicts_from_sql({"headers": ["a", "b", "c"], "data": [["1", "2"]], "total": 1})


def test_dicts_from_sql_handles_a_real_recorded_envelope() -> None:
    rows = dicts_from_sql(load("Q2__P0001.json"))
    assert rows
    assert all(isinstance(v, str) for row in rows for v in row.values())


# --------------------------------------------------------------------------- #
# SourceRow
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def q2_rows():
    return rows_from_sql(load("Q2__P0001.json"))


def test_rows_from_sql_produces_typed_rows(q2_rows) -> None:
    assert q2_rows
    assert {r.source for r in q2_rows} <= {"emr", "gp", "pharmacy", "patient"}
    for row in q2_rows:
        assert row.row_id and row.source_patient_id
        assert row.record_key == f"{row.source}:{row.source_patient_id}"


def test_both_the_parsed_and_the_raw_dob_are_kept(q2_rows) -> None:
    """The *difference* between them is evidence: a day/month swap, a one-digit
    typo and a genuinely different birthday all parse, and only the raw text
    tells them apart."""
    with_dob = [r for r in q2_rows if r.dob_raw]
    assert with_dob
    for row in with_dob:
        assert isinstance(row.dob_raw, str)
        if row.dob is not None:
            # dob_raw is whatever the source wrote; dob is the parse of it.
            assert parse_date(row.dob_raw) == row.dob


def test_gp_dates_are_day_first_and_emr_dates_are_iso(q2_rows) -> None:
    """The silos deliberately spell the same birthday differently (DATA_SPEC 2),
    and both must land on the same `dob`."""
    by_source = {}
    for row in q2_rows:
        if row.dob and row.source not in by_source:
            by_source[row.source] = row
    if "gp" in by_source:
        assert "/" in by_source["gp"].dob_raw
    if "emr" in by_source:
        assert "-" in by_source["emr"].dob_raw
    if {"gp", "emr"} <= set(by_source):
        assert by_source["gp"].dob == by_source["emr"].dob


def test_numeric_columns_are_cast(q2_rows) -> None:
    pharmacy = [r for r in q2_rows if r.source == "pharmacy"]
    assert pharmacy
    for row in pharmacy:
        assert row.qty is None or isinstance(row.qty, int)
        assert row.days_supply is None or isinstance(row.days_supply, int)
    assert any(r.qty for r in pharmacy), "expected at least one dispensing quantity"


def test_a_column_the_source_lacks_is_none_not_the_string_none(q2_rows) -> None:
    """If `""` reached the model as `"None"`, it would read as a present,
    non-matching value in identity scoring and in `evidence_state`."""
    pharmacy = [r for r in q2_rows if r.source == "pharmacy"]
    assert pharmacy
    assert all(r.name_family is None for r in pharmacy)
    # The literal string "None", not a genuine None -- `str(None) == "None"`, so
    # comparing the stringified value would flag every correctly-absent field.
    assert not any(v == "None" for r in q2_rows for v in r.model_dump().values())


def test_a_row_with_no_medicine_is_kept(q2_rows) -> None:
    """DATA_SPEC 2's absence rule: "known to a source with no meds" is one row
    with the medication fields null, and it is the difference between
    ABSENT_IN_SCOPE and UNKNOWN."""
    assert all(isinstance(r.has_med, bool) for r in q2_rows)


def test_an_unknown_source_is_skipped_not_fatal() -> None:
    result = {"headers": ["source", "row_id", "source_patient_id"],
              "data": [["emr", "EMR-1", "MRN1"], ["mystery", "X-1", "X"]], "total": 2}
    rows = rows_from_sql(result)
    assert [r.source for r in rows] == ["emr"]


def test_an_unexpected_column_fails_loudly() -> None:
    """`SourceRow` forbids extras, so a view that grew a column fails here
    instead of being ignored for the rest of the run."""
    result = {"headers": ["source", "row_id", "source_patient_id", "surprise"],
              "data": [["emr", "EMR-1", "MRN1", "x"]], "total": 1}
    with pytest.raises(Exception):
        rows_from_sql(result)


# --------------------------------------------------------------------------- #
# Lexicon
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def lexicon():
    return build_lexicon(
        dicts_from_sql(load("Q_REF__lexicon.json")),
        dicts_from_sql(load("Q_REF__apinchs.json")),
        dicts_from_sql(load("Q_REF__nicknames.json")),
    )


def test_the_lexicon_indexes_are_populated(lexicon) -> None:
    assert len(lexicon.entries) > 100
    assert lexicon.by_pbs_code and lexicon.by_brand and lexicon.by_generic
    assert lexicon.by_amt_code


def test_brand_and_generic_lookups_are_casefolded(lexicon) -> None:
    assert "lipitor" in lexicon.by_brand
    assert "atorvastatin" in lexicon.by_generic
    assert lexicon.by_brand["lipitor"].generic == "atorvastatin"


def test_a_real_pbs_code_resolves(lexicon) -> None:
    """The `code` resolution tier is the only one that is a fact rather than a
    guess, so it has to work."""
    real = [e for e in lexicon.entries if e.pbs_code and not e.pbs_code.startswith("SYN-")]
    assert len(real) > 150, "expected most rows to carry a real PBS code"
    assert lexicon.by_pbs_code[real[0].pbs_code] is real[0]


def test_apinchs_prefixes_are_longest_first(lexicon) -> None:
    """`A10AB` (fast-acting insulin) must beat `A10` before it, or every insulin
    gets the broader class and the specific rule never fires."""
    lengths = [len(prefix) for prefix, _klass in lexicon.apinchs]
    assert lengths == sorted(lengths, reverse=True)
    assert len(lexicon.apinchs) == 42


def test_a_combination_decomposes_into_paired_ingredients(lexicon) -> None:
    """`detect.duplication` intersects ingredient sets, and the dose comparison
    needs the per-ingredient milligrams."""
    combos = [e for e in lexicon.entries if e.is_combination]
    assert combos
    coversyl = next((e for e in combos if e.generic == "perindopril/indapamide"), None)
    assert coversyl is not None
    names = [name for name, _mg in coversyl.ingredients]
    assert names == ["perindopril", "indapamide"]
    assert [mg for _n, mg in coversyl.ingredients] == [5.0, 1.25]


def test_mispaired_strengths_are_dropped_not_guessed() -> None:
    """Attaching the wrong milligrams to the wrong drug is worse than attaching
    none, because the dose comparison would then be confidently wrong."""
    lex = build_lexicon(
        [{"generic": "a/b/c", "ingredients": "a;b;c", "strength": "5/10 mg",
          "is_combination": "true"}], [], [])
    assert lex.entries[0].ingredients == [("a", None), ("b", None), ("c", None)]


# --------------------------------------------------------------------------- #
# Nicknames: the non-transitivity that protects false-merge rate
# --------------------------------------------------------------------------- #


def test_a_nickname_family_is_closed_within_one_canonical(lexicon) -> None:
    margaret = lexicon.nicknames["margaret"]
    assert {"margaret", "peggy", "peg", "maggie", "marg"} <= margaret
    # Symmetric: every member sees the whole family.
    assert "margaret" in lexicon.nicknames["peggy"]
    assert "maggie" in lexicon.nicknames["peggy"]


def test_an_ambiguous_variant_does_not_bridge_two_canonicals(lexicon) -> None:
    """`Chris` is a variant of both Christine and Christopher. Closing through it
    would make **Christine equivalent to Christopher** -- a false merge across
    two people of different sexes, and false-merge rate has a target of zero."""
    assert "christine" in lexicon.nicknames["chris"]
    assert "christopher" in lexicon.nicknames["chris"]
    assert "christopher" not in lexicon.nicknames["christine"]
    assert "christine" not in lexicon.nicknames["christopher"]


@pytest.mark.parametrize(("variant", "a", "b"), [
    ("chris", "christine", "christopher"),
    ("pat", "patricia", "patrick"),
    ("jan", "janet", "janice"),
    ("harry", "harold", "henry"),
    ("terry", "theresa", "terence"),
])
def test_no_ambiguous_variant_merges_its_two_families(lexicon, variant, a, b) -> None:
    assert {a, b} <= lexicon.nicknames[variant]
    assert b not in lexicon.nicknames[a]
    assert a not in lexicon.nicknames[b]
