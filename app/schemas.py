"""Wire contracts: run request/response, trace events, errors.

The output schema follows the hackathon's official shape so a judge can read it
without a guide. Extra fields are additive, never renames.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["success", "partial", "error"]
AgentName = Literal["Planner", "Executor", "Evaluator", "Writer"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    """What a caller asks for. One question, optional knobs."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=2000)
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


class HealthResponse(BaseModel):
    status: str
    sample_mode: bool
    domain_pack: str
    zetaris: str
    meterless: str
    meterless_routes: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    """Thumbs from the UI, feeding the H-MEM trust ledger."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    kind: Literal["helpful", "not_helpful", "wrong"]
    run_id: str | None = None
