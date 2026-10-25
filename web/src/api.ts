// The one place the UI talks to the backend. `VITE_API_MODE=live` calls the
// FastAPI server at VITE_API_URL; `mock` (the default) replays the example
// responses in tests/fixtures/api/ with fake delays so the timeline animates.
//
// Mock mode never invents data: every value shown comes from a fixture file.
// Where no fixture exists (a resumed identity review, other patients), it says
// so instead of making something up.

import type {
  FeedbackRequest,
  FeedbackResponse,
  HealthResponse,
  IdentityDecisionRequest,
  PatientsResponse,
  RunRequest,
  RunResponse,
} from "./types";

import statusFx from "@fixtures/status.json";
import patientsFx from "@fixtures/patients.json";
import partialFx from "@fixtures/run_P0001_trace_partial.json";
import doneFx from "@fixtures/run_P0001_done.json";
import gpNotFoundFx from "@fixtures/run_P0001_gp_not_found.json";
import needsReviewFx from "@fixtures/run_P0002_needs_review.json";
import feedbackFx from "@fixtures/feedback_response.json";

export const API_MODE: "mock" | "live" =
  import.meta.env.VITE_API_MODE === "live" ? "live" : "mock";
const API_URL = String(import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// Nightshift can take minutes on a cold model load, so a run is polled rather
// than awaited; a single request still gets a bounded timeout.
const REQUEST_TIMEOUT_MS = 30_000;
export const POLL_INTERVAL_MS = API_MODE === "mock" ? 600 : 1500;
// 15 minutes of polling at most; a judge's run should finish in 5-10.
export const STATUS_REFRESH_MS = 30_000;
export const MAX_POLLS = Math.ceil((15 * 60 * 1000) / POLL_INTERVAL_MS);

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
      } catch {
        /* body was not JSON; keep statusText */
      }
      throw new ApiError(`${init?.method ?? "GET"} ${path} failed (${res.status}): ${detail}`, res.status);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(`${init?.method ?? "GET"} ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s`);
    }
    throw new ApiError(`Cannot reach the API at ${API_URL} (${(e as Error).message})`);
  } finally {
    clearTimeout(timer);
  }
}

// --------------------------------------------------------------------------- //
// Mock
// --------------------------------------------------------------------------- //

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

const fx = {
  status: statusFx as unknown as HealthResponse,
  patients: patientsFx as unknown as PatientsResponse,
  partial: partialFx as unknown as RunResponse,
  done: doneFx as unknown as RunResponse,
  gpNotFound: gpNotFoundFx as unknown as RunResponse,
  needsReview: needsReviewFx as unknown as RunResponse,
  feedback: feedbackFx as unknown as FeedbackResponse,
};

/** Patients mock mode has an example run for; the picker labels them. */
export const MOCK_RUN_PATIENTS = [fx.done.patient_id, fx.needsReview.patient_id].filter((x): x is string => !!x);

/** `?mock=gp_not_found` replays the GP-not-found example for MRN0000001. */
function mockScenario(): string | null {
  return new URLSearchParams(window.location.search).get("mock");
}

interface MockRun {
  final: RunResponse;
  startedAt: number;
}
const mockRuns = new Map<string, MockRun>();
const MOCK_STEP_MS = 700;

function mockFinalFor(patientId: string): RunResponse {
  if (patientId === fx.done.patient_id) {
    return clone(mockScenario() === "gp_not_found" ? fx.gpNotFound : fx.done);
  }
  if (patientId === fx.needsReview.patient_id) return clone(fx.needsReview);
  throw new ApiError(
    `Mock mode has example runs for ${fx.done.patient_id} and ${fx.needsReview.patient_id} only. ` +
      `Set VITE_API_MODE=live to run ${patientId} against the API.`,
  );
}

/** The run as it would look `elapsed` ms in: trace events revealed one at a time. */
function mockSnapshot(run: MockRun): RunResponse {
  const shown = Math.floor((Date.now() - run.startedAt) / MOCK_STEP_MS);
  const trace = run.final.trace;
  if (shown >= trace.length) return clone(run.final);
  // Mid-run polls use the recorded mid-run example (status running, no grid
  // yet) with the final run's trace revealed up to this point.
  return { ...clone(fx.partial), run_id: run.final.run_id, patient_id: run.final.patient_id, trace: trace.slice(0, shown) };
}

const mock = {
  async status(): Promise<HealthResponse> {
    await sleep(250);
    return clone(fx.status);
  },
  async patients(): Promise<PatientsResponse> {
    await sleep(300);
    return clone(fx.patients);
  },
  async startRun(req: RunRequest): Promise<RunResponse> {
    await sleep(300);
    const final = mockFinalFor(req.patient_id ?? "");
    const run = { final, startedAt: Date.now() };
    mockRuns.set(final.run_id, run);
    return mockSnapshot(run);
  },
  async getRun(runId: string): Promise<RunResponse> {
    await sleep(150);
    const run = mockRuns.get(runId);
    if (!run) throw new ApiError(`Unknown run ${runId}`, 404);
    return mockSnapshot(run);
  },
  async decideIdentity(_runId: string, _req: IdentityDecisionRequest): Promise<RunResponse> {
    await sleep(300);
    throw new ApiError(
      "Mock mode has no example of a resumed run, so the decision was not applied. " +
        "In live mode it is sent to POST /run/{id}/identity and the run continues.",
    );
  },
  async feedback(req: FeedbackRequest): Promise<FeedbackResponse> {
    await sleep(400);
    const f = fx.feedback;
    // Only the recorded verdict has recorded trust updates; anything else is
    // acknowledged with none rather than with invented numbers.
    if (req.target_id === f.target_id && req.verdict === f.verdict && (req.reason ?? null) === (f.reason ?? null)) {
      return { ...clone(f), run_id: req.run_id };
    }
    return { ...req, reason: req.reason ?? null, trust_updates: [], acceptance_updates: [] };
  },
};

// --------------------------------------------------------------------------- //
// Live
// --------------------------------------------------------------------------- //

const live = {
  status: () => http<HealthResponse>("/status"),
  patients: () => http<PatientsResponse>("/patients"),
  startRun: (req: RunRequest) => http<RunResponse>("/run", { method: "POST", body: JSON.stringify(req) }),
  getRun: (runId: string) => http<RunResponse>(`/run/${encodeURIComponent(runId)}`),
  decideIdentity: (runId: string, req: IdentityDecisionRequest) =>
    http<RunResponse>(`/run/${encodeURIComponent(runId)}/identity`, { method: "POST", body: JSON.stringify(req) }),
  feedback: (req: FeedbackRequest) =>
    http<FeedbackResponse>("/feedback", { method: "POST", body: JSON.stringify(req) }),
};

export const api = API_MODE === "live" ? live : mock;

export const isTerminal = (s: RunResponse["status"]) => s === "success" || s === "partial" || s === "error";
