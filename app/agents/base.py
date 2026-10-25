"""What every agent works with: the adapters, the lexicon, the trace, the clock.

Agents are thin on purpose. The clinical decisions -- linkage, coverage,
fusion, detection, the safety gate, ranking -- are Arpon's deterministic code in
`app/domain/packs/medtrace/`. The agents do what PLAN 2.5 gives them: plan the
investigation, fetch through Zetaris, resolve free text from a closed candidate
list, verify claims against the rows, and explain. Every model call goes through
`MeterlessClient` and is recorded as a `ModelCall` with the model that answered.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

from app.adapters.meterless import ChatResult, MeterlessClient
from app.adapters.zetaris import RunQueries
from app.domain.packs.medtrace.types import Lexicon
from app.schemas import ModelCall
from app.tracing import Tracer


class RunTimeout(RuntimeError):
    """`RUN_TIMEOUT_S` is spent. The orchestrator returns `partial` with what it has."""


@dataclass
class AgentContext:
    llm: MeterlessClient
    zetaris: RunQueries
    lex: Lexicon
    tracer: Tracer
    as_of: date
    deadline: float
    model_calls: list[ModelCall] = field(default_factory=list)

    def record(self, agent: str, action: str, step: str, calls: list[ChatResult], message: str) -> None:
        """Log model calls: one `ModelCall` each, and a trace event naming the model that answered."""
        for call in calls:
            self.model_calls.append(call.model_call())
            self.tracer.emit(agent, action, step=step, message=message, **call.trace_fields())

    def check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise RunTimeout("RUN_TIMEOUT_S reached")
