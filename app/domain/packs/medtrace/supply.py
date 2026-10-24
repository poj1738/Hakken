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

from datetime import date
from typing import Literal

from app.domain.packs.medtrace.types import MedStatement


def supply_status(
    dispensings: list[MedStatement],
    as_of: date,
) -> Literal["ACTIVE_BY_SUPPLY", "POSSIBLY_CEASED", "NO_DISPENSING"]:
    """Classify one medicine by whether the supply could still be running.

    `expected_runout = last dispense date + days_supply`.
    `POSSIBLY_CEASED` once `as_of` is past `runout + max(30 days, days_supply/2)`.

    The grace period absorbs the ordinary reasons a refill is late -- a holiday,
    a hoarded box, a hospital admission supplying its own -- so that the flag
    means something when it fires. `NO_DISPENSING` is not evidence of anything:
    it is also what a second pharmacy, a private script or a sample pack looks
    like, and `coverage.possible_second_pharmacy` handles that case.
    """
    raise NotImplementedError("Arpon: supply.py")


def pdc(dispensings: list[MedStatement], as_of: date, window_days: int = 180) -> float | None:
    """Proportion of days covered over the trailing window, or `None`.

    Days with supply on hand divided by days in the window, capped at 1.0 so
    stockpiling cannot push adherence above complete. Overlapping fills count
    once.

    Returns `None` rather than `0.0` when there is no dispensing in the window --
    zero coverage and no visibility are different claims, and only one of them
    belongs in front of a pharmacist.
    """
    raise NotImplementedError("Arpon: supply.py")
