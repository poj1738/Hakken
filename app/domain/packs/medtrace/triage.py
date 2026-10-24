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

#: APINCHS classes from the ACSQHC core list (A, P, I, N, C, H, and S where a
#: lexicon carries it). These carry the absolute floor.
CORE_APINCHS = frozenset({"A", "P", "I", "N", "C", "H", "S"})

#: How much more a finding matters because of what the medicine is.
CLASS_RISK: dict[str, float] = {"core": 3.0, "Ext": 2.0, "steroid_taper_ext": 1.5}

#: How much more it matters because of what kind of finding it is.
SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}

#: The "must review" line. Anything at or above it is shown expanded, first.
#: The highest a non-high-risk finding can score is 1 x 3 x 1 x 1 = 3, so a
#: floor of 4 puts every core APINCHS item above every other finding,
#: whatever the learned acceptance says.
MUST_REVIEW_FLOOR = 4.0

#: A documented reason ("withheld: AKI") halves the priority: collapsed in the
#: UI with its reason, never hidden -- the reason can still be the mistake.
DOCUMENTED_INTENT_FACTOR = 0.5

#: Learned acceptance is clamped here, so no type can be learned into
#: invisibility -- a rate of zero would multiply a finding off the list.
MIN_ACCEPTANCE = 0.05

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

    Concretely:

    - `class_risk` -- 3 for core APINCHS, 2 for an extension (`Ext`), 1.5 for
      the prednisolone taper, 1 otherwise.
    - `type_severity` -- high 3, medium 2, low 1.
    - `evidence_strength` -- 0.6 plus 0.2 per independent pre-admission source
      behind it, capped at 1. A finding the GP, the pharmacy and the patient all
      point at outranks one resting on a single source.
    - `acceptance` -- looked up as `(type, detail["atc_class"])`, then `(type,
      "")`, default 1, clamped to at least `MIN_ACCEPTANCE`.
    - `documented_intentional` halves it.
    - **Core APINCHS is floored at `MUST_REVIEW_FLOOR`**, after everything
      else, so no amount of learned dismissal ranks a warfarin finding below a
      non-high-risk one.

    Ties break on generic then type, so the order is deterministic.
    """
    kept: list[DiscrepancyCandidate] = []
    for cand in cands:
        if cand.type.value in SUPPRESS or cand.detail.get("suppressed_as") in SUPPRESS:
            continue
        risk_class = cand.high_risk_class
        core = risk_class in CORE_APINCHS
        class_risk = CLASS_RISK["core"] if core else CLASS_RISK.get(risk_class or "", 1.0)
        severity = SEVERITY_WEIGHT.get(cand.severity, 1.0)
        independent = {s for s in cand.sources_involved if s != "emr"}
        evidence = min(1.0, 0.6 + 0.2 * len(independent))
        key = cand.type.value
        rate = acceptance.get((key, str(cand.detail.get("atc_class") or "")),
                              acceptance.get((key, ""), 1.0))
        rate = min(1.0, max(MIN_ACCEPTANCE, rate))
        priority = class_risk * severity * evidence * rate
        if cand.intent_status == "documented_intentional":
            priority *= DOCUMENTED_INTENT_FACTOR
        if core:
            priority = max(priority, MUST_REVIEW_FLOOR)
        cand.priority = round(priority, 4)
        kept.append(cand)
    return sorted(kept, key=lambda c: (-c.priority, c.generic, c.type.value))
