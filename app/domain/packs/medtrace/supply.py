"""Dispensing arithmetic (brief section 3; PLAN 2.5).

Turns a dispensing history into "is this plausibly still being taken", which is
the only objective evidence we have that a GP's `active` listing has gone stale.

Both error directions are costly and they are not symmetric. Calling a current
medicine ceased can stop an anticoagulant; calling a stopped medicine current
re-prescribes something a doctor deliberately withdrew. So the output is
`POSSIBLY_CEASED` -- never `CEASED` -- and **false-cessation rate has a target
of zero** (PLAN 4, Sunday). The generous grace period below exists for that
reason, not for arithmetic convenience.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from app.domain.packs.medtrace.parse import normalise_text
from app.domain.packs.medtrace.types import MedStatement

#: Days past the expected run-out before a medicine is called possibly ceased.
#: DATA_SPEC 9.4 uses 90 days, matching the discontinuation definition in
#: Ofori-Asenso 2019 and de Oliveira Costa 2023 (90+ days without coverage).
GRACE_DAYS = 90

#: Regimens whose run-out cannot be computed from a fill interval, so the
#: possibly-ceased rule is suppressed for them (DATA_SPEC 9.4). A PRN medicine
#: with no fill for six months may be entirely correct.
IRREGULAR_REGIMENS = ("prn", "as needed", "when required", "6-monthly", "six monthly",
                      "yearly", "annually", "monthly")

#: Default cover for a dispensing with no `days_supply`. Deliberately generous:
#: under-estimating cover is what produces a false cessation.
ASSUMED_DAYS_SUPPLY = 30


def _is_irregular(statement: MedStatement) -> bool:
    blob = " ".join(normalise_text(t) for t in (statement.frequency, statement.route) if t)
    return statement.prn or any(word in blob for word in IRREGULAR_REGIMENS)


def _cover(statement: MedStatement) -> int:
    return statement.days_supply or ASSUMED_DAYS_SUPPLY


def supply_status(
    dispensings: list[MedStatement],
    as_of: date,
) -> Literal["ACTIVE_BY_SUPPLY", "POSSIBLY_CEASED", "NO_DISPENSING"]:
    """Classify one medicine by whether the supply could still be running.

    `expected_runout = last dispense date + days_supply`.
    `POSSIBLY_CEASED` once `as_of` is past `runout + 90 days`.

    The grace period absorbs the ordinary reasons a refill is late -- a holiday,
    a hoarded box, a hospital admission supplying its own -- so that the flag
    means something when it fires. `NO_DISPENSING` is not evidence of anything:
    it is also what a second pharmacy, a private script or a sample pack looks
    like, and `coverage.possible_second_pharmacy` handles that case.

    Suppressed to `ACTIVE_BY_SUPPLY` for PRN, six-monthly and yearly regimens,
    where a long gap between fills is normal rather than informative.

    Takes the whole list and filters to dispensings itself, so a caller cannot
    accidentally pass a GP listing and get supply arithmetic over it.
    """
    fills = [s for s in dispensings
             if s.source == "pharmacy" and s.doc_date is not None]
    if not fills:
        return "NO_DISPENSING"

    if any(_is_irregular(s) for s in fills):
        return "ACTIVE_BY_SUPPLY"

    last = max(fills, key=lambda s: s.doc_date)  # type: ignore[arg-type,return-value]
    assert last.doc_date is not None
    runout = last.doc_date + timedelta(days=_cover(last))
    if as_of <= runout + timedelta(days=GRACE_DAYS):
        return "ACTIVE_BY_SUPPLY"
    return "POSSIBLY_CEASED"


def pdc(dispensings: list[MedStatement], as_of: date, window_days: int = 180) -> float | None:
    """Proportion of days covered over the trailing window, or `None`.

    Days with supply on hand divided by days in the window, capped at 1.0 so
    stockpiling cannot push adherence above complete. Overlapping fills count
    once -- the union of covered days, not the sum of their lengths, which is
    what makes an early refill look like adherence rather than 150%.

    Returns `None` rather than `0.0` when there is no dispensing in the window:
    zero coverage and no visibility are different claims, and only one of them
    belongs in front of a pharmacist.
    """
    if window_days <= 0:
        return None
    start = as_of - timedelta(days=window_days)
    fills = [s for s in dispensings
             if s.source == "pharmacy" and s.doc_date is not None
             and s.doc_date + timedelta(days=_cover(s)) > start
             and s.doc_date <= as_of]
    if not fills:
        return None

    covered: set[int] = set()
    for fill in fills:
        assert fill.doc_date is not None
        first = max((fill.doc_date - start).days, 0)
        last = min((fill.doc_date - start).days + _cover(fill), window_days)
        covered.update(range(first, last))
    return round(min(1.0, len(covered) / window_days), 4)
