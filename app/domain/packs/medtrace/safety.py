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

from app.domain.packs.medtrace.types import DiscrepancyCandidate, GateResult, Lexicon


def high_risk_class(atc: str | None, lex: Lexicon) -> str | None:
    """The APINCHS letter for an ATC code, by longest matching prefix.

    `lex.apinchs` is sorted longest-first so the most specific rule wins: `A10A`
    (insulins) must beat a broader `A10` before it. Returns `None` for an
    unclassified or missing code -- and `None` means "not classified", not
    "safe", so nothing downstream may treat it as a reason to demote.
    """
    raise NotImplementedError("Arpon: safety.py")


def forced_confirm(generic: str, atc: str | None) -> str | None:
    """A confirmation task that is emitted regardless of whether we found a conflict.

    Warfarin, insulin and tapering steroids share a property that defeats
    source-comparison entirely: the dose changes **without a new prescription**,
    so every source can be internally consistent and all of them stale. Agreement
    between sources is not evidence of the current dose here.

    Returns the task text ("Confirm current warfarin dose with the patient or INR
    record"), or `None`. Independent of `detect_discrepancies` by design -- a
    silent agreement is exactly the case this catches.
    """
    raise NotImplementedError("Arpon: safety.py")


def safety_gate(c: DiscrepancyCandidate) -> GateResult:
    """The human-review gate. Decides what may be shown, and on what terms.

    - `blocked` -- no `row_ids`. An unciteable finding is not shown as a finding.
    - `needs_pharmacist` -- any high-risk (APINCHS) item, anything resolved by
      `llm` or left `unmapped`, and anything resting on a `review`-band identity
      link. Shown and ranked, but never actionable without a human tick.
    - `allow` -- shown normally. Still a *draft* for pharmacist confirmation;
      nothing this system emits is an instruction.
    """
    raise NotImplementedError("Arpon: safety.py")
