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
import { Brand, SideStatus } from "./components/Header";
import { PatientHead, PatientList, fullName, type PatientsState } from "./components/Picker";
import { Stepper } from "./components/Stepper";
import { Timeline } from "./components/Timeline";
import { IdentityReview } from "./components/IdentityReview";
import { BpmhBanner, Notices } from "./components/Coverage";
import { Supply } from "./components/Supply";
import { Grid, gridFeedbackKey } from "./components/Grid";
import { Flags, type FeedbackChoice, type FeedbackState } from "./components/Flags";
import { Tasks } from "./components/Tasks";
import { TrustPanel, type AppliedTrustUpdate } from "./components/TrustPanel";
import { DISCLAIMER, Footer } from "./components/Footer";
import { Silos } from "./components/Silos";
import { Pipeline } from "./components/Pipeline";
import { LearningHero } from "./components/LearningHero";
import { SectionNav, type NavItem } from "./components/SectionNav";
import { Welcome } from "./components/Welcome";
import type { LogFilter } from "./trace";
import { sameFilter } from "./trace";
import { cleanText, medName, targetLabel, typeLabel } from "./format";

type Section = "identity" | "findings" | "meds" | "actions" | "notices" | "supply" | "trust" | "log";
const PANEL = "section-panel";

/** The API's caveats about this result, minus the fixed disclaimer shown in the header and footer. */
function Caveats({ caveats }: { caveats: string[] }) {
  const shown = caveats.filter((c) => c !== DISCLAIMER);
  if (!shown.length) return null;
  return (
    <div className="alert alert-note caveats" role="note">
      {shown.map((c) => (
        <div key={c} title={c}>
          {cleanText(c)}
        </div>
      ))}
    </div>
  );
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

// The run's status (from the API) in words, for the patient header and the sidebar list.
const STATUS_TAG: Record<string, { label: string; tone: string }> = {
  running: { label: "Reconciling…", tone: "t-low" },
  needs_review: { label: "Review needed", tone: "t-medium" },
  success: { label: "Reconciliation complete", tone: "t-done" },
  partial: { label: "Partial result", tone: "t-medium" },
  error: { label: "Stopped with an error", tone: "t-high" },
};

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
  const [section, setSection] = useState<Section>("findings");
  // Item 9: the Welcome page is the default view until a patient is chosen, and always one click away.
  const [view, setView] = useState<"welcome" | "patient">("welcome");
  // Item 11: a click on a Powered-by node filters the processing log.
  const [logFilter, setLogFilter] = useState<LogFilter | null>(null);
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
    setSection("findings");
    setLogFilter(null);
  };

  // A result stays on screen only while its patient is selected, so one
  // patient's medicines can never sit under another patient's name.
  const selectPatient = (id: string) => {
    setView("patient");
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
        if (r.status === "needs_review") setSection("identity");
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
      if (r.status === "needs_review") setSection("identity");
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
      if (r.status !== "needs_review") setSection("findings");
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
      // Name the target in words now, while its finding is on screen (a finding id alone means nothing on the next patient).
      const f = run.findings.find((x) => x.id === targetId);
      const targetName = f ? `${medName(f.generic)} · ${typeLabel(f.type)}` : targetLabel(targetId);
      setTrustUpdates((u) => [...u, ...r.trust_updates.map((t) => ({ ...t, runId: r.run_id, targetId: r.target_id, targetName, reason: r.reason }))]);
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
  const review = run?.status === "needs_review";
  const doneCount = run ? run.tasks.filter((_, i) => actionsDone[i]).length : 0;
  const step: 1 | 2 | 3 = !selected ? 1 : run && (review || finished) ? 3 : 2;
  const panelRef = useRef<HTMLDivElement>(null);
  const patient = patients.find((x) => x.patient_id === selected);
  const ready = patientsState.kind === "ready" && patients.length > 0;

  // What this screen has seen for each patient in this session, for the sidebar list.
  const [seen, setSeen] = useState<Record<string, string>>({});
  useEffect(() => {
    const id = run?.patient_id ?? (run ? selected : null);
    if (id && run) setSeen((m) => ({ ...m, [id]: (STATUS_TAG[run.status] ?? STATUS_TAG.running).label.replace("Reconciliation complete", "Complete") }));
  }, [run, selected]);

  const choose = (id: Section) => {
    setSection(id);
    // Scroll the chosen section into view.
    requestAnimationFrame(() => panelRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };

  const shortages = run ? run.notices.filter((n) => n.type === "known_shortage") : [];
  const otherNotices = run ? run.notices.filter((n) => n.type !== "known_shortage") : [];

  const nav: NavItem<Section>[] = run
    ? [
        ...(review ? [{ id: "identity" as const, label: "Identity review", count: run.identity_review?.candidates.length ?? null, alert: true }] : []),
        {
          id: "findings",
          label: "Discrepancies",
          count: hasResult ? run.findings.length : null,
          alert: hasResult && run.findings.some((f) => f.high_risk_class),
          disabled: !hasResult,
        },
        { id: "meds", label: "Medication history", count: hasResult ? run.grid.length : null, disabled: !hasResult },
        { id: "actions", label: "Actions", count: hasResult ? run.tasks.length - doneCount : null, disabled: !hasResult },
        { id: "notices", label: "Notices", count: hasResult ? otherNotices.length : null, disabled: !hasResult },
        // S42: shortages get their own section, shown only when the API sent any.
        ...(shortages.length ? [{ id: "supply" as const, label: "Supply", count: shortages.length }] : []),
        { id: "trust", label: "Source confidence", count: trustUpdates.length || null, disabled: !hasResult },
        { id: "log", label: "Processing log", count: run.trace.length },
      ]
    : [];
  // Never show a section the rail has disabled (e.g. right after a new run starts).
  const shownSection: Section = nav.find((i) => i.id === section && !i.disabled) ? section : review ? "identity" : hasResult ? "findings" : "log";

  return (
    <div className="app">
      <a className="skip" href={`#${PANEL}`}>
        Skip to results
      </a>
      <aside className="side" aria-label="Workspace">
        <Brand />
        <button type="button" className={`snav-item side-welcome ${view === "welcome" ? "on" : ""}`} aria-current={view === "welcome" ? "page" : undefined} onClick={() => setView("welcome")}>
          <span>Welcome</span>
        </button>
        <PatientList
          patients={patients}
          patientsState={patientsState}
          onRetry={loadPatients}
          selected={selected}
          onSelect={selectPatient}
          disabled={polling}
          states={seen}
        />
        {run && view === "patient" && (
          <div className="side-group">
            <h2 className="side-label">This reconciliation</h2>
            <SectionNav items={nav} current={shownSection} onSelect={choose} panelId={PANEL} />
          </div>
        )}
        <SideStatus health={health} error={healthError} />
      </aside>

      <div className="main-col">
        {API_MODE === "mock" && (
          <div className="mock-note" title="VITE_API_MODE=mock: replaying tests/fixtures/api/*.json">
            Example data: hand-written, not a real run
          </div>
        )}
        <main className="wrap">
          {view === "welcome" ? (
            <Welcome
              patients={patients}
              onPick={selectPatient}
              onStart={() => {
                const q = document.getElementById("pt-q");
                q?.scrollIntoView({ block: "nearest" });
                q?.focus();
              }}
            />
          ) : (
            <>
          <Stepper current={step} busy={polling} />
          <PatientHead
            patient={patient}
            loading={patientsState.kind === "loading"}
            status={run ? STATUS_TAG[run.status] ?? null : null}
            onRun={startRun}
            running={polling}
            canRun={ready && !!selected}
            error={runError}
            mock={API_MODE === "mock"}
          />
          {run && (finished || review) && <Caveats caveats={run.output.caveats} />}
          {hasResult && <BpmhBanner banner={run!.banner} bpmhConfirmable={run!.bpmh_confirmable} />}
          {run?.status === "partial" && <div className="alert alert-medium">Partial result: read the caveats</div>}

          <Pipeline
            run={run}
            health={health}
            live={polling || review}
            filter={logFilter}
            onFilter={(f) => {
              const off = sameFilter(logFilter, f);
              setLogFilter(off ? null : f);
              if (!off && run) choose("log");
            }}
          />

          <section className="panel overview" aria-labelledby="overview-title">
            <h2 className="h2" id="overview-title">
              Overview
            </h2>
            {hasResult && run!.output.summary && (
              <p className="overview-summary" title={run!.output.summary}>
                {cleanText(run!.output.summary)}
              </p>
            )}
            <Silos run={run} searching={polling} />
          </section>
          {hasResult && <LearningHero run={run!} updates={trustUpdates} />}

          {!run && polling && (
            <section className="panel panel-pad" aria-live="polite">
              <h2 className="h2">
                Starting the reconciliation <span className="spinner spinner-sm" aria-hidden />
              </h2>
            </section>
          )}

          {run && (
            <div className="panel section" id={PANEL} ref={panelRef} role="tabpanel" aria-labelledby={`nav-${shownSection}`} tabIndex={-1}>
              {shownSection === "identity" &&
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
                  <div className="panel-pad">
                    <h2 className="h2">Identity review required</h2>
                    <p className="error">
                      The reconciliation paused for an identity review, but no review details were provided, so no decision can be
                      made from this screen.
                    </p>
                  </div>
                ))}

              {shownSection === "log" && polling && (
                <div className="panel-pad running" aria-live="polite">
                  <h2 className="h2">
                    Reconciling… <span className="spinner spinner-sm" aria-hidden />
                  </h2>
                  <Timeline run={run} polling={polling} warning={pollWarning} compact patientName={patient ? fullName(patient) : null} />
                </div>
              )}
              {shownSection === "log" && !polling && (
                <Timeline
                  run={run}
                  polling={polling}
                  warning={pollWarning}
                  patientName={patient ? fullName(patient) : null}
                  filter={logFilter}
                  onClearFilter={() => setLogFilter(null)}
                />
              )}

              {shownSection === "log" && !polling && run.status === "error" && (
                <div className="panel-pad">
                  <div className="friendly-err" role="alert">
                    <span>Stopped with an error. No result.</span>
                    <button type="button" className="btn btn-line btn-sm" onClick={startRun}>
                      Run again
                    </button>
                  </div>
                  <p className="error">{run.error?.message ?? "The reconciliation ended with an error."}</p>
                </div>
              )}
              {shownSection === "log" && finished && run.status !== "error" && !hasResult && (
                <div className="panel-pad">
                  <h2 className="h2">Summary</h2>
                  <p className="overview-summary" title={run.output.summary}>
                    {cleanText(run.output.summary)}
                  </p>
                </div>
              )}

              {hasResult && shownSection === "findings" && <Flags findings={run.findings} grid={run.grid} coverage={run.coverage} doseUnits={run.dose_units ?? {}} feedback={feedback} onFeedback={sendFeedback} />}
              {hasResult && shownSection === "meds" && (
                <Grid
                  grid={run.grid}
                  evidenceIndex={run.evidence_index}
                  coverage={run.coverage}
                  doseUnits={run.dose_units ?? {}}
                  findings={run.findings}
                  admissionDate={patient?.admission_date}
                  feedback={feedback}
                  onRejectCell={rejectCell}
                />
              )}
              {hasResult && shownSection === "actions" && (
                <Tasks
                  tasks={run.tasks}
                  findings={run.findings}
                  notices={run.notices}
                  done={actionsDone}
                  onToggle={(i, d) => setActionsDone((s) => ({ ...s, [i]: d }))}
                />
              )}
              {hasResult && shownSection === "notices" && <Notices notices={otherNotices} />}
              {hasResult && shownSection === "supply" && <Supply notices={shortages} />}
              {hasResult && shownSection === "trust" && <TrustPanel trust={run.trust} runId={run.run_id} updates={trustUpdates} acceptance={acceptance} />}
            </div>
          )}
            </>
          )}
          <Footer />
        </main>
      </div>
    </div>
  );
}
