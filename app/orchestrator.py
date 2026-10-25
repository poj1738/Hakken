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

import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.adapters.meterless import MeterlessClient, MeterlessError
from app.adapters.zetaris import QueryBudgetExceeded, RunQueries, ZetarisClient, ZetarisError, load_lexicon
from app.agents import evaluator, executor, planner, writer
from app.agents.base import AgentContext, RunTimeout
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
    response: RunResponse | None = None


class Orchestrator:
    """One per process. Holds the lexicon and patient list (read once through Zetaris) and the runs."""

    def __init__(self, settings: Settings | None = None, *, llm: MeterlessClient | None = None,
                 zetaris: ZetarisClient | None = None, log_dir: Path | None = LOG_DIR) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or MeterlessClient(self.settings)
        self.zetaris = zetaris or ZetarisClient(self.settings)
        self.log_dir = log_dir
        self._lex: Lexicon | None = None
        self._anchors: dict[str, SourceRow] | None = None
        self.runs: dict[str, RunState] = {}
        self.trust: dict[tuple[str, str], float] = dict(SOURCE_TRUST_PRIORS)
        self.acceptance: dict[tuple[str, str], float] = {}
        self.last_routed_model: str | None = None

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
        return [PatientSummary(patient_id=a.source_patient_id, record_key=a.record_key, name_given=a.name_given,
                               name_family=a.name_family, dob=a.dob, sex=a.sex, admission_date=a.doc_date)
                for a in sorted(self._load_anchors().values(), key=lambda a: a.source_patient_id)]

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
            state.response = self._respond(state, "partial", summary=f"Stopped early ({exc}); results are incomplete.",
                                           error=ErrorInfo(type=type(exc).__name__, message=str(exc), recoverable=True))
        except (ZetarisError, MeterlessError, ValueError) as exc:
            state.ctx.tracer.emit("Evaluator", "error", step="ERROR", status="error", error=str(exc),
                                  message=f"Run failed: {exc}")
            state.response = self._respond(state, "error", summary=f"The run could not complete: {exc}",
                                           error=ErrorInfo(type=type(exc).__name__, message=str(exc),
                                                           recoverable=getattr(exc, "recoverable", False)))
        finally:
            state.running = False
        return state.response

    def _llm_step(self, state: RunState, name: str, call, fallback):
        """A model step with its fallback: live failures degrade, visibly, instead of failing the run."""
        try:
            return call()
        except MeterlessError as exc:
            if self.settings.sample_mode:
                raise
            state.degraded = True
            state.caveats.append(f"Nightshift unavailable for {name} ({exc.kind}); that step used the grounded "
                                 "template and is labelled offline-heuristic.")
            agent, action = name.split()
            step = {"plan": "PLAN", "resolve_free_text": "RESOLVE_FREE_TEXT", "draft": "DRAFT",
                    "revise": "DRAFT", "critique": "CRITIQUE"}.get(action)
            state.ctx.tracer.emit(agent.capitalize(), "fallback", step=step, status="degraded", error=str(exc),
                                  message=f"{name}: Nightshift failed ({exc.kind}); used the grounded template.")
            return fallback()

    def _from_start(self, state: RunState) -> RunResponse:
        ctx = state.ctx
        budget_left = ctx.zetaris.budget - ctx.zetaris.used
        state.plan = self._llm_step(state, "planner plan",
                                    lambda: planner.plan(ctx, state.anchor, executor.catalogue(), budget_left),
                                    lambda: planner._offline_plan(state.anchor, budget_left))
        self._route(state, "find_identities")
        state.links, state.candidates = executor.find_identities(ctx, state.anchor)
        return self._from_identity(state)

    def _planned(self, state: RunState, tool: str) -> bool:
        return state.plan is None or tool in state.plan.tools

    def _route(self, state: RunState, tool: str) -> None:
        """Trace the hand-off: the Planner's need -> the template the Executor fills -> Zetaris."""
        need = state.plan.need(tool) if state.plan else planner.DEFAULT_NEED[tool]
        template = planner.TEMPLATE_FOR[tool]
        how = (f"the Executor fills template {template} and the Zetaris adapter sends it (read-only check, "
               "Bearer key, X-Org-ID, fresh X-Request-ID)" if template else "the lexicon plus one Nemotron "
               "choice from a closed candidate list; no SQL")
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

        self._route(state, "fetch_meds")
        rows, raw, _ = executor.fetch_meds(ctx, state.anchor, state.links)
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
                                                 sorted({m.generic for m in analysis.fused if evaluator.is_current(m)}))
            analysis.notices = [*analysis.notices, *shortages]
            analysis.tasks = list(dict.fromkeys([*analysis.tasks, *(t for n in shortages for t in n.tasks)]))
        findings = analysis.findings

        texts, summary = self._llm_step(
            state, "writer draft", lambda: writer.draft(ctx, findings, state.anchor, analysis.banner),
            lambda: ({f.id: writer.template(f) for f in findings},
                     writer._offline_summary(findings, state.anchor, analysis.banner)))
        findings = [f.model_copy(update={"explanation": texts.get(f.id) or writer.template(f)}) for f in findings]

        self._route(state, "verify")
        findings, blocked, q3_sql = evaluator.verify(ctx, findings, state.anchor)

        rounds = max(1, self.settings.max_agent_iterations)
        for round_no in range(1, rounds + 1):
            problems = self._llm_step(state, "evaluator critique", lambda: evaluator.critique(ctx, findings),
                                      lambda: {f.id: p for f in findings if (p := evaluator.claim_problems(f))})
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
            revised, _ = self._llm_step(state, "writer revise",
                                        lambda: writer.draft(ctx, findings, state.anchor, analysis.banner,
                                                             problems=problems),
                                        lambda: ({fid: writer.template(f) for f in findings
                                                  if (fid := f.id) in problems}, None))
            findings = [f.model_copy(update={"explanation": revised.get(f.id, f.explanation)}) for f in findings]

        status = "partial" if state.degraded else "success"
        ctx.tracer.emit("Writer", "done", step="PARTIAL" if state.degraded else "DONE",
                        message=f"Done: {len(findings)} findings, {len(analysis.notices)} notices, "
                                f"{len(analysis.tasks)} tasks.")
        return self._respond(state, status, summary=summary, analysis=analysis, findings=findings, q3_sql=q3_sql,
                             blocked=[*analysis.blocked, *blocked])

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
                                       scope_notes=["waiting for identity review"])
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
        return RunResponse(
            run_id=state.run_id, status=status,  # type: ignore[arg-type]
            output=RunOutput(
                summary=summary or "",
                recommendations=[Recommendation(text=t, requires_human_review=True)
                                 for t in (analysis.tasks[:5] if analysis else [])],
                evidence=[EvidenceItem(claim=f.explanation, sql=q3_sql, source=queries.ALL_SOURCES_VIEW,
                                       row_count=len(f.evidence), verified=True) for f in findings if q3_sql],
                caveats=caveats),
            agents=agents, trace_id=state.run_id, log_file=ctx.tracer.log_file,
            execution_time_seconds=round(time.monotonic() - state.started, 2), error=error,
            sample_mode=self.settings.sample_mode,
            provider_state="sample_mode" if self.settings.sample_mode else ("online" if live else None),
            patient_id=state.anchor.source_patient_id, coverage=coverage or {}, bpmh_confirmable=confirmable,
            banner=banner, grid=analysis.fused if analysis else [], findings=findings,
            notices=analysis.notices if analysis else [], tasks=analysis.tasks if analysis else [],
            evidence_index=evidence_index,
            trust=[TrustEntry(source=s, attribute=a, value=v, hmem_record_id=None)
                   for (s, a), v in sorted(self.trust.items())],
            trace=list(ctx.tracer.events), query_count=ctx.zetaris.used, zetaris_ms=ctx.zetaris.zetaris_ms,
            model_calls=list(calls),
        )
