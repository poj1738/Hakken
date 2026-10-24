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


# --------------------------------------------------------------------------- #
# Brief 8: the differences that must never be flagged, and the ones that must.
#
# Source: docs/research/"Medication Reconciliation Prototype_ Synthetic Data
# Realism, High-Risk Lists and Pitch Claims Review.md" (24 Oct 2026), brief 8.
# SUPPRESS above is the frozen contract and is pinned by a test; these tables
# are the clinical detail behind it, kept as data so detect.py and the demo
# cannot drift from the reviewed list.
#
# The overall rule: compare by ingredient, molar-equivalent dose, total daily
# dose and release type. Brand, salt, notation and combination-versus-component
# differences are suppressed UNLESS release type, unit concentration or brand
# non-interchangeability changes the therapy.
#
# Where the consultant could not retrieve a dose-equivalence source, no
# conversion factor is recorded here. An unverified factor silently applied to a
# high-risk medicine is worse than no factor at all, so those cases are listed
# under ALWAYS_FLAG and sent to a human instead.
# --------------------------------------------------------------------------- #

#: Salt and ester forms that are the same therapy at the listed strengths, so a
#: difference between them is never a finding. Keyed by ingredient; each entry
#: maps a salt form to the mg that are equivalent across forms.
#: Perindopril: TGA AusPAR for Coveram.
SALT_EQUIVALENT_MG: dict[str, list[tuple[float, float]]] = {
    # (arginine mg, erbumine mg) -- Coversyl 5 mg == perindopril erbumine 4 mg.
    "perindopril": [(2.5, 2.0), (5.0, 4.0), (10.0, 8.0)],
}

#: Ingredients whose Australian products are labelled by base-equivalent
#: strength, so the same labelled mg is the same dose whatever salt is named.
#: Consultant judgement; per-PI verification was NOT done, so this suppresses
#: only a salt-name difference at identical mg -- never a dose difference.
SALT_NAME_ONLY = (
    "amlodipine", "bisoprolol", "quetiapine", "venlafaxine", "desvenlafaxine",
)

#: Frequency notations that mean the same instruction. ACSQHC Recommendations
#: for safe use of medicines terminology (November 2024).
EQUIVALENT_NOTATION: dict[str, str] = {
    "mane": "morning", "in the morning": "morning", "one in the morning": "morning",
    "nocte": "night", "at night": "night",
    "bd": "twice daily", "morning and night": "twice daily",
}

#: Ingredients where time of day is part of the therapy, so "daily" versus a
#: specific time is a real difference rather than notation. Judgement.
TIMING_MATTERS = ("simvastatin", "levothyroxine")

#: Differences that are ALWAYS findings, even though a shallower comparison
#: would call them equivalent. These override every suppression rule above.
ALWAYS_FLAG = {
    # Release-type change, and the succinate form is PBS-restricted to heart
    # failure. A 1:1 equivalence source was NOT retrieved -- assert no factor.
    "metoprolol_salt_change": "tartrate and succinate are not interchangeable",
    # IR versus MR at the same mg: Endone vs OxyContin, gliclazide 80 mg IR vs
    # Diamicron MR. Gliclazide IR and MR are not mg-equivalent and the
    # conversion source was NOT retrieved.
    "release_type_change": "immediate and modified release are different therapy",
    # A halved MR unit, unless the PI permits halving. Per-product halving rules
    # were NOT verified, so every halved MR unit goes to a human.
    "modified_release_split": "an MR unit halved without a PI that permits it",
    # Weekly versus daily on these is the classic fatal error.
    "weekly_vs_daily": ("methotrexate", "alendronate", "risedronate"),
    # A combination PLUS a separate product sharing an ingredient -- Coveram +
    # Norvasc, Rosuzet + Crestor, CoPlavix + Astrix, Panadeine Forte + Panadol
    # Osteo. This is the duplication detector's main job.
    "combination_plus_component": "a combination and one of its own ingredients",
    # Brands that are not interchangeable.
    "brand_not_interchangeable": (
        ("Marevan", "Coumadin"),      # warfarin; WA Country Health
        ("Optisulin", "Toujeo"),      # 100 vs 300 units/mL, equivalence NOT retrieved
    ),
}

#: A combination versus its separate components at identical doses is never a
#: finding -- Coversyl Plus vs perindopril + indapamide, Caduet, Atozet,
#: CoPlavix, Twynsta, Jardiamet. Handled by comparing ingredient sets and total
#: daily dose rather than by product name; listed here so the intent is
#: explicit and testable.
COMBINATION_EQUALS_COMPONENTS = True

#: Brand differences are suppressed only for items the national List of
#: Medicines for Brand Consideration does NOT carry. The LMBC is published by
#: the Australian Digital Health Agency as SNOMED reference set
#: 1495581000168106 (version 20241231); its contents were NOT retrieved, so
#: until it is loaded, a brand difference on a narrow-therapeutic-index
#: medicine goes to a human rather than being suppressed.
LMBC_REFSET_ID = "1495581000168106"
LMBC_LOADED = False


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
