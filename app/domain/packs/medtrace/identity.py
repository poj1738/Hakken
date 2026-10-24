"""Record linkage across the four silos (brief section 1; PLAN 2.5).

Two tiers. A matching synthetic IHI is decisive; everything else is
Fellegi-Sunter, where each field contributes a log2 weight for agreeing or
disagreeing and the sum becomes a posterior.

The asymmetry that drives every threshold here: a **missed link** shows the
pharmacist one fewer source and a visible coverage gap, while a **false merge**
silently blends two patients' medicines into one list. The first is a stated
limitation; the second is a safety incident. So guards push to `review` rather
than resolving, and false-merge rate has a target of zero (PLAN 4, Sunday).
"""

from __future__ import annotations

from app.domain.packs.medtrace.types import IdentityBand, IdentityLink, Lexicon, SourceRow

#: Fellegi-Sunter posterior at or above this merges without asking.
AUTO_MERGE_THRESHOLD = 0.85
#: Between this and `AUTO_MERGE_THRESHOLD`, a human decides.
REVIEW_THRESHOLD = 0.82


def decide(probability: float) -> IdentityBand:
    """Band a posterior: `>=0.85` auto-merge, `>=0.82` review, else new.

    **TODO (Arpon, 4pm): replace with `app.engines.world_model.decide`.** This is
    a deliberate three-line duplicate so `identity.py` is importable before
    Arnav's World Model port lands (PLAN 5.9, 7). The thresholds are the same
    numbers; when the engine lands this body becomes a delegation and the
    constants above are deleted.

    The 0.82-0.85 review band is narrow on purpose. It is the only part of the
    pipeline that stops the run and asks a human (`needs_review`), so widening it
    costs a pharmacist's attention on every patient and narrowing it converts
    near-misses into silent merges.
    """
    if probability >= AUTO_MERGE_THRESHOLD:
        return "auto-merge"
    if probability >= REVIEW_THRESHOLD:
        return "review"
    return "new"


def score_pair(a: SourceRow, b: SourceRow, lex: Lexicon) -> IdentityLink:
    """Score one candidate pairing, with the field-level reasons.

    Tier 1 -- `ihi_syn`:
      - equal -> probability 1.0, tier `ihi_exact`.
      - both present and different -> **hard non-link**, tier `ihi_conflict`.
        Not a low score: two different IHIs are positive evidence of two people,
        and no amount of name agreement should overturn it.

    Tier 2 -- Fellegi-Sunter, tier `probabilistic`:
      - given name: Jaro-Winkler, plus the nickname table from `lex` for
        Margaret/Peggy, which string distance alone scores as a non-match.
      - surname: compared against both `name_family` and `name_previous`, so a
        maiden name agrees rather than disagreeing.
      - DOB: partial credit for a day/month swap, a one-digit edit, or a year off
        by 1 or 10 -- the planted corruptions (PLAN 4.4). Full disagreement on a
        well-formed DOB is strong negative evidence.
      - postcode: weak positive only. Agreement is common by chance in an
        age-skewed cohort, and disagreement just means someone moved.

    m/u probabilities are hand-set today and re-estimated from the tune split on
    Sunday (PLAN 2.5). Every contributing comparison is recorded in
    `field_evidence` in the words the UI shows the pharmacist.
    """
    raise NotImplementedError("Arpon: identity.py")


def link_identity(anchor: SourceRow, candidates: list[SourceRow], lex: Lexicon) -> list[IdentityLink]:
    """Score every candidate against the anchor, then apply the guards.

    Candidates arrive as rows (Q1 returns one row per medicine), so they are
    first collapsed to one record per `(source, source_patient_id)`.

    Guards, each of which can only *demote* a band:
      - `lookalike_cluster`: the same name and DOB appearing twice within one
        source. The planted lookalike and twin pairs are exactly this, and the
        arithmetic cannot tell them apart -- so the threshold rises and a
        distinguishing field is required.
      - `transitivity_suspect`: A~B and B~C but not A~C. The triangle is
        inconsistent, so at most one of the three can be trusted silently.
      - `overlay_suspect`: `detect_overlay` flagged the candidate record.

    Returns at most one link per candidate record, highest probability first.
    """
    raise NotImplementedError("Arpon: identity.py")


def detect_overlay(rows_for_one_record: list[SourceRow]) -> list[str]:
    """Flag a single source record that looks like two people merged upstream.

    Signals: two different DOBs or sexes under one `source_patient_id`, or the
    same chronic drug dispensed at two pharmacies on the same day. An overlay in
    the *source* data is the one case where linking correctly still produces a
    wrong medication list, so it is surfaced rather than resolved.

    Stretch (PLAN 4, cut order item 1). Returns the reasons found, or `[]`.
    """
    raise NotImplementedError("Arpon: identity.py")
