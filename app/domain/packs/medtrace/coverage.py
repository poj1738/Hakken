"""What we found, what we did not, and what absence is allowed to mean.

Brief section 2; PLAN 2.5. This module exists because the dangerous failure of a
medication reconciliation tool is not a wrong number -- it is a confident blank.
If the GP system was never reached and the grid shows an empty cell, a reader
concludes the patient is not taking the medicine. `EvidenceState` makes that
unrepresentable: only `ABSENT_IN_SCOPE` counts against a medicine, and it
requires that we found the source *and* can see the slice of it that would have
listed the drug.
"""

from __future__ import annotations

from datetime import date

from app.domain.packs.medtrace.types import (
    Coverage,
    EvidenceState,
    IdentityLink,
    MedStatement,
    SourceRow,
)


def coverage(links: list[IdentityLink], rows: list[SourceRow]) -> dict[str, Coverage]:
    """Report, per source, whether we found this patient and how completely.

    States:
      - `found` -- an accepted link and rows (or a deliberate "known here, no
        medicines" row, PLAN 2.2).
      - `near_miss_pending` -- a `review`-band link awaiting a human. Not
        `not_found`: we probably did find them, and saying "no GP record" would
        be wrong.
      - `not_found` -- no candidate cleared the floor.

    `scope_notes` carries the honest caveats that `evidence_state` then reads:
    "pharmacy_id P2 only" when dispensing is visible from one pharmacy,
    "GP list updated 14 months ago" from the document date. Every source is
    present in the returned dict, including the ones we missed -- a missing key
    would read as a source we never had to consider.
    """
    raise NotImplementedError("Arpon: coverage.py")


def evidence_state(
    generic: str,
    source: str,
    cov: Coverage,
    stmts: list[MedStatement],
) -> EvidenceState:
    """What one source says about one medicine. The three-valued core.

    - `PRESENT` -- this source asserts it.
    - `ABSENT_IN_SCOPE` -- found, in scope, and not asserted. The only value that
      counts as evidence against the medicine.
    - `UNKNOWN` -- we cannot tell. Returned when the source is `not_found` or
      `near_miss_pending`, and also when the medicine **would not appear** in
      what we can see: a privately dispensed drug is invisible to a PBS-only
      view, and calling that "absent" would manufacture an omission.
    """
    raise NotImplementedError("Arpon: coverage.py")


def bpmh_confirmable(cov: dict[str, Coverage]) -> tuple[bool, str]:
    """Whether a BPMH can be confirmed at all, and the banner if not.

    ACSQHC Standard 4 (Action 4.5) expects **at least two independent sources**.
    Below that the output is explicitly not a confirmable history, and the UI
    shows the banner instead of implying completeness. Returns
    `(confirmable, banner_text)` with an empty banner when confirmable.

    Independence matters: the EMR admission chart and a prior discharge summary
    from the same EMR are one source, not two.
    """
    raise NotImplementedError("Arpon: coverage.py")


def possible_second_pharmacy(
    stmts: list[MedStatement],
    cov: dict[str, Coverage],
    as_of: date,
) -> list[str]:
    """Signs that dispensing is split across a pharmacy we cannot see.

    10% of generated patients have exactly this (PLAN 4.4). Signals: a chronic
    medicine with no dispensing at all, gaps far longer than `days_supply`, or
    more than one `pharmacy_id` already visible. Returns task-shaped reasons for
    the notice; it never concludes that a medicine was stopped.
    """
    raise NotImplementedError("Arpon: coverage.py")
