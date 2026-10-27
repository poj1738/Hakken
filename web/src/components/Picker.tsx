import { useEffect, useMemo, useRef, useState } from "react";
import type { PatientSummary } from "../types";
import { API_MODE, MOCK_RUN_PATIENTS } from "../api";
import { fmtDate } from "../format";
import { TechDetails } from "./TechDetails";

export type PatientsState = { kind: "loading" } | { kind: "ready" } | { kind: "error"; message: string };

const SEX: Record<string, string> = { F: "Female", M: "Male" };
export const fullName = (p: PatientSummary) => [p.name_given, p.name_family].filter(Boolean).join(" ") || "Unnamed patient";
/** "MRN0000001" reads as "MRN 0000001", as in the design; the full id is the tooltip. */
const mrn = (id: string) => id.replace(/^MRN/i, "");

/**
 * The sidebar's patient list. Each row's state is what this screen has seen for
 * that patient in this session (from the API's run status), or "Not yet run".
 */
export function PatientList({
  patients,
  patientsState,
  onRetry,
  selected,
  onSelect,
  disabled,
  states,
}: {
  patients: PatientSummary[];
  patientsState: PatientsState;
  onRetry: () => void;
  selected: string;
  onSelect: (id: string) => void;
  disabled: boolean;
  states: Record<string, string>;
}) {
  const [q, setQ] = useState("");
  const [atEnd, setAtEnd] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  // Filter by name or MRN as typed ("walker", "0000015", "MRN15" all work); case and spaces ignored.
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return patients;
    const digits = t.replace(/^mrn\s*/, "").replace(/\s+/g, "");
    return patients.filter((p) => fullName(p).toLowerCase().includes(t) || p.patient_id.toLowerCase().includes(t) || (/^\d+$/.test(digits) && p.patient_id.includes(digits)));
  }, [patients, q]);
  const list = useRef<HTMLUListElement>(null);
  // The bottom fade shows only while there is more list below; recheck when the filter changes.
  useEffect(() => {
    const el = list.current;
    if (el) setAtEnd(el.scrollTop + el.clientHeight >= el.scrollHeight - 4);
  }, [shown]);
  const clear = () => {
    setQ("");
    input.current?.focus();
  };
  return (
    <div className="side-group pt-group">
      <h2 className="side-label" id="patients-label">
        Admitted patients{patientsState.kind === "ready" && patients.length > 0 && <span className="side-label-n"> · {patients.length}</span>}
      </h2>
      {patientsState.kind === "loading" && (
        <p className="side-note">
          Loading patients… <span className="spinner spinner-sm" aria-hidden />
        </p>
      )}
      {patientsState.kind === "error" && (
        <div className="friendly-err" role="alert">
          <span>The patient list didn't load. Check that the MedTrace API is running.</span>
          <button type="button" className="btn btn-line btn-sm" onClick={onRetry}>
            Try again
          </button>
          <TechDetails items={[["Error", patientsState.message]]} />
        </div>
      )}
      {patientsState.kind === "ready" && !patients.length && <p className="side-note">No admitted patients.</p>}
      {patients.length > 0 && (
        <div className="pt-search">
          <label htmlFor="pt-q" className="sr-only">
            Search patients by name or MRN
          </label>
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden className="pt-search-ico">
            <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <input
            id="pt-q"
            ref={input}
            type="search"
            placeholder="Search name or MRN"
            autoComplete="off"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && q && (e.preventDefault(), clear())}
            aria-controls="pt-list"
          />
          {q && (
            <button type="button" className="pt-clear" onClick={clear} aria-label="Clear search">
              ×
            </button>
          )}
        </div>
      )}
      {q && (
        <p className="sr-only" role="status">
          {shown.length ? `${shown.length} ${shown.length === 1 ? "patient" : "patients"} match` : "No patients match"}
        </p>
      )}
      {/* Its own scroll area, so a long list (200 patients live) never runs into the sections below. */}
      <div className={`pt-scroll ${atEnd ? "at-end" : ""}`}>
        <ul
          id="pt-list"
          className="pt-list"
          aria-labelledby="patients-label"
          onScroll={(e) => {
            const el = e.currentTarget;
            setAtEnd(el.scrollTop + el.clientHeight >= el.scrollHeight - 4);
          }}
          ref={list}
        >
          {shown.map((p) => {
            // Mock mode only has example runs for two patients; say so before Run, not after.
            const state = states[p.patient_id] ?? (API_MODE === "mock" && MOCK_RUN_PATIENTS.includes(p.patient_id) ? "Example run" : "Not yet run");
            return (
              <li key={p.patient_id}>
                <button
                  type="button"
                  className={`pt-item ${p.patient_id === selected ? "on" : ""}`}
                  data-patient={p.patient_id}
                  aria-current={p.patient_id === selected ? "true" : undefined}
                  disabled={disabled && p.patient_id !== selected}
                  onClick={() => onSelect(p.patient_id)}
                  title={p.patient_id}
                >
                  <span className="pt-item-name">{fullName(p)}</span>
                  <span className="pt-item-sub">
                    MRN {mrn(p.patient_id)} · {state}
                  </span>
                </button>
              </li>
            );
          })}
          {q && !shown.length && <li className="pt-none">No patients match</li>}
        </ul>
      </div>
    </div>
  );
}

/** The main area's patient header: who is being reconciled, the run's state, and Run. */
export function PatientHead({
  patient,
  loading,
  status,
  onRun,
  running,
  canRun,
  error,
  mock,
}: {
  patient?: PatientSummary;
  loading: boolean;
  status: { label: string; tone: string } | null;
  onRun: () => void;
  running: boolean;
  canRun: boolean;
  error: string | null;
  mock: boolean;
}) {
  return (
    <section className="pt-head" aria-label="Patient">
      <div>
        <div className="pt-title">
          <h1 className="pt-name">{patient ? fullName(patient) : loading ? "Loading patients…" : "Choose a patient to begin"}</h1>
          {status && <span className={`tag ${status.tone}`}>{status.label}</span>}
        </div>
        {patient && (
          <dl className="pt-facts">
            <div>
              <dt>MRN</dt>
              <dd title={patient.patient_id}>{mrn(patient.patient_id)}</dd>
            </div>
            <div>
              <dt>Date of birth</dt>
              <dd>{fmtDate(patient.dob)}</dd>
            </div>
            <div>
              <dt>Sex</dt>
              <dd>{patient.sex ? SEX[patient.sex] ?? patient.sex : "Not recorded"}</dd>
            </div>
            <div>
              <dt>Admitted</dt>
              <dd>{fmtDate(patient.admission_date)}</dd>
            </div>
          </dl>
        )}
        {error && (
          <div className="friendly-err" role="alert">
            <span>The reconciliation didn't finish.</span>
            <button type="button" className="btn btn-line btn-sm" onClick={onRun} disabled={running || !canRun}>
              Run again
            </button>
            <TechDetails items={[["Error", error]]} />
          </div>
        )}
      </div>
      <div className="pt-actions">
        {mock && (
          <span className="badge badge-mock" title="Replaying tests/fixtures/api/*.json: hand-written examples, not real runs">
            Example data
          </span>
        )}
        <button className="btn btn-primary run-btn" type="button" onClick={onRun} disabled={running || !canRun}>
          {running ? "Reconciling…" : "Run reconciliation"}
        </button>
      </div>
    </section>
  );
}
