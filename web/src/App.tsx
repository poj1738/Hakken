import { useCallback, useEffect, useRef, useState } from "react";
import { API_MODE, MAX_POLL_FAILURES, MAX_POLLS, POLL_INTERVAL_MS, STATUS_REFRESH_MS, api, isTerminal } from "./api";
import type {
  AcceptanceUpdate,
  Finding,
  HealthResponse,
  PatientSummary,
  RunResponse,
  Source,
  TrustAttribute,
} from "./types";
import { Header } from "./components/Header";
import { Picker, type PatientsState } from "./components/Picker";
import { Timeline } from "./components/Timeline";
import { IdentityReview } from "./components/IdentityReview";
import { BpmhBanner, RecordSources } from "./components/Coverage";
import { Grid, gridFeedbackKey } from "./components/Grid";
import { Flags, type FeedbackChoice, type FeedbackState } from "./components/Flags";
import { Tasks } from "./components/Tasks";
import { TrustPanel, type AppliedTrustUpdate } from "./components/TrustPanel";
import { SummaryCards } from "./components/SummaryCards";
import { DISCLAIMER, Footer } from "./components/Footer";
import { cleanText } from "./format";

type Tab = "findings" | "meds" | "actions" | "trust";
const TABS: [Tab, string][] = [
  ["findings", "Discrepancies"],
  ["meds", "Medication History"],
  ["actions", "Actions Required"],
  ["trust", "Source Confidence"],
];

/** The API's caveats about this result, minus the fixed disclaimer shown in the header and footer. */
function Caveats({ caveats }: { caveats: string[] }) {
  const shown = caveats.filter((c) => c !== DISCLAIMER);
  if (!shown.length) return null;
  return (
    <div className="alert alert-note" role="note">
      {shown.map((c) => (
        <div key={c} title={c}>
          {cleanText(c)}
        </div>
      ))}
    </div>
  );
}

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
  const [pollWarning, setPollWarning] = useState<string | null>(null);
  const [decided, setDecided] = useState<Record<string, "same" | "different">>({});
  const [identityBusy, setIdentityBusy] = useState<string | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});
  const [tab, setTab] = useState<Tab>("findings");
  // Checklist ticks for this screen only; the summary card counts them live.
  const [actionsDone, setActionsDone] = useState<Record<number, boolean>>({});
  // Trust moves accumulate across runs in this session, so patient B shows what patient A taught.
  const [trustUpdates, setTrustUpdates] = useState<AppliedTrustUpdate[]>([]);
  const [acceptance, setAcceptance] = useState<AcceptanceUpdate[]>([]);
  const pollToken = useRef(0);

  // The header shows GET /status as returned, refreshed every 30 s and whenever
  // a run settles, so "Model" is the server's answer, not ours.
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

  const resetResult = () => {
    setRun(null);
    setRunError(null);
    setDecided({});
    setIdentityError(null);
    setFeedback({});
    setActionsDone({});
    setTab("findings");
  };

  // A result stays on screen only while its patient is selected, so one
  // patient's medicines can never sit under another patient's name.
  const selectPatient = (id: string) => {
    if (id === selected) return;
    pollToken.current++;
    setSelected(id);
    resetResult();
  };

  const poll = useCallback(async (runId: string) => {
    const token = ++pollToken.current;
    setPolling(true);
    setPollWarning(null);
    let failures = 0;
    try {
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (token !== pollToken.current) return;
        let r: RunResponse;
        try {
          r = await api.getRun(runId);
        } catch (e) {
          // One dropped poll must not abandon a run that is still going; give up
          // only after MAX_POLL_FAILURES in a row.
          if (++failures >= MAX_POLL_FAILURES) throw e;
          if (token === pollToken.current) setPollWarning(`Connection to the reconciliation lost (${failures}/${MAX_POLL_FAILURES}); retrying. ${msg(e)}`);
          continue;
        }
        failures = 0;
        if (token !== pollToken.current) return;
        setPollWarning(null);
        setRun(r);
        if (isTerminal(r.status) || r.status === "needs_review") return;
      }
      setRunError(`Stopped checking after ${Math.round((MAX_POLLS * POLL_INTERVAL_MS) / 60000)} minutes; the reconciliation may still finish.`);
    } catch (e) {
      if (token === pollToken.current) setRunError(msg(e));
    } finally {
      if (token === pollToken.current) {
        setPolling(false);
        setPollWarning(null);
      }
    }
  }, []);

  const startRun = async () => {
    pollToken.current++;
    resetResult();
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

  // `key` is where the UI shows the result (a finding id, or one grid cell);
  // `targetId` is what the API is told: a finding id, or grid:<generic>:<attribute>.
  const sendFeedbackFor = async (key: string, targetId: string, c: FeedbackChoice) => {
    if (!run) return;
    setFeedback((s) => ({ ...s, [key]: { busy: true } }));
    try {
      const r = await api.feedback({
        run_id: run.run_id,
        target_id: targetId,
        verdict: c.verdict,
        reason: c.reason ?? null,
        // Only a source_outdated reject names a record; the API rejects them elsewhere.
        ...(c.reason === "source_outdated" ? { source: c.source, attribute: c.attribute } : {}),
      });
      setFeedback((s) => ({ ...s, [key]: { result: r } }));
      setTrustUpdates((u) => [...u, ...r.trust_updates.map((t) => ({ ...t, runId: r.run_id, targetId: r.target_id, reason: r.reason }))]);
      setAcceptance((a) => [...a, ...r.acceptance_updates]);
    } catch (e) {
      setFeedback((s) => ({ ...s, [key]: { error: msg(e) } }));
    }
  };
  const sendFeedback = (f: Finding, c: FeedbackChoice) => sendFeedbackFor(f.id, f.id, c);
  // The learning demo's step 1: a source's value for one grid attribute is outdated.
  const rejectCell = (generic: string, attribute: TrustAttribute, source: Source) =>
    sendFeedbackFor(gridFeedbackKey(generic, attribute, source), `grid:${generic}:${attribute}`, {
      verdict: "reject",
      reason: "source_outdated",
      source,
      attribute,
    });

  const finished = !!run && isTerminal(run.status);
  // A result with no coverage and no grid (an early stop, or the mock placeholder)
  // shows only its summary: an empty grid and "No discrepancies" would read as a
  // clean bill of health.
  const hasResult = finished && (Object.keys(run!.coverage).length > 0 || run!.grid.length > 0);
  const doneCount = run ? run.tasks.filter((_, i) => actionsDone[i]).length : 0;

  return (
    <div className="app">
      <Header health={health} error={healthError} />
      {API_MODE === "mock" && (
        <div className="mock-note" title="VITE_API_MODE=mock: replaying tests/fixtures/api/*.json">
          Example data: these screens replay hand-written examples, not the results of a real reconciliation.
        </div>
      )}
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
      <main className="wrap">
        {run && (finished || run.status === "needs_review") && <Caveats caveats={run.output.caveats} />}
        {hasResult && <BpmhBanner banner={run!.banner} bpmhConfirmable={run!.bpmh_confirmable} />}
        {run?.status === "partial" && <div className="alert alert-medium">Partial result. Read every caveat before relying on it.</div>}
        {hasResult && <SummaryCards run={run!} actionsDone={doneCount} />}

        <div className="cols">
          <div className="col-main">
            {run?.status === "needs_review" &&
              (run.identity_review ? (
                <IdentityReview
                  review={run.identity_review}
                  banner={run.banner}
                  decided={decided}
                  busy={identityBusy}
                  error={identityError}
                  onDecide={decideIdentity}
                />
              ) : (
                <section className="card card-pad">
                  <h2 className="card-title">Identity Review Required</h2>
                  <p className="error">
                    The reconciliation paused for an identity review, but no review details were provided, so no decision can be
                    made from this screen.
                  </p>
                </section>
              ))}

            {run?.status === "error" && (
              <section className="card card-pad">
                <h2 className="card-title">Reconciliation Failed</h2>
                <p className="error">{run.error?.message ?? "The reconciliation ended with an error."}</p>
              </section>
            )}

            {finished && run.status !== "error" && !hasResult && (
              <section className="card card-pad">
                <h2 className="card-title">Summary</h2>
                <p className="tab-summary" title={run.output.summary}>
                  {cleanText(run.output.summary)}
                </p>
              </section>
            )}

            {hasResult && (
              <div className="card tabs-card">
                <nav className="tabs" aria-label="Reconciliation sections" role="tablist">
                  {TABS.map(([id, label]) => (
                    <button key={id} type="button" role="tab" aria-selected={tab === id} className={`tab ${tab === id ? "on" : ""}`} onClick={() => setTab(id)}>
                      {label}
                    </button>
                  ))}
                </nav>
                {tab === "findings" && <Flags findings={run!.findings} summary={run!.output.summary} feedback={feedback} onFeedback={sendFeedback} />}
                {tab === "meds" && (
                  <Grid grid={run!.grid} evidenceIndex={run!.evidence_index} coverage={run!.coverage} feedback={feedback} onRejectCell={rejectCell} />
                )}
                {tab === "actions" && (
                  <Tasks
                    tasks={run!.tasks}
                    findings={run!.findings}
                    notices={run!.notices}
                    done={actionsDone}
                    onToggle={(i, d) => setActionsDone((s) => ({ ...s, [i]: d }))}
                  />
                )}
                {tab === "trust" && <TrustPanel trust={run!.trust} runId={run!.run_id} updates={trustUpdates} acceptance={acceptance} />}
              </div>
            )}

            {!run && (
              <section className="card card-pad empty-state">
                <h2 className="card-title">{polling ? "Reconciliation in Progress" : "Reconcile a Patient's Medicines"}</h2>
                <p>
                  {polling
                    ? "Locating the patient across the four record sources. Progress is shown in the processing log."
                    : "MedTrace locates the patient in the admission chart, GP record, pharmacy dispensing history and patient interview, compares every medicine across them, and lists what a pharmacist must review."}
                </p>
              </section>
            )}
            {run && polling && !finished && run.status !== "needs_review" && (
              <section className="card card-pad empty-state">
                <h2 className="card-title">Reconciliation in Progress</h2>
                <p>Progress is shown in the processing log.</p>
              </section>
            )}
          </div>

          <aside className="col-side">
            {run && Object.keys(run.coverage).length > 0 && run.status !== "running" && (
              <RecordSources coverage={run.coverage} notices={run.notices} />
            )}
            <Timeline run={run} polling={polling} warning={pollWarning} />
          </aside>
        </div>
      </main>
      <Footer />
    </div>
  );
}
