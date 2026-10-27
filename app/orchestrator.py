"""The bounded run: Planner -> Executor -> Evaluator -> Writer, per PLAN 5.4.

    PLAN -> FIND_IDENTITY -> (NEEDS_REVIEW) -> COVERAGE -> FETCH_MEDS -> NORMALISE
    -> RESOLVE_FREE_TEXT -> FUSE -> DETECT -> PRIORITISE -> DRAFT -> VERIFY
    -> (CRITIQUE -> revise, at most MAX_AGENT_ITERATIONS) -> DONE | PARTIAL

It always returns. The Zetaris budget (`RunQueries`, 8) and `RUN_TIMEOUT_S` end a
run as `partial` with what it has; a review-band identity link pauses it as
`needs_review` until `resume()`; a Nightshift failure in live mode falls back to
the grounded template for that step, says so in the trace and the caveats, and
marks the run `partial` -- it never invents text and never hides the degradation.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any
from datetime import date
from pathlib import Path

from app.adapters.meterless import MeterlessClient, MeterlessError
from app.adapters.zetaris import QueryBudgetExceeded, RunQueries, ZetarisClient, ZetarisError, load_lexicon
from app.agents import evaluator, executor, identity_memory, planner, writer
from app.agents.base import AgentContext, RunTimeout
from app.agents.memory import RECALL_QUERY, TrustMemory
from app.engines.hmem import HMEM
from app.engines.world_model import WorldModel
from app.config import Settings, get_settings
from app.domain.packs.medtrace import coverage as cov_mod
from app.domain.packs.medtrace import queries
from app.domain.packs.medtrace.parse import rows_from_sql
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.domain.packs.medtrace.types import IdentityLink, Lexicon, SourceRow
from app.schemas import (
    AgentRecord,
    ErrorInfo,
    EvidenceItem,
    Finding,
    IdentityDecisionRequest,
    IdentityReview,
    PatientSummary,
    Recommendation,
    RunOutput,
    RunRequest,
    RunResponse,
    TrustEntry,
)
from app.tracing import LOG_DIR, Tracer

DISCLAIMER = "Synthetic data. Not medical advice. A pharmacist must confirm every item."
#: model step action -> the state-machine step its trace events belong to
_STEP_OF = {"plan": "PLAN", "resolve_free_text": "RESOLVE_FREE_TEXT", "draft": "DRAFT", "revise": "DRAFT",
            "summarise": "DRAFT", "critique": "CRITIQUE"}
#: Findings per Writer or critique call. Nightshift cuts any call at ~90 s (live, 27 Oct: the
#: critique of five findings was cut at 92 s every run), so each call carries one or two.
MODEL_BATCH = 2


def _batches(items: list, size: int = MODEL_BATCH) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]
ROLES = {"Planner": "plan the investigation", "Executor": "fetch, link, normalise, resolve free text",
         "Evaluator": "fuse, detect, gate, verify, critique", "Writer": "explain and summarise"}


class UnknownPatient(ValueError):
    pass


@dataclass
class RunState:
    run_id: str
    request: RunRequest
    anchor: SourceRow
    ctx: AgentContext
    started: float
    plan: planner.Plan | None = None
    links: list[IdentityLink] = field(default_factory=list)
    candidates: dict[str, SourceRow] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    degraded: bool = False
    running: bool = False
    memory_used: list = field(default_factory=list)
    # Finished work, kept as each stage completes, so a late timeout returns it (scan S5).
    analysis: Any = None
    findings: list = field(default_factory=list)
    summary: str | None = None
    verified: bool = False
    q3_sql: str = ""
    response: RunResponse | None = None


class Orchestrator:
    """One per process. Holds the lexicon and patient list (read once through Zetaris) and the runs."""

    def __init__(self, settings: Settings | None = None, *, llm: MeterlessClient | None = None,
                 zetaris: ZetarisClient | None = None, log_dir: Path | None = LOG_DIR,
                 world: WorldModel | None = None, hmem: HMEM | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or MeterlessClient(self.settings)
        self.zetaris = zetaris or ZetarisClient(self.settings)
        # Shared identity state across runs. Persisted under STATE_DIR live; in memory in
        # SAMPLE_MODE, so a judge's offline run never writes state.
        self.world = world or WorldModel(namespace="medtrace",
                                         storage="memory" if self.settings.sample_mode else "local",
                                         directory=self.settings.state_dir)
        self.log_dir = log_dir
        # The trust the pharmacist teaches lives in H-MEM (durable live, in memory offline).
        self.memory = TrustMemory(hmem or HMEM(persist_dir=None if self.settings.sample_mode
                                               else self.settings.state_dir / "hmem"))
        self._lex: Lexicon | None = None
        self._anchors: dict[str, SourceRow] | None = None
        self.runs: dict[str, RunState] = {}
        self.acceptance: dict[tuple[str, str], float] = {}
        #: Verdicts already applied, so a double-click or a retry cannot move trust twice (scan S31).
        self.feedback_applied: dict[tuple, Any] = {}
        self.feedback_lock = threading.Lock()
        self.last_routed_model: str | None = None

    @property
    def trust(self) -> dict[tuple[str, str], float]:
        """`(source, attribute) -> trust`, read from the H-MEM trust records."""
        return self.memory.trust()

    # -- process-level reads (Q_REF and Q0, once) ------------------------------

    @property
    def lex(self) -> Lexicon:
        if self._lex is None:
            self._lex = load_lexicon(self.zetaris)
        return self._lex

    def _load_anchors(self) -> dict[str, SourceRow]:
        if self._anchors is None:
            result, _ = self.zetaris.run(queries.q_admissions(), template_id="Q0", replay_key="admissions")
            anchors: dict[str, SourceRow] = {}
            for row in rows_from_sql(result):  # one row per chart line: dedupe on the MRN
                anchors.setdefault(row.source_patient_id, row)
            self._anchors = anchors
        return self._anchors

    def patients(self) -> list[PatientSummary]:
        """Every admitted patient live; in SAMPLE_MODE only those with a recorded run (scan S14:
        Q0 lists 200, but 187 of them would end in a replay miss)."""
        anchors = self._load_anchors().values()
        if self.settings.sample_mode:
            recorded = self.zetaris.replayable()
            anchors = [a for a in anchors if a.source_patient_id in recorded]
        return [PatientSummary(patient_id=a.source_patient_id, record_key=a.record_key, name_given=a.name_given,
                               name_family=a.name_family, dob=a.dob, sex=a.sex, admission_date=a.doc_date)
                for a in sorted(anchors, key=lambda a: a.source_patient_id)]

    # -- runs ------------------------------------------------------------------

    def start(self, request: RunRequest) -> RunResponse:
        """Create and run to the end (or to `needs_review`). The API uses `create` + `execute`."""
        return self.execute(self.create(request))

    def create(self, request: RunRequest) -> str:
        """Validate the patient and open the run. Returns its id; nothing is queried yet."""
        if not request.patient_id:
            raise UnknownPatient("patient_id is required")
        anchor = self._load_anchors().get(request.patient_id)
        if anchor is None:
            raise UnknownPatient(f"{request.patient_id} is not an admitted patient")
        if self.settings.sample_mode and request.patient_id not in self.zetaris.replayable():
            raise UnknownPatient(f"{request.patient_id} has no recorded data in SAMPLE_MODE; recorded patients: "
                                 f"{', '.join(sorted(self.zetaris.replayable()))}")
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        tracer = Tracer(run_id, settings=self.settings, log_dir=self.log_dir)
        started = time.monotonic()
        ctx = AgentContext(llm=self.llm, zetaris=RunQueries(self.zetaris), lex=self.lex, tracer=tracer,
                           as_of=anchor.doc_date or date.today(), deadline=started + self.settings.run_timeout_s)
        state = RunState(run_id=run_id, request=request, anchor=anchor, ctx=ctx, started=started)
        self.runs[run_id] = state
        tracer.emit("Planner", "start", step="START",
                    message=f"Reconciling {anchor.name_given} {anchor.name_family} ({anchor.source_patient_id}), "
                            f"admitted {anchor.doc_date}." + (" SAMPLE_MODE: recorded Zetaris data, offline "
                                                              "agents." if self.settings.sample_mode else ""))
        state.running = True
        return run_id

    def execute(self, run_id: str) -> RunResponse:
        state = self.runs[run_id]
        return self._guard(state, self._from_start if not state.links else self._from_identity)

    def resume(self, run_id: str, decision: IdentityDecisionRequest) -> RunResponse:
        self.decide(run_id, decision)
        return self.execute(run_id)

    def decide(self, run_id: str, decision: IdentityDecisionRequest) -> None:
        """Record the pharmacist's identity decision. Raises if the run is not awaiting it."""
        state = self.runs.get(run_id)
        if state is None:
            raise KeyError(run_id)
        if state.running or state.response is None or state.response.status != "needs_review":
            raise ValueError(f"{run_id} is not waiting for an identity decision")
        link = next((l for l in state.links if l.candidate_id == decision.candidate_id and l.band == "review"), None)
        if link is None:
            raise ValueError(f"{decision.candidate_id} is not awaiting review in {run_id}")
        band = "auto-merge" if decision.same_person else "new"
        state.links = [l.model_copy(update={"band": band}) if l is link else l for l in state.links]
        state.ctx.tracer.emit("Executor", "identity_decision", step="FIND_IDENTITY",
                              message=f"Pharmacist decided {decision.candidate_id} is "
                                      f"{'the same person' if decision.same_person else 'a different person'}.")
        seq = identity_memory.record_decision(self.world, state.anchor, decision.candidate_id, decision.same_person,
                                              run_id=run_id, source_name=decision.candidate_id.split(":")[0])
        state.ctx.tracer.emit("Executor", "world_model", step="FIND_IDENTITY", engine="world_model",
                              engine_op="relate",
                              message=f"World Model: decision recorded with provenance (audit seq {seq}); future "
                                      "runs for this patient reuse it.")
        # The deadline restarts: time spent waiting for a human is not run time.
        state.ctx.deadline = time.monotonic() + self.settings.run_timeout_s
        state.running = True

    def get(self, run_id: str) -> RunResponse | None:
        """The run as it stands: the final response, or a `running` snapshot with the trace so far."""
        state = self.runs.get(run_id)
        if state is None:
            return None
        if state.running or state.response is None:
            last = state.ctx.tracer.events[-1].message if state.ctx.tracer.events else "Starting."
            return self._respond(state, "running", summary=f"Running: {last}")
        return state.response

    # -- the state machine -------------------------------------------------------

    def _guard(self, state: RunState, step) -> RunResponse:
        try:
            state.running = True
            state.response = step(state)
        except (QueryBudgetExceeded, RunTimeout) as exc:
            state.ctx.tracer.emit("Evaluator", "stop", step="PARTIAL", status="partial", message=f"Stopped early: {exc}.")
            state.response = self._partial(state, exc)
        except (ZetarisError, MeterlessError, ValueError) as exc:
            state.ctx.tracer.emit("Evaluator", "error", step="ERROR", status="error", error=str(exc),
                                  message=f"Run failed: {exc}")
            state.response = self._respond(state, "error", summary=f"The run could not complete: {exc}",
                                           error=ErrorInfo(type=type(exc).__name__, message=str(exc),
                                                           recoverable=getattr(exc, "recoverable", False)))
        except Exception as exc:
            # Anything else -- a bug, an unexpected response shape -- still ends the run (scan S11).
            # Without this, a background run stayed `running` forever and the UI polled without end.
            mask = state.ctx.tracer.mask
            where = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}"
                                for f in reversed(traceback.extract_tb(exc.__traceback__)[-3:]))
            message = mask(f"{type(exc).__name__}: {exc}")
            state.ctx.tracer.emit("Evaluator", "error", step="ERROR", status="error", error=mask(f"{message} at {where}"),
                                  message=f"Run failed with an unexpected error: {message}")
            state.response = self._respond(state, "error", summary=f"The run could not complete: {message}",
                                           error=ErrorInfo(type=type(exc).__name__, message=message,
                                                           recoverable=False))
        finally:
            state.running = False
        return state.response

    def _partial(self, state: RunState, exc: Exception) -> RunResponse:
        """A run stopped by the budget or the clock keeps what it finished (scan S5).

        Before this, a timeout late in a live run returned an empty grid and no findings,
        although fusion, detection and often verification had all completed.
        """
        error = ErrorInfo(type=type(exc).__name__, message=str(exc), recoverable=True)
        if state.analysis is None:
            return self._respond(state, "partial", summary=f"Stopped early ({exc}); results are incomplete.",
                                 error=error)
        findings = [f if f.explanation else f.model_copy(update={"explanation": writer.template(f)})
                    for f in state.findings]
        if not state.verified:
            state.caveats.append("Stopped before every cited row was re-read from Zetaris: these findings are "
                                 "not re-verified. Treat them as unconfirmed.")
        summary = state.summary or writer._offline_summary(findings, state.anchor, state.analysis.banner)
        return self._respond(state, "partial", summary=f"Stopped early ({exc}). {summary}", analysis=state.analysis,
                             findings=findings, q3_sql=state.q3_sql if state.verified else "", error=error,
                             blocked=list(state.analysis.blocked))

    def _time_for_a_model_call(self, state: RunState, what: str) -> bool:
        """False when less time is left than one model call may take: don't start what can't finish."""
        if self.settings.sample_mode:
            return True
        left = state.ctx.deadline - time.monotonic()
        if left >= self.settings.meterless_timeout_s:
            return True
        agent, _, action = what.partition(" ")
        state.ctx.tracer.emit(agent.capitalize() or "Evaluator", "budget", step=_STEP_OF.get(action), status="skipped",
                              message=f"Skipped {what}: {left:.0f}s left is less than one model call "
                                      f"({self.settings.meterless_timeout_s:.0f}s); used the grounded fallback.")
        return False

    def _llm_step(self, state: RunState, name: str, call, fallback):
        """A model step with its fallback: live failures degrade, visibly, instead of failing the run.

        No model call starts with less time left than one call may take (scan S5): the
        grounded fallback runs instead, and the trace says so.
        """
        if not self._time_for_a_model_call(state, name):
            return fallback()
        try:
            return call()
        except MeterlessError as exc:
            if self.settings.sample_mode:
                raise
            state.degraded = True
            caveat = (f"Nightshift unavailable for {name} ({exc.kind}); the affected items used the grounded "
                      "template and are labelled offline-heuristic.")
            if caveat not in state.caveats:  # batched steps can fail more than once
                state.caveats.append(caveat)
            agent, action = name.split()
            # Every request the failure spent is a model call: in model_calls and the trace, with
            # the model that answered where there was one (scan S9, CLAUDE.md rule 3).
            state.ctx.record(agent.capitalize(), action, _STEP_OF.get(action), exc.calls,  # type: ignore[arg-type]
                             f"{name}: request failed ({exc.kind}).")
            state.ctx.tracer.emit(agent.capitalize(), "fallback", step=_STEP_OF.get(action), status="degraded",
                                  error=str(exc),
                                  message=f"{name}: Nightshift failed ({exc.kind}); used the grounded template.")
            return fallback()

    def _from_start(self, state: RunState) -> RunResponse:
        ctx = state.ctx
        budget_left = ctx.zetaris.budget - ctx.zetaris.used
        state.memory_used = self.memory.recall(RECALL_QUERY)
        ctx.tracer.emit("Planner", "recall", step="PLAN", engine="hmem", engine_op="query",
                        memory_ids=[m.memory_id for m in state.memory_used],
                        message=f"H-MEM recalled {len(state.memory_used)} memories for the plan"
                                + (": " + "; ".join(f"{m.content} ({m.score})" for m in state.memory_used[:3])
                                   if state.memory_used else "."))
        memory_context = "\n".join(f"- {m.content} (confidence-weighted score {m.score})" for m in state.memory_used)
        state.plan = self._llm_step(state, "planner plan",
                                    lambda: planner.plan(ctx, state.anchor, executor.catalogue(), budget_left,
                                                         memory_context),
                                    lambda: planner._offline_plan(state.anchor, budget_left))
        self._route(state, "find_identities")
        state.links, state.candidates = executor.find_identities(ctx, state.anchor)
        state.links, notes = identity_memory.remembered(self.world, state.anchor, state.links)
        for note in notes:
            ctx.tracer.emit("Executor", "world_model", step="FIND_IDENTITY", engine="world_model",
                            engine_op="neighborsOf", message=f"World Model remembers: {note}; not asking again.")
        q1 = next((r.query_id for r in reversed(ctx.zetaris.records) if r.template_id == "Q1"), None)
        summary = identity_memory.record_links(self.world, state.anchor, state.links, state.candidates,
                                               run_id=state.run_id, query_id=q1)
        first, last = summary["audit"]
        ctx.tracer.emit("Executor", "world_model", step="FIND_IDENTITY", engine="world_model", engine_op="upsert+relate",
                        message=f"World Model: recorded {summary['records']} patient records and {summary['edges']} "
                                f"same-person link(s), each with provenance (Zetaris query {q1}); audit seq "
                                f"{first}-{last}.")
        return self._from_identity(state)

    def _planned(self, state: RunState, tool: str) -> bool:
        return state.plan is None or tool in state.plan.tools

    def _route(self, state: RunState, tool: str) -> None:
        """Trace the hand-off: the Planner's need -> the template the Executor fills -> Zetaris."""
        need = state.plan.need(tool) if state.plan else planner.DEFAULT_NEED[tool]
        template = planner.TEMPLATE_FOR[tool]
        how = (f"the Executor runs verified query {template} on Zetaris, read-only" if template else
               "matched against the medicines lexicon, with Nemotron choosing only from a closed list; no SQL")
        step = {"find_identities": "FIND_IDENTITY"}.get(tool, tool.upper())
        state.ctx.tracer.emit("Executor", "route", step=step, message=f'Planner need "{need}" -> {how}.')

    def _from_identity(self, state: RunState) -> RunResponse:
        ctx = state.ctx
        pending = [l for l in state.links if l.band == "review"]
        if pending:
            cov = self._link_coverage(state)
            ctx.tracer.emit("Executor", "needs_review", step="NEEDS_REVIEW", status="waiting",
                            message=f"Paused: {len(pending)} identity near-miss(es) need your confirmation.")
            return self._needs_review(state, pending, cov)

        # Whose medicines to read comes from the World Model's graph: the anchor plus every
        # record with an open same-person edge (score-decided or pharmacist-decided).
        keys = identity_memory.linked_record_keys(self.world, state.anchor)
        linked = [l for l in state.links if l.band == "auto-merge" and l.candidate_id in keys]
        ctx.tracer.emit("Executor", "world_model", step="FETCH_MEDS", engine="world_model", engine_op="neighborsOf",
                        message=f"Linked set read from the World Model graph: {', '.join(sorted(keys))}.")
        self._route(state, "fetch_meds")
        rows, raw, _ = executor.fetch_meds(ctx, state.anchor, linked)
        q2_id = ctx.zetaris.records[-1].query_id
        stmts = executor.normalise(ctx, rows)
        extra_tasks: list[str] = []
        if self._planned(state, "resolve_free_text"):
            self._route(state, "resolve_free_text")
            stmts, extra_tasks = self._llm_step(state, "executor resolve_free_text",
                                                lambda: executor.resolve_free_text(ctx, stmts),
                                                lambda: (stmts, []))
        analysis = evaluator.analyse(ctx, state.links, rows, stmts, raw, q2_id, self.trust, self.acceptance)
        if extra_tasks:
            analysis.tasks = list(dict.fromkeys([*analysis.tasks, *extra_tasks]))
        if self._planned(state, "check_shortages"):
            self._route(state, "check_shortages")
            shortages = executor.check_shortages(ctx, state.anchor,
                                                 sorted({m.generic for m in analysis.fused if evaluator.is_current(m)}),
                                                 stmts, raw)
            if shortages:  # said once for the run, not on every notice (scan S42)
                state.caveats.append(executor.SHORTAGE_DISCLAIMER)
            analysis.notices = [*analysis.notices, *shortages]
            analysis.tasks = list(dict.fromkeys([*analysis.tasks, *(t for n in shortages for t in n.tasks)]))
        findings = [f.model_copy(update={"hmem_record_ids": self._hmem_ids(f), "explanation": writer.template(f)})
                    for f in analysis.findings]
        state.analysis, state.findings = analysis, findings

        # Small batches, each its own model call (27 Oct: Nightshift cuts any call at ~90 s). A
        # batch that fails loses only its own explanations, which fall back to the template.
        texts: dict[str, str] = {}
        for batch in _batches(findings):
            drafted, _ = self._llm_step(
                state, "writer draft",
                lambda b=batch: writer.draft(ctx, b, state.anchor, analysis.banner, with_summary=False),
                lambda b=batch: ({f.id: writer.template(f) for f in b}, None))
            texts.update(drafted)
        findings = [f.model_copy(update={"explanation": texts.get(f.id) or writer.template(f)}) for f in findings]
        summary = self._llm_step(state, "writer summarise",
                                 lambda: writer.summarise(ctx, findings, state.anchor, analysis.banner),
                                 lambda: writer._offline_summary(findings, state.anchor, analysis.banner))
        summary = self._checked_summary(state, summary, findings, analysis.banner)
        state.findings, state.summary = findings, summary

        self._route(state, "verify")
        findings, blocked, q3_sql = evaluator.verify(ctx, findings, state.anchor)
        state.findings, state.verified, state.q3_sql = findings, True, q3_sql
        if blocked:  # the summary may describe a finding that verification just removed
            summary = state.summary = self._checked_summary(state, summary, findings, analysis.banner)

        rounds = max(1, self.settings.max_agent_iterations)
        to_check = findings  # round 1 reads every explanation; later rounds only the revised ones
        for round_no in range(1, rounds + 1):
            problems: dict[str, list[str]] = {}
            for batch in _batches(to_check):
                problems.update(self._llm_step(
                    state, "evaluator critique", lambda b=batch: evaluator.critique(ctx, b),
                    lambda b=batch: {f.id: p for f in b if (p := evaluator.claim_problems(f))}))
            if not problems:
                break
            if round_no == rounds:
                # Anything still under objection after the last round -- from the code checks or the
                # model's per-finding verdict -- is replaced with the grounded template. Live, 25 Oct:
                # "esomeprazole 40 mg 1 bd (once daily)" passed every number check and was still
                # wrong; the model verdict caught it. Prose loses to safety.
                for fid, issues in problems.items():
                    ctx.tracer.emit("Evaluator", "verify", step="VERIFY", status="blocked",
                                    message=f"Verifier blocked an unsupported claim in {fid}: {'; '.join(issues)[:300]}. "
                                            "Replaced with the grounded template.")
                findings = [f.model_copy(update={"explanation": writer.template(f)}) if f.id in problems else f
                            for f in findings]
                break
            ctx.tracer.emit("Evaluator", "critique", step="CRITIQUE",
                            message=f"Round {round_no}: sending {len(problems)} explanation(s) back to the Writer.")
            revised: dict[str, str] = {}
            for batch in _batches([f for f in findings if f.id in problems]):
                fixed, _ = self._llm_step(
                    state, "writer revise",
                    lambda b=batch: writer.draft(ctx, b, state.anchor, analysis.banner,
                                                 problems={f.id: problems[f.id] for f in b}),
                    lambda b=batch: ({f.id: writer.template(f) for f in b}, None))
                revised.update(fixed)
            findings = [f.model_copy(update={"explanation": revised.get(f.id, f.explanation)}) for f in findings]
            to_check = [f for f in findings if f.id in problems]
            state.findings = findings

        state.findings = findings
        status = "partial" if state.degraded else "success"
        ctx.tracer.emit("Writer", "done", step="PARTIAL" if state.degraded else "DONE",
                        message=f"Done: {len(findings)} findings, {len(analysis.notices)} notices, "
                                f"{len(analysis.tasks)} tasks.")
        return self._respond(state, status, summary=summary, analysis=analysis, findings=findings, q3_sql=q3_sql,
                             blocked=[*analysis.blocked, *blocked])

    @staticmethod
    def _checked_summary(state: RunState, summary: str | None, findings: list[Finding],
                         banner: str | None) -> str | None:
        """Scan S10: the summary is the UI's headline, so it gets the same code checks as an
        explanation. One that fails is replaced with the grounded summary, never shown."""
        if not summary:
            return summary
        issues = evaluator.summary_problems(summary, findings, state.anchor, banner)
        if not issues:
            return summary
        state.ctx.tracer.emit("Evaluator", "verify", step="VERIFY", status="blocked",
                              message=f"Verifier blocked the Writer's summary: {'; '.join(issues)[:300]}. "
                                      "Replaced with the grounded summary.")
        return writer._offline_summary(findings, state.anchor, banner)

    @staticmethod
    def _recommendation(f: Finding) -> Recommendation:
        """One per ranked finding, in triage order (scan S16).

        `confidence` is triage's evidence strength for the finding -- 0.6 plus 0.2 per
        independent pre-admission source it cites, capped at 1 (`triage.prioritise`) --
        not a constant. Tasks from notices carry no such measure, so they stay in
        `RunResponse.tasks` rather than appearing here with an invented number.
        """
        independent = {e.source for e in f.evidence if e.source and e.source != "emr"}
        return Recommendation(text=f.tasks[0] if f.tasks else f"Review {f.generic} ({f.type.value.replace('_', ' ')})",
                              rationale=f.explanation or None, confidence=min(1.0, 0.6 + 0.2 * len(independent)),
                              requires_human_review=True)

    def _hmem_ids(self, f: Finding) -> list[str]:
        """The H-MEM trust records a verdict on this finding would move (feedback, PLAN 5.7)."""
        from app.feedback import _attribute_for
        attribute = _attribute_for(f)
        sources = sorted({e.source for e in f.evidence if e.source} - {"emr"})
        return [mid for s in sources if (mid := self.memory.record_id(s, attribute))]

    # -- response assembly -------------------------------------------------------

    @staticmethod
    def _link_coverage(state: RunState) -> dict:
        """Coverage before any medicine rows are read: from the links alone.

        `coverage.coverage()` needs Q2's rows, which a paused run has not fetched, and
        would report every source as not found. Here the anchor's EMR record is found,
        a source with an auto-merge link is found, one with a review-band link is
        `near_miss_pending`, and the rest are `not_found`.
        """
        from app.domain.packs.medtrace.types import SOURCES, Coverage
        out: dict[str, Coverage] = {"emr": Coverage(source="emr", state="found", record_key=state.anchor.record_key,
                                                    doc_date=state.anchor.doc_date)}
        for source in SOURCES:
            if source == "emr":
                continue
            mine = [l for l in state.links if l.candidate_id.startswith(f"{source}:")]
            merged = next((l for l in mine if l.band == "auto-merge"), None)
            if merged is not None:
                out[source] = Coverage(source=source, state="found", record_key=merged.candidate_id)
            elif any(l.band == "review" for l in mine):
                out[source] = Coverage(source=source, state="near_miss_pending",
                                       scope_notes=[cov_mod._IDENTITY_PENDING_NOTE])
            else:
                out[source] = Coverage(source=source, state="not_found")
        return out

    def _needs_review(self, state: RunState, pending: list[IdentityLink], cov) -> RunResponse:
        # The side-by-side view uses the identity step's own Q1 rows: no extra query.
        rows = {l.candidate_id: state.candidates[l.candidate_id] for l in state.links
                if l.candidate_id in state.candidates}
        confirmable, banner = cov_mod.bpmh_confirmable(cov)
        resp = self._respond(state, "needs_review",
                             summary=f"Waiting for identity review: {len(pending)} near-miss record(s).",
                             coverage=cov, banner=banner or None, confirmable=confirmable)
        resp.identity_review = IdentityReview(anchor=state.anchor, candidates=pending, records=rows)
        return resp

    def _respond(self, state: RunState, status: str, *, summary: str | None = None, analysis=None,
                 findings: list[Finding] | None = None, q3_sql: str = "", blocked: list[str] | None = None,
                 coverage=None, banner: str | None = None, confirmable: bool = False,
                 error: ErrorInfo | None = None) -> RunResponse:
        ctx = state.ctx
        calls = ctx.model_calls
        live = [c.routed_model for c in calls if c.routed_model and c.routed_model != "offline-heuristic"]
        if live:
            self.last_routed_model = live[-1]
        findings = findings or []
        caveats = [DISCLAIMER, *state.caveats]
        if self.settings.sample_mode:
            caveats.append("SAMPLE_MODE: recorded Zetaris data and offline-heuristic agents; no model was called.")
        if blocked:
            caveats.append(f"{len(blocked)} candidate finding(s) were blocked by verification or the safety gate.")
        agents = []
        for name, role in ROLES.items():
            mine = [c for c in calls if c.role == name]
            agents.append(AgentRecord(name=name, role=role, iterations=len(mine),
                                      models_used=sorted({c.routed_model for c in mine if c.routed_model}),
                                      routes_requested=sorted({c.requested_route for c in mine})))
        evidence_index = {e.row_id: e for f in findings for e in f.evidence}
        if analysis is not None:
            coverage, banner, confirmable = analysis.cov, analysis.banner, analysis.bpmh_confirmable
            evidence_index = {**analysis.grid_evidence, **analysis.notice_evidence, **evidence_index}
        return RunResponse(
            run_id=state.run_id, status=status,  # type: ignore[arg-type]
            output=RunOutput(
                summary=summary or "",
                recommendations=[self._recommendation(f) for f in findings[:5]],
                evidence=[EvidenceItem(claim=f.explanation, sql=q3_sql, source=queries.ALL_SOURCES_VIEW,
                                       row_count=len(f.evidence), verified=True) for f in findings if q3_sql],
                caveats=caveats),
            agents=agents, trace_id=state.run_id, log_file=ctx.tracer.log_file,
            execution_time_seconds=round(time.monotonic() - state.started, 2), error=error,
            sample_mode=self.settings.sample_mode,
            provider_state="sample_mode" if self.settings.sample_mode else ("online" if live else None),
            patient_id=state.anchor.source_patient_id, coverage=coverage or {}, bpmh_confirmable=confirmable,
            banner=banner, grid=analysis.fused if analysis else [],
            dose_units=analysis.dose_units if analysis else {}, findings=findings,
            notices=analysis.notices if analysis else [], tasks=analysis.tasks if analysis else [],
            evidence_index=evidence_index,
            trust=[TrustEntry(source=s, attribute=a, value=v, hmem_record_id=self.memory.record_id(s, a))
                   for (s, a), v in sorted(self.trust.items())],
            memory_used=list(state.memory_used),
            trace=list(ctx.tracer.events), query_count=ctx.zetaris.used, zetaris_ms=ctx.zetaris.zetaris_ms,
            model_calls=list(calls),
        )
