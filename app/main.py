"""FastAPI surface (PLAN 5.6): the endpoints the UI calls.

    GET  /status                 status pill: Zetaris, Nightshift, last Nemotron that answered
    GET  /patients               the admitted-patient picker (Q0, read once)
    POST /run                    start a run; returns `running` at once, poll GET /run/{id}
                                 (?wait=true runs to the end first -- handy for curl)
    GET  /run/{id}               the run so far, or its final RunResponse
    GET  /run/{id}/trace         the trace events alone
    POST /run/{id}/identity      the pharmacist's decision on a near-miss; resumes the run
    POST /feedback               a verdict -> trust / acceptance deltas (PLAN 5.7)

Runs execute on a background thread so a 5-8 minute live run never holds a request
open. Health checks are cached so the status pill cannot hang on a slow service.
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.feedback import FeedbackError, apply_feedback
from app.orchestrator import Orchestrator, UnknownPatient
from app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    IdentityDecisionRequest,
    PatientsResponse,
    RunRequest,
    RunResponse,
)

STATUS_TTL_S = 20.0


class _Health:
    """Cached provider checks: GET /v1/models at most every STATUS_TTL_S."""

    def __init__(self) -> None:
        self.zetaris = "starting"
        self._meterless: tuple[float, str, list[str]] = (0.0, "unknown", [])

    def meterless(self, orch: Orchestrator) -> tuple[str, list[str]]:
        stamp, state, routes = self._meterless
        if time.monotonic() - stamp > STATUS_TTL_S:
            st = orch.llm.status(timeout=5.0)
            state, routes = (st.state if not orch.settings.sample_mode else "sample_mode"), st.routes
            self._meterless = (time.monotonic(), state, routes)
        return state, routes


def create_app(orchestrator: Orchestrator | None = None, *, background: bool = True) -> FastAPI:
    orch = orchestrator or Orchestrator()
    health = _Health()

    def warm() -> None:
        """Q_REF and Q0 once per process, so runs start fast and /patients is instant."""
        try:
            _ = orch.lex
            orch.patients()
            health.zetaris = "sample_mode" if orch.settings.sample_mode else "connected"
        except Exception as exc:  # reported on /status, never crashes the server
            health.zetaris = f"unreachable: {type(exc).__name__}: {str(exc)[:160]}"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        warm()
        yield

    app = FastAPI(title="MedTrace (Team Hakken)", version="0.1.0", lifespan=lifespan)
    app.state.orchestrator = orch
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def _run_async(target, *args: Any) -> None:
        if background:
            threading.Thread(target=target, args=args, daemon=True).start()
        else:
            target(*args)

    @app.get("/status", response_model=HealthResponse)
    @app.get("/health", response_model=HealthResponse, include_in_schema=False)
    def status() -> HealthResponse:
        state, routes = health.meterless(orch)
        return HealthResponse(status="ok", sample_mode=orch.settings.sample_mode, domain_pack="medtrace",
                              zetaris=health.zetaris, meterless=state, meterless_routes=routes,
                              last_routed_model=orch.last_routed_model)

    @app.get("/patients", response_model=PatientsResponse)
    def patients() -> PatientsResponse:
        try:
            return PatientsResponse(patients=orch.patients())
        except Exception as exc:
            raise HTTPException(503, f"patient list unavailable: {exc}") from exc

    @app.post("/run", response_model=RunResponse)
    def start_run(req: RunRequest, wait: bool = Query(False)) -> RunResponse:
        try:
            run_id = orch.create(req)
        except UnknownPatient as exc:
            raise HTTPException(404, str(exc)) from exc
        if wait:
            return orch.execute(run_id)
        _run_async(orch.execute, run_id)
        return orch.get(run_id)  # type: ignore[return-value]

    @app.get("/run/{run_id}", response_model=RunResponse)
    def get_run(run_id: str) -> RunResponse:
        resp = orch.get(run_id)
        if resp is None:
            raise HTTPException(404, f"unknown run {run_id}")
        return resp

    @app.get("/run/{run_id}/trace")
    def get_trace(run_id: str) -> list[dict[str, Any]]:
        resp = get_run(run_id)
        return [e.model_dump(mode="json") for e in resp.trace]

    @app.post("/run/{run_id}/identity", response_model=RunResponse)
    def identity(run_id: str, req: IdentityDecisionRequest, wait: bool = Query(False)) -> RunResponse:
        try:
            orch.decide(run_id, req)
        except KeyError as exc:
            raise HTTPException(404, f"unknown run {run_id}") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if wait:
            return orch.execute(run_id)
        _run_async(orch.execute, run_id)
        return orch.get(run_id)  # type: ignore[return-value]

    @app.post("/feedback", response_model=FeedbackResponse)
    def feedback(req: FeedbackRequest) -> FeedbackResponse:
        try:
            return apply_feedback(orch, req)
        except FeedbackError as exc:
            raise HTTPException(404, str(exc)) from exc

    return app


def __getattr__(name: str) -> Any:
    """`uvicorn app.main:app` builds the app on first access, not at import time --
    so importing this module in tests never reads `.env` or touches a service."""
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
