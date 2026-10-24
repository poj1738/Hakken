"""High-risk classification and the human-review gate (`CLAUDE.md` rule 9).

APINCHS is the ACSQHC grouping of medicines where an error is most likely to
cause serious harm: Antimicrobials, Potassium and electrolytes, Insulin,
Narcotics and sedatives, Chemotherapeutics, Heparin and anticoagulants, Systems
(this last one is a process category, not a drug class). We classify by **ATC
prefix**, which arrives free inside the PBS data (PLAN 3) and needs no licensed
ontology.

The concept is attributed to ACSQHC; the ~40-row prefix table is our own work
(`docs/DATA_LICENCES.md`).
"""

from __future__ import annotations

from app.domain.packs.medtrace.types import (
    DiscrepancyCandidate,
    DiscrepancyType,
    GateResult,
    Lexicon,
)

#: Medicines whose dose changes **without a new prescription**, so comparing
#: sources cannot establish the current dose however well they agree.
#: `generic` -> the task text. See `forced_confirm`.
DOSE_CHANGES_WITHOUT_A_SCRIPT: dict[str, str] = {
    "warfarin": "Confirm the current warfarin dose with the patient or their INR record",
    "insulin glargine": "Confirm the current insulin glargine dose with the patient",
    "insulin aspart": "Confirm the current insulin aspart doses with the patient",
    "prednisolone": "Confirm which step of the prednisolone taper the patient is on",
}

#: ATC prefixes for the same property, so an agent we have no `generic` string
#: for is still caught: all insulins, and vitamin K antagonists.
DOSE_CHANGES_WITHOUT_A_SCRIPT_ATC: tuple[str, ...] = ("A10A", "B01AA")

#: `docs/DATA_SPEC.md` 10.1, verbatim: "Prednisolone (H02AB) is not APINCHS; it
#: carries `high_risk_class = "steroid_taper_ext"` for dose_unconfirmable only."
#: So it is high-risk for exactly one purpose and must not be ranked as a core
#: APINCHS class -- hence a distinct label rather than reusing `Ext`.
STEROID_TAPER_PREFIX = "H02AB"
STEROID_TAPER_CLASS = "steroid_taper_ext"

#: Resolutions that mean the medicine name itself is not established fact.
#: A finding resting on one of these cannot be actioned without a human.
UNTRUSTED_RESOLUTIONS = frozenset({"llm", "unmapped"})


def high_risk_class(atc: str | None, lex: Lexicon) -> str | None:
    """The APINCHS letter for an ATC code, by longest matching prefix.

    `lex.apinchs` is sorted longest-first so the most specific rule wins: `A10AB`
    (fast-acting insulin) must beat a broader `A10` before it. Returns `None` for
    an unclassified or missing code -- and `None` means "not classified", not
    "safe", so nothing downstream may treat it as a reason to demote.
    """
    if not atc:
        return None
    code = atc.strip().upper()
    for prefix, klass in lex.apinchs:
        if code.startswith(prefix):
            return klass
    # Tapering steroids are the one documented exception: high-risk for
    # `dose_unconfirmable` only, and deliberately absent from the APINCHS table.
    if code.startswith(STEROID_TAPER_PREFIX):
        return STEROID_TAPER_CLASS
    return None


def forced_confirm(generic: str, atc: str | None) -> str | None:
    """A confirmation task that is emitted regardless of whether we found a conflict.

    Warfarin, insulin and tapering steroids share a property that defeats
    source-comparison entirely: the dose changes **without a new prescription**,
    so every source can be internally consistent and all of them stale.
    Agreement between sources is not evidence of the current dose here.

    Returns the task text, or `None`. Independent of `detect_discrepancies` by
    design -- a silent agreement is exactly the case this catches.
    """
    name = (generic or "").strip().casefold()
    for known, task in DOSE_CHANGES_WITHOUT_A_SCRIPT.items():
        if name == known or name.startswith(known):
            return task
    code = (atc or "").strip().upper()
    if code:
        for prefix in DOSE_CHANGES_WITHOUT_A_SCRIPT_ATC:
            if code.startswith(prefix):
                label = generic.strip() or "this medicine"
                return f"Confirm the current {label} dose with the patient"
    return None


def safety_gate(c: DiscrepancyCandidate) -> GateResult:
    """The human-review gate. Decides what may be shown, and on what terms.

    - `blocked` -- no `row_ids`. An unciteable finding is not shown as a finding.
    - `needs_pharmacist` -- any high-risk (APINCHS) item, anything resolved by
      `llm` or left `unmapped`, and anything resting on a `review`-band identity
      link. Shown and ranked, but never actionable without a human tick.
    - `allow` -- shown normally. Still a *draft* for pharmacist confirmation;
      nothing this system emits is an instruction.

    Reads two optional conventions from `DiscrepancyCandidate.detail`:
    `resolution` (how the medicine name was established) and `identity_band`
    (the band of the link the finding rests on). Both absent means neither
    concern applies -- a finding that does not say it is uncertain is treated as
    certain, which is why the detectors must set them.
    """
    row_ids = list(getattr(c, "row_ids", []) or [])
    if not row_ids:
        return GateResult(
            decision="blocked",
            reason="no row_ids: an unciteable finding is indistinguishable from an invented one",
            required_tasks=[],
        )

    detail = dict(getattr(c, "detail", {}) or {})
    reasons: list[str] = []
    tasks: list[str] = []

    if getattr(c, "high_risk_class", None):
        reasons.append(f"high-risk medicine (APINCHS {c.high_risk_class})")
    resolution = str(detail.get("resolution", "")).casefold()
    if resolution in UNTRUSTED_RESOLUTIONS:
        reasons.append(f"medicine name established by {resolution}, not by a code")
        tasks.append("Confirm the medicine name with the patient or the dispensing record")
    band = str(detail.get("identity_band", "")).casefold()
    if band == "review":
        reasons.append("rests on an identity link that needs confirmation")
        tasks.append("Confirm this is the same person before acting on this finding")
    if getattr(c, "type", None) == DiscrepancyType.IDENTITY_UNCERTAIN:
        reasons.append("the finding is itself an unresolved identity question")

    if reasons:
        return GateResult(decision="needs_pharmacist", reason="; ".join(reasons),
                          required_tasks=tasks)
    return GateResult(decision="allow",
                      reason="cited and not high-risk; still a draft for confirmation",
                      required_tasks=[])
