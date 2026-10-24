"""Ranking, and what is never flagged (brief section 5; PLAN 2.5).

Ordering is a safety control, not presentation. A pharmacist reconciling an
admission has minutes, so the ranking decides which findings are actually read.

`acceptance` is learned from pharmacist verdicts per `(type, ATC class)`: types
that keep getting rejected as clinically irrelevant sink. The floor on that is
absolute -- **an APINCHS item is never demoted below "must review"**, however
often that class has been dismissed before. Learned relevance may reorder the
list; it may not hide a high-risk finding.
"""

from __future__ import annotations

from app.domain.packs.medtrace.types import DiscrepancyCandidate

#: Differences that are **never** findings (PLAN 2.6).
#:
#: - `brand_only` -- Lipitor and atorvastatin are the same medicine. Flagging it
#:   is the canonical false positive, and the demo shows it *not* firing.
#: - `notation_only` -- "1 tab bd" and "BD" are the same instruction.
#: - `equivalent_daily_dose` -- "500mg bd" and "1g daily" are the same dose.
SUPPRESS = ["brand_only", "notation_only", "equivalent_daily_dose"]


def prioritise(
    cands: list[DiscrepancyCandidate],
    acceptance: dict[tuple[str, str], float],
) -> list[DiscrepancyCandidate]:
    """Score and sort candidates, highest priority first.

    `priority = class_risk x type_severity x evidence_strength x acceptance(type, class)`.

    - `class_risk` -- from the APINCHS class.
    - `type_severity` -- from `DiscrepancyCandidate.severity`.
    - `evidence_strength` -- how many independent sources, how recent, and
      whether any leg was `llm`-resolved or `unmapped`.
    - `acceptance` -- the learned term, from `POST /feedback`.

    Sets `priority` in place and returns the sorted list. Items whose type is in
    `SUPPRESS` are dropped here if anything upstream produced them, so the
    suppression rule holds even if a detector regresses.
    """
    raise NotImplementedError("Arpon: triage.py")
