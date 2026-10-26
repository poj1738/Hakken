"""Wire contracts: run request/response, trace events, errors.

The output schema follows the hackathon's official shape so a judge can read it
without a guide. Extra fields are additive, never renames.

The MedTrace fields (PLAN 2.8) reuse the frozen domain types from
`app.domain.packs.medtrace.types` rather than redefining them, so the API, the
clinical code and `web/src/types.ts` cannot drift apart. Every MedTrace field
has a default, so a run that never reached a stage still validates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.packs.medtrace.types import (
    Coverage,
    DiscrepancyType,
    EvidenceState,
    FusedMed,
    IdentityLink,
    IntentStatus,
    Notice,
    Severity,
    Source,
    SourceRow,
    TrustAttribute,
)

# `success` / `partial` / `error` are the official values and the only ones a
# finished run reports. `running` is a mid-run poll of `GET /run/{id}`;
# `needs_review` is a run paused on a review-band identity link until
# `POST /run/{id}/identity` resumes it (PLAN 5.5, 6.4).
RunStatus = Literal["success", "partial", "error", "running", "needs_review"]
AgentName = Literal["Planner", "Executor", "Evaluator", "Writer"]

FeedbackVerdict = Literal["confirm", "reject"]
FeedbackReason = Literal[
    "wrong_patient",
    "source_outdated",
    "intentional_change",
    "not_clinically_relevant",
    "already_known",
    "other",
]
# The H-MEM feedback kinds a verdict maps to (PLAN 5.7).
HmemFeedbackKind = Literal["helpful", "not_helpful", "wrong"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    """What a caller asks for: one patient, optional knobs."""

    model_config = ConfigDict(extra="forbid")

    # The EMR `source_patient_id` of the admitted patient, e.g. "MRN0000001" --
    # never a ground-truth key like "P0001", which exists only for evaluation.
    patient_id: str | None = Field(default=None, min_length=1, max_length=64)
    question: str = Field(
        default="Reconcile this patient's pre-admission medicines.",
        min_length=3,
        max_length=2000,
    )
    domain_pack: str | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=10)
    sample_mode: bool | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    """One cited fact, traceable to the SQL that produced it.

    `sql` and `source` are mandatory: an evidence row the Evaluator cannot
    re-derive is not evidence, and the Writer is blocked from citing it.
    """

    claim: str
    value: str | float | int | None = None
    unit: str | None = None
    sql: str
    source: str
    row_count: int | None = None
    verified: bool = False
    world_model_entity_id: str | None = None


class Recommendation(BaseModel):
    text: str
    rationale: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_human_review: bool = False


class MemoryUsed(BaseModel):
    """An H-MEM record that was reinjected, with why it was chosen."""

    memory_id: str
    content: str
    layer: str
    score: float
    retrieval_reason: str | None = None


class RunOutput(BaseModel):
    summary: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class AgentRecord(BaseModel):
    """What one agent did, for the `agents[]` array of the response."""

    name: str
    role: str
    iterations: int = 0
    # The model that actually answered, from meterless.routed_model - never the
    # route we asked for. See docs/DECISIONS.md.
    models_used: list[str] = Field(default_factory=list)
    routes_requested: list[str] = Field(default_factory=list)
    status: str = "ok"


class ErrorInfo(BaseModel):
    type: str
    message: str
    recoverable: bool = False


# --------------------------------------------------------------------------- #
# MedTrace: evidence, findings, identity review (PLAN 2.8)
# --------------------------------------------------------------------------- #


class Evidence(BaseModel):
    """One source row a finding or grid cell rests on, as Zetaris returned it.

    `fields` keeps the values exactly as they came back -- strings, uncast --
    so the UI can show the original text. A SQL NULL stays `None` and is never
    stringified to "None" (`REFERENCE_NOTES` 1.1).
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    row_id: str
    sql_template_id: str
    query_id: str | None = None
    fields: dict[str, str | None] = Field(default_factory=dict)


class Finding(BaseModel):
    """One ranked discrepancy, as shown in the flags list.

    Built from a `DiscrepancyCandidate` after `prioritise` and `safety_gate`,
    plus the Writer's explanation. `id` is the `target_id` feedback refers to.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: DiscrepancyType
    generic: str
    high_risk_class: str | None = None
    severity: Severity = "low"
    intent_status: IntentStatus = "likely_unintentional"
    # Why a documented_intentional item is collapsed (chart_note / action_reason).
    intent_reason: str | None = None
    priority: float = 0.0
    # The Writer's 1-2 sentences, citing row_ids. Never says "not taking" for UNKNOWN.
    explanation: str = ""
    # Passed through from `DiscrepancyCandidate.detail`. Carries `atc_class` (the
    # 4-character ATC subgroup that keys feedback acceptance and `prioritise`),
    # and what the UI must render: `conflict: "confirm"` (ask first, never "stop
    # this medicine"), `bpmh_single_source`, `subtype`, `statement`,
    # `daily_dose_ratio`.
    detail: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_states: dict[str, EvidenceState] = Field(default_factory=dict)
    tasks: list[str] = Field(default_factory=list)
    needs_pharmacist: bool = False
    trust_explanation: list[str] = Field(default_factory=list)
    hmem_record_ids: list[str] = Field(default_factory=list)


class IdentityReview(BaseModel):
    """A run paused on review-band links, shown side by side in the UI.

    `records` maps each `record_key` ("gp:GP004411") in `candidates` to its row,
    so the UI can lay the demographics side by side without a second request.
    """

    model_config = ConfigDict(extra="forbid")

    anchor: SourceRow
    candidates: list[IdentityLink] = Field(default_factory=list)
    records: dict[str, SourceRow] = Field(default_factory=dict)


class IdentityDecisionRequest(BaseModel):
    """`POST /run/{id}/identity`: the pharmacist's call on one candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=128)
    same_person: bool


class ModelCall(BaseModel):
    """One Nightshift call. `routed_model` is what answered, not what we asked for."""

    model_config = ConfigDict(extra="forbid")

    role: AgentName
    requested_route: str
    routed_model: str | None = None
    request_id: str | None = None
    tokens: dict[str, int] = Field(default_factory=dict)
    # completion_tokens == max_tokens; `finish_reason` cannot be trusted (DECISIONS, 24 Oct).
    truncated: bool = False


class TrustEntry(BaseModel):
    """One (source, attribute) trust value, for the trust panel."""

    model_config = ConfigDict(extra="forbid")

    source: str
    attribute: str
    value: float = Field(ge=0.0, le=1.0)
    uncertainty: float | None = Field(default=None, ge=0.0)
    hmem_record_id: str | None = None


class PatientSummary(BaseModel):
    """One admitted patient for the picker, from Q0 (`q_admissions`)."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str
    record_key: str
    name_given: str | None = None
    name_family: str | None = None
    dob: date | None = None
    sex: str | None = None
    admission_date: date | None = None


class PatientsResponse(BaseModel):
    patients: list[PatientSummary] = Field(default_factory=list)


class TraceEvent(BaseModel):
    """One JSONL line in logs/trace-<run_id>.jsonl.

    The first block is the hackathon's official field set; the rest is ours.
    """

    model_config = ConfigDict(extra="allow")

    timestamp: str = Field(default_factory=_utc_now)
    run_id: str
    agent_name: str
    action: str
    input_summary: str | None = None
    output_summary: str | None = None
    target_agent: str | None = None
    model: str | None = None
    confidence: float | None = None
    retry_count: int = 0
    status: str = "ok"

    # -- our extensions --
    # Orchestrator state ("FIND_IDENTITY", "VERIFY", ...) and the plain-English
    # line the UI timeline shows, e.g. "Found Peggy Smyth in pharmacy: nickname
    # + DOB swap, 0.83, needs your confirmation".
    step: str | None = None
    message: str | None = None
    route: str | None = None
    latency_ms: int | None = None
    tokens: dict[str, Any] | None = None
    sql: str | None = None
    row_count: int | None = None
    engine: str | None = None
    engine_op: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    # The whole meterless compute receipt, flattened to the fields we rely on.
    meterless: dict[str, Any] | None = None


class RunResponse(BaseModel):
    """The official response shape, plus our additive fields."""

    run_id: str
    status: RunStatus
    output: RunOutput
    agents: list[AgentRecord] = Field(default_factory=list)
    trace_id: str
    log_file: str
    execution_time_seconds: float
    error: ErrorInfo | None = None
    # Additive: judges asked to see memory influence and the provider state.
    memory_used: list[MemoryUsed] = Field(default_factory=list)
    sample_mode: bool = False
    provider_state: str | None = None

    # -- MedTrace (PLAN 2.8) --
    patient_id: str | None = None
    coverage: dict[str, Coverage] = Field(default_factory=dict)
    bpmh_confirmable: bool = False
    banner: str | None = None
    grid: list[FusedMed] = Field(default_factory=list)
    # Additive (26 Oct, Anshu's ask): generic -> unit of the grid's resolved `daily_dose`
    # ("mg", "units" or "mL"; masses are converted to mg). Absent where the cited rows state
    # no unit or disagree -- the UI then shows the number unlabelled rather than guessing.
    dose_units: dict[str, str] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    identity_review: IdentityReview | None = None
    # Every row cited by a finding or a grid cell, keyed by row_id, so a cell's
    # hover can show its source, original text and SQL template.
    evidence_index: dict[str, Evidence] = Field(default_factory=dict)
    trust: list[TrustEntry] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    query_count: int = Field(default=0, ge=0)
    zetaris_ms: int = Field(default=0, ge=0)
    model_calls: list[ModelCall] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """`GET /status`: what the header's status pill shows."""

    status: str
    sample_mode: bool
    domain_pack: str
    zetaris: str
    meterless: str
    meterless_routes: list[str] = Field(default_factory=list)
    # The Nemotron that answered most recently, from meterless.routed_model.
    last_routed_model: str | None = None


class FeedbackRequest(BaseModel):
    """`POST /feedback`: a pharmacist's verdict on a finding or fused attribute.

    A reject must say why, because the reason decides the H-MEM delta
    (PLAN 5.7); a confirm carries no reason. `source_outdated` must also name
    the outdated `(source, attribute)`, because the -0.20 lands on exactly that
    H-MEM record -- e.g. `("gp", "daily_dose")` in the learning demo.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=256)
    verdict: FeedbackVerdict
    reason: FeedbackReason | None = None
    source: Source | None = None
    attribute: TrustAttribute | None = None

    @model_validator(mode="after")
    def _reason_matches_verdict(self) -> FeedbackRequest:
        if self.verdict == "reject" and self.reason is None:
            raise ValueError("a reject needs a reason")
        if self.verdict == "confirm" and self.reason is not None:
            raise ValueError("a confirm carries no reason")
        if self.reason == "source_outdated" and (self.source is None or self.attribute is None):
            raise ValueError("source_outdated needs the outdated source and attribute")
        return self


class TrustUpdate(BaseModel):
    """One H-MEM record moved by a verdict, before and after."""

    model_config = ConfigDict(extra="forbid")

    source: str
    attribute: str
    hmem_record_id: str
    kind: HmemFeedbackKind
    before: float
    after: float
    delta: float


class AcceptanceUpdate(BaseModel):
    """`intentional_change` / `not_clinically_relevant` feed `prioritise`'s acceptance rate."""

    model_config = ConfigDict(extra="forbid")

    type: DiscrepancyType
    atc_class: str
    before: float
    after: float


class FeedbackResponse(BaseModel):
    run_id: str
    target_id: str
    verdict: FeedbackVerdict
    reason: FeedbackReason | None = None
    trust_updates: list[TrustUpdate] = Field(default_factory=list)
    acceptance_updates: list[AcceptanceUpdate] = Field(default_factory=list)
