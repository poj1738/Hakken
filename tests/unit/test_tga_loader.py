"""`scripts/load_tga_shortages.py`, tested against a fixture, not the real export.

The real file is Monday's optional work and is not in the repo, so this builds a
synthetic export carrying every stated format quirk. Each quirk below is one a
plain `csv.DictReader` gets wrong, which is the reason the parser exists at all.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

SPEC = importlib.util.spec_from_file_location(
    "load_tga_shortages", pathlib.Path("scripts/load_tga_shortages.py")
)
assert SPEC and SPEC.loader
tga = importlib.util.module_from_spec(SPEC)
sys.modules["load_tga_shortages"] = tga
SPEC.loader.exec_module(tga)


#: A 10-line preamble above the header, 16 columns including `Phone`,
#: `~`-separated ingredients in *both* orders, day-first dates, all four
#: statuses, and a BOM (added by the caller).
FIXTURE = """Medicine Shortage Reports Database
Therapeutic Goods Administration
Report generated: 24/10/2026
This export is provided for information only.
The database is not a complete record of all shortages.

Notes:
Dates are shown in DD/MM/YYYY format.
Ingredients are separated by a tilde.

ARTG ID,Medicine name,Sponsor,Active ingredients,Quantity of active ingredients,Dosage form,Status,Shortage start date,Expected resolution date,Availability,Reason,Phone,Email,Notified date,Shortage type,Last updated
123456,Marevan 5mg tablet,Aspen Pharmacare,warfarin sodium,5 mg,Tablet,Current,01/09/2026,15/12/2026,Limited availability,Manufacturing,02 1234 5678,x@example.com,01/09/2026,Shortage,20/10/2026
223456,Coversyl Plus 5/1.25,Servier,indapamide~perindopril arginine,1.25 mg~5 mg,Tablet,Anticipated,01/11/2026,,Unavailable,Commercial,02 1234 5678,x@example.com,15/10/2026,Shortage,20/10/2026
323456,Eliquis 5mg,Bristol-Myers,apixaban,5 mg,Tablet,Resolved,01/02/2026,01/06/2026,Available,Manufacturing,02 1234 5678,x@example.com,01/02/2026,Shortage,01/06/2026
423456,Old Brand 10mg,Someone,atenolol,10 mg,Tablet,Discontinued,01/01/2026,,Discontinued,Commercial,02 1234 5678,x@example.com,01/01/2026,Discontinuation,01/03/2026
"""


@pytest.fixture()
def parsed() -> list[dict[str, object]]:
    return tga.parse(FIXTURE)


def test_the_header_is_found_below_the_preamble(parsed: list[dict[str, object]]) -> None:
    """The preamble length is not guaranteed, so the header is located by
    `ARTG ID` rather than assumed to be line 1."""
    assert len(parsed) == 4
    assert [r["artg_id"] for r in parsed] == ["123456", "223456", "323456", "423456"]


def test_a_byte_order_mark_is_tolerated() -> None:
    """The export is `utf-8-sig`. A BOM left in place corrupts the first header
    name, so `ARTG ID` would not be found at all."""
    assert len(tga.parse("﻿" + FIXTURE)) == 4


def test_a_file_without_the_marker_fails_loudly() -> None:
    """A changed format must stop the build, not yield zero rows silently."""
    with pytest.raises(ValueError, match="ARTG ID"):
        tga.parse("not,the,right,file\n1,2,3\n")


def test_ingredients_split_on_tilde_and_sort(parsed: list[dict[str, object]]) -> None:
    """The export's order is not stable, so they are sorted rather than read
    positionally -- otherwise the same combination compares unequal to itself."""
    assert parsed[0]["ingredients"] == ["warfarin sodium"]
    assert parsed[1]["ingredients"] == ["indapamide", "perindopril arginine"]
    assert tga.split_ingredients("perindopril arginine~indapamide") == \
        tga.split_ingredients("indapamide~perindopril arginine")


def test_dates_are_parsed_day_first(parsed: list[dict[str, object]]) -> None:
    """`01/09/2026` is 1 September, not 9 January. Month-first would silently
    shift most dates and quietly invent valid-looking wrong ones."""
    assert parsed[0]["shortage_start"] == "2026-09-01"
    assert parsed[0]["expected_resolution"] == "2026-12-15"
    assert tga.parse_day_first("15/12/2026") == "2026-12-15"


def test_a_missing_or_unparseable_date_becomes_none_not_a_guess(parsed: list[dict[str, object]]) -> None:
    assert parsed[1]["expected_resolution"] is None
    assert tga.parse_day_first("") is None
    assert tga.parse_day_first("December 2026") is None


def test_only_current_and_anticipated_are_notifiable(parsed: list[dict[str, object]]) -> None:
    """A resolved or discontinued shortage must not raise a notice; doing so
    would put stale alarms in front of a pharmacist."""
    assert {r["status"]: r["notifiable"] for r in parsed} == {
        "Current": True, "Anticipated": True, "Resolved": False, "Discontinued": False,
    }
    assert tga.NOTIFIABLE_STATUSES == frozenset({"Current", "Anticipated"})


def test_the_phone_column_is_dropped(parsed: list[dict[str, object]]) -> None:
    """A contact phone number is personal data we have no use for."""
    assert "Phone" in FIXTURE
    for row in parsed:
        assert not any("1234 5678" in str(v) for v in row.values())
    assert "phone" not in {c.lower() for c in tga.OUT_COLUMNS}


def test_salt_quantity_is_named_so_it_cannot_be_mistaken_for_strength(parsed: list[dict[str, object]]) -> None:
    """`Quantity of active ingredients` is salt mass. Comparing it with a
    dispensed strength would manufacture a dose discrepancy out of a salt
    difference -- so the field is renamed at the boundary."""
    assert parsed[0]["salt_quantity"] == "5 mg"
    assert "strength" not in {c.lower() for c in tga.OUT_COLUMNS}
    assert "salt_quantity" in tga.OUT_COLUMNS


def test_an_unexpected_status_is_reported_not_silently_accepted(capsys) -> None:
    rows = tga.parse(FIXTURE.replace(",Current,", ",Pending,"))
    assert "Pending" in capsys.readouterr().out
    assert [r for r in rows if r["status"] == "Pending"][0]["notifiable"] is False
