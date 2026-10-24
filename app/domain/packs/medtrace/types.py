"""Shared MedTrace types. **Frozen contract -- see PLAN 2.5 and section 1.**

This is a shared file. Arnav's pipeline, Arpon's clinical code and Anshu's
`web/src/types.ts` all depend on these names, so a change here breaks three
people at once. Changing anything in this module needs a `docs/HANDOFF.md`
entry and a line in the PR description.

Two rules that explain most of the design:

1. **Every value out of Zetaris is a string** (`REFERENCE_NOTES` 1.2), so the
   only casting happens in `parse.py`. `SourceRow` keeps both the cast value and
   the raw text where the raw text is evidence in its own right -- a mangled DOB
   is the *point*, not noise to be cleaned away.
2. **Absence is three-valued.** `EvidenceState` distinguishes "this source says
   no" from "we never saw this source". Collapsing them to a boolean is how a
   reconciliation tool tells a pharmacist a patient stopped a medicine they are
   still taking, so the type system refuses to let us.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import date
from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Vocabularies
# --------------------------------------------------------------------------- #

#: The four patient silos, in the order the UI shows them.
SOURCES: tuple[str, ...] = ("emr", "gp", "pharmacy", "patient")

Source = Literal["emr", "gp", "pharmacy", "patient"]

#: Attributes that can be trusted differently per source. The first six are the
#: attributes `fuse()` resolves; the rest are judgements a source makes that are
#: not grid columns but still carry source-specific reliability.
#:
#: PLAN 2.5 lists `("emr", "admission_chart")` among the priors. Kept verbatim so
#: the H-MEM seed matches the plan, and read as "what the admission chart asserts
#: about existence at the time of admission".
TrustAttribute = Literal[
    "existence",
    "daily_dose",
    "frequency",
    "release",
    "route",
    "strength",
    "intended_dose",
    "actually_taking",
    "name",
    "admission_chart",
]

#: Attributes `fuse()` resolves into `FusedMed.attributes`.
FUSED_ATTRIBUTES: tuple[str, ...] = (
    "existence",
    "daily_dose",
    "frequency",
    "release",
    "route",
)


class EvidenceState(str, Enum):
    """What one source says about one medicine.

    `ABSENT_IN_SCOPE` is the only value that counts *against* a medicine:
    the source was found, we can see the slice of it that would list the drug,
    and the drug is not there. `UNKNOWN` means we cannot tell -- the source was
    never found, or the drug would not appear in the slice we have (a private
    script in a PBS-only view). The Writer must never render `UNKNOWN` as
    "not taking".
    """

    PRESENT = "present"
    ABSENT_IN_SCOPE = "absent_in_scope"
    UNKNOWN = "unknown"


class DiscrepancyType(str, Enum):
    """Findings a pharmacist acts on (PLAN 2.6).

    `SUPPRESS` in `triage.py` lists the differences that are deliberately never
    findings. A brand-vs-generic difference is not a discrepancy, and flagging it
    is how these tools get switched off.
    """

    OMISSION = "omission"
    COMMISSION = "commission"
    DOSE = "dose"
    FREQUENCY = "frequency"
    FORMULATION = "formulation"
    ROUTE = "route"
    DUPLICATION = "duplication"
    STALE_LISTING = "stale_listing"
    DOSE_UNCONFIRMABLE = "dose_unconfirmable"
    UNPROPAGATED_DISCHARGE_CHANGE = "unpropagated_discharge_change"
    IDENTITY_UNCERTAIN = "identity_uncertain"


class NoticeType(str, Enum):
    """Context banners and tasks. Not discrepancies, and never ranked with them.

    A notice says something about *our evidence*; a discrepancy says something
    about the patient's medicines.
    """

    COVERAGE_GAP = "coverage_gap"
    BPMH_NOT_CONFIRMABLE = "bpmh_not_confirmable"
    POSSIBLE_SECOND_PHARMACY = "possible_second_pharmacy"
    PATIENT_ONLY_ITEM = "patient_only_item"
    CONFLICT_ABSTAINED = "conflict_abstained"
    STALE_DOCUMENT = "stale_document"


Severity = Literal["high", "medium", "low"]
IntentStatus = Literal["documented_intentional", "possibly_intentional", "likely_unintentional"]
IdentityBand = Literal["auto-merge", "review", "new"]
IdentityTier = Literal["ihi_exact", "ihi_conflict", "probabilistic"]
ReleaseClass = Literal["IR", "MR", "unknown"]
MedStatus = Literal["active", "ceased", "unknown"]
Resolution = Literal["code", "lexicon", "fuzzy", "llm", "unmapped"]
CoverageState = Literal["found", "near_miss_pending", "not_found"]
SupplyStatus = Literal["ACTIVE_BY_SUPPLY", "POSSIBLY_CEASED", "NO_DISPENSING"]
GateDecision = Literal["allow", "needs_pharmacist", "blocked"]

# --------------------------------------------------------------------------- #
# The Zetaris wire envelope
# --------------------------------------------------------------------------- #


class _SqlResultRequired(TypedDict):
    """The keys every recorded response carries. See `SqlResult`."""

    headers: list[str]
    data: list[list[Any]]
    total: int


class SqlResult(_SqlResultRequired, total=False):
    """One Zetaris REST response body, exactly as recorded on a live instance.

    Observed `[live -- Arpon's machine, 23 Oct]` and kept in
    `tests/fixtures/zetaris/`. `headers` is positional against every row in
    `data`, every value is a string, and an empty result is `data: []` with
    `total: 0` and populated `headers` -- not an error.

    Defined here rather than in `app/adapters/zetaris.py` because `parse.py`
    consumes it and the adapter is Arnav's file: the shape is the contract
    between us, so it belongs in the shared module.

    `timeUsed` is **optional**, which is why this is split across two classes.
    The recorded fixtures strip it (it is a latency measurement, not part of the
    shape we parse), so a `SAMPLE_MODE` replay has to satisfy this type too.
    The split is also the only form that works here: under
    `from __future__ import annotations` a `NotRequired[int]` annotation is left
    as a string and `__required_keys__` silently reports it as required, whereas
    `total=False` is a class flag and is honoured.
    """

    timeUsed: int


# --------------------------------------------------------------------------- #
# Rows and reference data
# --------------------------------------------------------------------------- #


class SourceRow(BaseModel):
    """One harmonised row from `medtrace.all_sources` (PLAN 2.3), cast.

    `dob` is the parsed date where we could parse one; `dob_raw` is always the
    text as it arrived. Both are kept because the *difference* between them is
    evidence: a day/month swap, a one-digit typo and a genuinely different
    birthday all parse, and only the raw text tells them apart.

    Everything else stays a string. The view renames columns and does not parse
    (PLAN 2.3), so a value like `strength_text` is whatever the silo wrote --
    "10mg", "10 mg", "0.5mg/mL" -- and `normalise.py` is the only thing allowed
    to interpret it.
    """

    model_config = ConfigDict(extra="forbid")

    source: Source
    row_id: str
    source_patient_id: str
    ihi_syn: str | None = None

    name_given: str | None = None
    name_family: str | None = None
    name_previous: str | None = None
    dob: date | None = None
    dob_raw: str | None = None
    sex: str | None = None
    postcode: str | None = None

    record_kind: str | None = None
    doc_date: date | None = None

    med_text: str | None = None
    med_code: str | None = None
    code_system: str | None = None
    strength_text: str | None = None
    dose_text: str | None = None
    route_text: str | None = None
    freq_text: str | None = None
    status_text: str | None = None
    note_text: str | None = None

    qty: int | None = None
    days_supply: int | None = None
    pharmacy_id: str | None = None
    script_type: str | None = None

    @property
    def record_key(self) -> str:
        """`"gp:GP004411"` -- the stable id used in `IdentityLink` and World Model."""
        return f"{self.source}:{self.source_patient_id}"

    @property
    def has_med(self) -> bool:
        """False for a "known here, no medicines" row (PLAN 2.2 absence rules)."""
        return bool(self.med_text)


class LexiconEntry(BaseModel):
    """One product in the medicines lexicon, built from PBS (PLAN 4.2).

    `ingredients` is `[(ingredient, strength_mg_or_None)]` so a combination
    product decomposes without a second lookup -- that is what makes the
    Coversyl Plus + perindopril duplication detectable.
    """

    model_config = ConfigDict(extra="forbid")

    pbs_code: str | None = None
    brand: str | None = None
    generic: str | None = None
    amt_mp: str | None = None
    amt_mpp: str | None = None
    amt_tpp: str | None = None
    atc_primary: str | None = None
    strength: str | None = None
    form: str | None = None
    release: ReleaseClass = "unknown"
    pack_qty: int | None = None
    repeats: int | None = None
    is_combination: bool = False
    ingredients: list[tuple[str, float | None]] = Field(default_factory=list)
    dos_weight: float | None = None


@dataclass(frozen=True)
class Lexicon:
    """Reference data, read from Zetaris once at app startup and cached.

    Built by `parse.build_lexicon` from the three Q_REF results, **never from a
    file on disk** -- the hard rule is that facts reach the agents through
    Zetaris (`CLAUDE.md` rule 1). The cost is paid once per process, not once
    per run, because a reference query costs the same 4-91 s as any other
    (`docs/DECISIONS.md`, 24 Oct).

    Plain containers only, no methods: the lookup *logic* lives in `normalise.py`
    and `safety.py` where it is tested. Keys in the `by_*` maps are already
    casefolded and whitespace-collapsed by `build_lexicon`.
    """

    entries: tuple[LexiconEntry, ...] = ()
    by_pbs_code: dict[str, LexiconEntry] = dc_field(default_factory=dict)
    by_amt_code: dict[str, LexiconEntry] = dc_field(default_factory=dict)
    by_brand: dict[str, LexiconEntry] = dc_field(default_factory=dict)
    by_generic: dict[str, LexiconEntry] = dc_field(default_factory=dict)
    #: `(atc_prefix, apinchs_letter)`, longest prefix first so the first match wins.
    apinchs: tuple[tuple[str, str], ...] = ()
    #: casefolded given name -> every name it is interchangeable with, including
    #: itself. Symmetric: `nicknames["peggy"]` contains "margaret" and the reverse.
    nicknames: dict[str, frozenset[str]] = dc_field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


class IdentityLink(BaseModel):
    """One candidate pairing, with the evidence that produced the score.

    `field_evidence` exists so the UI can show *why* ("nickname Peggy~Margaret",
    "DOB day/month swap") rather than a bare number. A pharmacist cannot act on
    0.83; they can act on "same DOB, surname differs by one letter".

    `guards` records a reason the score was held back. A guard that fires pushes
    a pair to `review` even when the arithmetic says `auto-merge`, because a
    false merge mixes two patients' medicines -- the worst thing this system can
    do, and the one metric with a target of zero.
    """

    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    candidate_id: str
    match_weight: float
    probability: float = Field(ge=0.0, le=1.0)
    band: IdentityBand
    tier: IdentityTier
    field_evidence: dict[str, str] = Field(default_factory=dict)
    guards: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #


class Coverage(BaseModel):
    """Whether we found a source, and how much of it we can actually see.

    `scope_notes` carries the honest caveats -- "pharmacy_id P2 only",
    "GP list updated 14 months ago". They are what turns a confident-looking
    grid into a defensible one, and `evidence_state` reads them to decide
    whether absence means anything.
    """

    model_config = ConfigDict(extra="forbid")

    source: Source
    state: CoverageState
    scope_notes: list[str] = Field(default_factory=list)
    record_key: str | None = None
    doc_date: date | None = None


# --------------------------------------------------------------------------- #
# Medication statements
# --------------------------------------------------------------------------- #


class MedStatement(BaseModel):
    """One medicine as asserted by one source, normalised.

    `resolution` is how we got here, and it is deliberately on the record rather
    than inferred: `"llm"` and `"unmapped"` lines are shown differently in the UI
    and are never allowed to drive a high-risk finding on their own.

    `daily_dose_mg` is the *total* daily dose in canonical units, so "500mg bd"
    and "1g daily" compare equal and are never flagged as a dose discrepancy.
    """

    model_config = ConfigDict(extra="forbid")

    source: Source
    row_id: str
    raw_text: str
    generic: str | None = None
    ingredients: list[tuple[str, float | None]] = Field(default_factory=list)
    atc: str | None = None
    release: ReleaseClass = "unknown"
    route: str | None = None
    daily_dose_mg: float | None = None
    frequency: str | None = None
    prn: bool = False
    status: MedStatus = "unknown"
    doc_date: date | None = None
    resolution: Resolution = "unmapped"
    # Dispensing arithmetic needs these; null for every non-pharmacy source.
    qty: int | None = None
    days_supply: int | None = None
    pharmacy_id: str | None = None
    script_type: str | None = None
    note_text: str | None = None


# --------------------------------------------------------------------------- #
# Fusion
# --------------------------------------------------------------------------- #


class FusedValue(BaseModel):
    """The resolved value of one attribute, plus what disagreed with it.

    `abstained` is set when the winning and runner-up scores are within
    `margin`. Abstaining is a feature: "Conflict: ask patient" is a true and
    useful answer, and inventing a winner from a 0.02 margin is not.

    `dissenting` is kept even when we did resolve, so the grid can show the
    disagreement rather than hiding it behind the winner.
    """

    model_config = ConfigDict(extra="forbid")

    attribute: str
    value: str | float | None = None
    score: float = 0.0
    runner_up: str | float | None = None
    runner_up_score: float = 0.0
    margin: float = 0.0
    abstained: bool = False
    supporting: list[str] = Field(default_factory=list)
    dissenting: dict[str, str] = Field(default_factory=dict)
    row_ids: list[str] = Field(default_factory=list)


class FusedMed(BaseModel):
    """One row of the BPMH grid: a medicine, and what each source says about it."""

    model_config = ConfigDict(extra="forbid")

    generic: str
    atc: str | None = None
    high_risk_class: str | None = None
    per_source: dict[str, EvidenceState] = Field(default_factory=dict)
    attributes: dict[str, FusedValue] = Field(default_factory=dict)
    abstained: list[str] = Field(default_factory=list)
    row_ids: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


class DiscrepancyCandidate(BaseModel):
    """A candidate finding, before and after `triage.prioritise`.

    `row_ids` is mandatory in practice: `safety.safety_gate` blocks any candidate
    that cannot point at the rows it came from, because an unciteable finding is
    indistinguishable from a hallucinated one.

    `intent_status` is `documented_intentional` when a `chart_note` or
    `action_reason` explains the difference. Such items are collapsed in the UI,
    **never hidden** -- a documented reason can still be the wrong decision.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: DiscrepancyType
    generic: str
    sources_involved: list[str] = Field(default_factory=list)
    row_ids: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)
    high_risk_class: str | None = None
    severity: Severity = "low"
    intent_status: IntentStatus = "likely_unintentional"
    priority: float = 0.0
    tasks: list[str] = Field(default_factory=list)


class Notice(BaseModel):
    """A banner or task about our evidence, not about the patient's medicines."""

    model_config = ConfigDict(extra="forbid")

    type: NoticeType
    detail: str
    source: str | None = None
    generic: str | None = None
    row_ids: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    """The human-review gate's verdict on one candidate (`CLAUDE.md` rule 9).

    `blocked` means the finding is not shown as a finding at all. `needs_pharmacist`
    means it is shown, ranked, and cannot be actioned without a human tick.
    """

    model_config = ConfigDict(extra="forbid")

    decision: GateDecision
    reason: str
    required_tasks: list[str] = Field(default_factory=list)


__all__ = [
    "SOURCES",
    "FUSED_ATTRIBUTES",
    "Source",
    "TrustAttribute",
    "EvidenceState",
    "DiscrepancyType",
    "NoticeType",
    "Severity",
    "IntentStatus",
    "IdentityBand",
    "IdentityTier",
    "ReleaseClass",
    "MedStatus",
    "Resolution",
    "CoverageState",
    "SupplyStatus",
    "GateDecision",
    "SqlResult",
    "SourceRow",
    "LexiconEntry",
    "Lexicon",
    "IdentityLink",
    "Coverage",
    "MedStatement",
    "FusedValue",
    "FusedMed",
    "DiscrepancyCandidate",
    "Notice",
    "GateResult",
]
