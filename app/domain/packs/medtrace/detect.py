"""Discrepancy detection (PLAN 2.6).

Deterministic and tested against `data/synthetic/ground_truth.json`. No model
call reaches this module: a finding a pharmacist acts on has to be reproducible,
and the agents' job is to plan, fetch, verify, rank and explain -- not to decide
what counts as a discrepancy.

The hardest requirement here is restraint. Every type in `DiscrepancyType` is a
real finding; `triage.SUPPRESS` lists the differences that are never findings.
An alert list padded with brand-vs-generic noise is worse than no list, because
the one that matters is the one scrolled past.
"""

from __future__ import annotations

from datetime import date

from app.domain.packs.medtrace.types import (
    Coverage,
    DiscrepancyCandidate,
    FusedMed,
    Lexicon,
    MedStatement,
)


def detect_discrepancies(
    fused: list[FusedMed],
    stmts: list[MedStatement],
    cov: dict[str, Coverage],
    as_of: date,
    lex: Lexicon,
) -> list[DiscrepancyCandidate]:
    """Produce every candidate finding, unranked, each citing its rows.

    Per type (PLAN 2.6):
      - `omission` -- supported pre-admission, `ABSENT_IN_SCOPE` on the admission
        chart. Requires `ABSENT_IN_SCOPE`, never `UNKNOWN`.
      - `commission` -- charted and no other source supports it. Weak when the
        other sources are `UNKNOWN`, and said that way.
      - `dose` -- same ingredient, different `daily_dose_mg`. Equal total daily
        doses are never a discrepancy however the regimen is written.
      - `frequency` -- same daily dose, different split, or PRN vs regular.
      - `formulation` -- IR vs MR.
      - `route` -- Sunday.
      - `duplication` -- `ingredients` sets intersect across concurrent lines,
        which is what catches a combination plus one of its own components.
      - `stale_listing` -- listed `active`, `supply_status` says
        `POSSIBLY_CEASED`. Never asserts cessation.
      - `dose_unconfirmable` -- a high-risk regimen that changes without a new
        script and whose sources disagree. Warfarin is the archetype: the dose
        changes by phone, so dispensed tablet strengths cannot reconstruct it and
        the only correct output is a task to confirm.
      - `unpropagated_discharge_change` -- Sunday.
      - `identity_uncertain` -- the finding depends on a `review`-band link, so
        its confidence is capped by the link's.

    `intent_status` is `documented_intentional` when a `chart_note` or
    `action_reason` explains the difference. Those items stay in the list,
    collapsed -- a documented reason can still be a mistake.

    Every candidate carries the `row_ids` it came from. `safety.safety_gate`
    blocks any that cannot, because an unciteable finding is indistinguishable
    from an invented one.
    """
    raise NotImplementedError("Arpon: detect.py")
