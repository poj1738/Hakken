"""`supply.py`: dispensing arithmetic, and the false-cessation guard.

The two error directions are not symmetric. Calling a current medicine ceased
can stop an anticoagulant; calling a stopped one current re-prescribes
something a doctor deliberately withdrew. **False-cessation rate has a target
of zero**, which is why nothing here ever returns "CEASED".
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.packs.medtrace.supply import GRACE_DAYS, pdc, supply_status
from app.domain.packs.medtrace.types import MedStatement

AS_OF = date(2026, 10, 24)


def fill(days_ago: int, days_supply: int = 30, **kwargs) -> MedStatement:
    base = {"source": "pharmacy", "row_id": f"PHM-{days_ago:06d}", "raw_text": "atorvastatin",
            "generic": "atorvastatin", "days_supply": days_supply,
            "doc_date": AS_OF - timedelta(days=days_ago)}
    return MedStatement(**(base | kwargs))


# --------------------------------------------------------------------------- #
# supply_status
# --------------------------------------------------------------------------- #


def test_no_dispensing_is_not_evidence_of_anything() -> None:
    """It is also what a second pharmacy, a private script or a sample pack
    looks like."""
    assert supply_status([], AS_OF) == "NO_DISPENSING"


def test_a_recent_fill_is_active() -> None:
    assert supply_status([fill(10)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_supply_still_running_is_active() -> None:
    """Day 29 of a 30-day pack."""
    assert supply_status([fill(29, days_supply=30)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_inside_the_grace_period_is_still_active() -> None:
    """The grace absorbs a holiday, a hoarded box, or a hospital admission
    supplying its own -- so the flag means something when it does fire."""
    assert supply_status([fill(30 + GRACE_DAYS - 1, days_supply=30)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_well_past_the_grace_period_is_possibly_ceased() -> None:
    assert supply_status([fill(330, days_supply=30)], AS_OF) == "POSSIBLY_CEASED"


def test_the_boundary_is_inclusive_in_the_safe_direction() -> None:
    """Exactly at run-out plus grace is still active. Off-by-one here is a false
    cessation, and the target for those is zero."""
    assert supply_status([fill(30 + GRACE_DAYS, days_supply=30)], AS_OF) == "ACTIVE_BY_SUPPLY"
    assert supply_status([fill(31 + GRACE_DAYS, days_supply=30)], AS_OF) == "POSSIBLY_CEASED"


def test_the_most_recent_fill_decides() -> None:
    assert supply_status([fill(400), fill(5)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_a_prn_medicine_is_never_called_possibly_ceased() -> None:
    """A long gap between PRN fills is normal, not informative."""
    assert supply_status([fill(300, prn=True)], AS_OF) == "ACTIVE_BY_SUPPLY"


@pytest.mark.parametrize("frequency", ["6-monthly", "yearly", "prn"])
def test_irregular_regimens_are_suppressed(frequency: str) -> None:
    """Denosumab is six-monthly and zoledronic acid yearly. Treating their
    normal interval as a lapse would flag every one of them."""
    assert supply_status([fill(300, frequency=frequency)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_a_missing_days_supply_assumes_generous_cover() -> None:
    """Under-estimating cover is what produces a false cessation."""
    assert supply_status([fill(100, days_supply=None)], AS_OF) == "ACTIVE_BY_SUPPLY"


def test_a_gp_listing_passed_in_by_mistake_is_ignored() -> None:
    """The function filters to dispensings itself, so a caller cannot get supply
    arithmetic over a GP list."""
    gp = MedStatement(source="gp", row_id="GP-1", raw_text="atorvastatin",
                      generic="atorvastatin", doc_date=AS_OF - timedelta(days=400))
    assert supply_status([gp], AS_OF) == "NO_DISPENSING"


def test_nothing_ever_returns_ceased() -> None:
    """The vocabulary itself is the guard: there is no CEASED to return."""
    for history in ([], [fill(5)], [fill(900)], [fill(900, prn=True)]):
        assert supply_status(history, AS_OF) in (
            "ACTIVE_BY_SUPPLY", "POSSIBLY_CEASED", "NO_DISPENSING")


# --------------------------------------------------------------------------- #
# pdc
# --------------------------------------------------------------------------- #


def test_no_dispensing_in_the_window_is_none_not_zero() -> None:
    """Zero coverage and no visibility are different claims, and only one
    belongs in front of a pharmacist."""
    assert pdc([], AS_OF) is None
    assert pdc([fill(400)], AS_OF, window_days=180) is None


def test_continuous_cover_is_one() -> None:
    """The oldest fill has to start *before* the window opens, or day 0 is
    uncovered. A fill dated today covers days after `as_of`, which are outside
    a trailing window by definition."""
    fills = [fill(days, days_supply=30) for days in (180, 150, 120, 90, 60, 30)]
    assert pdc(fills, AS_OF, window_days=180) == 1.0


def test_half_cover_is_about_a_half() -> None:
    """Three 30-day packs across a 180-day window: about 90 days covered."""
    fills = [fill(days, days_supply=30) for days in (150, 90, 30)]
    assert 0.45 <= pdc(fills, AS_OF, window_days=180) <= 0.55


def test_overlapping_fills_count_once() -> None:
    """Otherwise an early refill reads as 150% adherence."""
    stockpiled = [fill(days, days_supply=30) for days in (0, 5, 10, 15)]
    assert pdc(stockpiled, AS_OF, window_days=180) <= 1.0
    assert pdc(stockpiled, AS_OF, window_days=180) < 0.4


def test_coverage_is_capped_at_one() -> None:
    hoarded = [fill(days, days_supply=180) for days in range(10, 190, 10)]
    assert pdc(hoarded, AS_OF, window_days=180) == 1.0


def test_a_fill_before_the_window_still_counts_for_its_remaining_cover() -> None:
    """A 90-day pack dispensed 30 days before the window covers its first 60."""
    # Exhausted well before the window opened: invisible.
    assert pdc([fill(300, days_supply=30)], AS_OF, window_days=180) is None
    # Still running when the window opened: counts for the overlap only.
    value = pdc([fill(200, days_supply=180)], AS_OF, window_days=180)
    assert value is not None and 0.0 < value < 1.0


def test_a_nonsense_window_returns_none() -> None:
    assert pdc([fill(10)], AS_OF, window_days=0) is None
