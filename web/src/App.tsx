import { useCallback, useEffect, useRef, useState } from "react";
import { API_MODE, MAX_POLLS, POLL_INTERVAL_MS, STATUS_REFRESH_MS, api, isTerminal } from "./api";
import type {
  AcceptanceUpdate,
  FeedbackReason,
  Finding,
  HealthResponse,
  PatientSummary,
  RunResponse,
  TrustUpdate,
} from "./types";
import { Header } from "./components/Header";
import { Picker, type PatientsState } from "./components/Picker";
import { Timeline } from "./components/Timeline";
import { IdentityReview } from "./components/IdentityReview";
import { CoverageStrip, Notices } from "./components/Coverage";
import { Grid } from "./components/Grid";
import { Flags, type FeedbackState } from "./components/Flags";
import { Tasks } from "./components/Tasks";
import { TrustPanel } from "./components/TrustPanel";
import { Footer } from "./components/Footer";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [patientsState, setPatientsState] = useState<PatientsState>({ kind: "loading" });
  const [selected, setSelected] = useState("");
  const [run, setRun] = useState<RunResponse | null>(null);
  const [polling, setPolling] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [decided, setDecided] = useState<Record<string, "same" | "different">>({});
  const [identityBusy, setIdentityBusy] = useState<string | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});
  // Trust moves accumulate across runs in this session, so patient B shows what patient A taught.
  const [trustUpdates, setTrustUpdates] = useState<TrustUpdate[]>([]);
  const [acceptance, setAcceptance] = useState<AcceptanceUpdate[]>([]);
  const pollToken = useRef(0);

  // The header pill shows GET /status as returned, refreshed every 30 s and
  // whenever a run settles, so "last model" is the server's answer, not ours.
  const refreshStatus = useCallback(() => {
    api.status().then(
      (h) => {
        setHealth(h);
        setHealthError(null);
      },
      (e) => setHealthError(msg(e)),
    );
  }, []);

  useEffect(() => {
    refreshStatus();
    const t = setInterval(refreshStatus, STATUS_REFRESH_MS);
    return () => clearInterval(t);
  }, [refreshStatus]);

  useEffect(() => {
    if (!polling) refreshStatus();
  }, [polling, refreshStatus]);

  const loadPatients = useCallback(() => {
    setPatientsState({ kind: "loading" });
    api.patients().then(
      (r) => {
        setPatients(r.patients);
        setPatientsState({ kind: "ready" });
        setSelected((s) => s || r.patients[0]?.patient_id || "");
      },
      (e) => setPatientsState({ kind: "error", message: msg(e) }),
    );
  }, []);

  useEffect(loadPatients, [loadPatients]);

  // A result stays on screen only while its patient is selected, so one
  // patient's medicines can never sit under another patient's name.
  const selectPatient = (id: string) => {
    if (id === selected) return;
    pollToken.current++;
    setSelected(id);
    setRun(null);
    setRunError(null);
    setDecided({});
    setIdentityError(null);
    setFeedback({});
  };

  const poll = useCallback(async (runId: string) => {
    const token = ++pollToken.current;
    setPolling(true);
    try {
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (token !== pollToken.current) return;
        const r = await api.getRun(runId);
        if (token !== pollToken.current) return;
        setRun(r);
        if (isTerminal(r.status) || r.status === "needs_review") return;
      }
      setRunError(`Stopped polling after ${Math.round((MAX_POLLS * POLL_INTERVAL_MS) / 60000)} minutes; the run may still finish.`);
    } catch (e) {
      if (token === pollToken.current) setRunError(msg(e));
    } finally {
      if (token === pollToken.current) setPolling(false);
    }
  }, []);

  const startRun = async () => {
    pollToken.current++;
    setRun(null);
    setRunError(null);
    setDecided({});
    setIdentityError(null);
    setFeedback({});
    setPolling(true);
    try {
      const r = await api.startRun({ patient_id: selected });
      setRun(r);
      if (isTerminal(r.status) || r.status === "needs_review") setPolling(false);
      else void poll(r.run_id);
    } catch (e) {
      setRunError(msg(e));
      setPolling(false);
    }
  };

  const decideIdentity = async (candidateId: string, samePerson: boolean) => {
    if (!run) return;
    setIdentityBusy(candidateId);
    setIdentityError(null);
    try {
      const r = await api.decideIdentity(run.run_id, { candidate_id: candidateId, same_person: samePerson });
      setDecided((d) => ({ ...d, [candidateId]: samePerson ? "same" : "different" }));
      setRun(r);
      if (!isTerminal(r.status) && r.status !== "needs_review") void poll(r.run_id);
    } catch (e) {
      setIdentityError(msg(e));
    } finally {
      setIdentityBusy(null);
    }
  };

  const sendFeedback = async (f: Finding, verdict: "confirm" | "reject", reason?: FeedbackReason) => {
    if (!run) return;
    setFeedback((s) => ({ ...s, [f.id]: { busy: true } }));
    try {
      const r = await api.feedback({ run_id: run.run_id, target_id: f.id, verdict, reason: reason ?? null });
      setFeedback((s) => ({ ...s, [f.id]: { result: r } }));
      setTrustUpdates((u) => [...u, ...r.trust_updates]);
      setAcceptance((a) => [...a, ...r.acceptance_updates]);
    } catch (e) {
      setFeedback((s) => ({ ...s, [f.id]: { error: msg(e) } }));
    }
  };

  const finished = run && (isTerminal(run.status) || run.status === "needs_review");

  return (
    <div className="app">
      <Header health={health} error={healthError} />
      {API_MODE === "mock" && (
        <div className="mock-note">
          Mock mode: replaying hand-written example responses from <code>tests/fixtures/api/</code>. These are not results
          of a real run.
        </div>
      )}
      <main className="layout">
        <div className="side">
          <Picker
            patients={patients}
            patientsState={patientsState}
            onRetryPatients={loadPatients}
            selected={selected}
            onSelect={selectPatient}
            onRun={startRun}
            running={polling}
            error={runError}
          />
          <Timeline run={run} polling={polling} />
        </div>
        <div className="main">
          {run?.status === "needs_review" && run.identity_review && (
            <IdentityReview
              review={run.identity_review}
              banner={run.banner}
              decided={decided}
              busy={identityBusy}
              error={identityError}
              onDecide={decideIdentity}
            />
          )}
          {run?.status === "error" && (
            <section className="card">
              <h2>Run failed</h2>
              <p className="error">{run.error?.message ?? "The run ended with an error."}</p>
            </section>
          )}
          {finished && run.status !== "needs_review" && (
            <>
              <section className="card summary">
                <h2>Summary</h2>
                <p>{run.output.summary}</p>
                {run.status === "partial" && <p className="banner small">Partial result: read the banner and notices below before relying on it.</p>}
              </section>
              <CoverageStrip coverage={run.coverage} banner={run.banner} bpmhConfirmable={run.bpmh_confirmable} />
              <Grid grid={run.grid} evidenceIndex={run.evidence_index} coverage={run.coverage} />
              <Flags findings={run.findings} feedback={feedback} onFeedback={sendFeedback} />
              <div className="two-col">
                <Tasks tasks={run.tasks} />
                <Notices notices={run.notices} />
              </div>
              <TrustPanel trust={run.trust} updates={trustUpdates} acceptance={acceptance} />
            </>
          )}
          {!run && !polling && (
            <section className="card empty-state">
              <h2>Reconcile a patient's medicines</h2>
              <p>
                MedTrace finds the patient in the admission chart, GP list, pharmacy dispensing history and patient
                interview, lines up every medicine side by side, and flags what a pharmacist must check.
              </p>
            </section>
          )}
        </div>
      </main>
      <Footer caveats={run?.output.caveats ?? []} />
    </div>
  );
}
