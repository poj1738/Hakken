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
  return (
    <div className="side-group">
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
      <ul className="pt-list" aria-labelledby="patients-label">
        {patients.map((p) => {
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
      </ul>
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
          <div className="pt-facts" title={patient.patient_id}>
            MRN {mrn(patient.patient_id)} · Born {fmtDate(patient.dob)} · {patient.sex ? SEX[patient.sex] ?? patient.sex : "Sex not recorded"} · Admitted{" "}
            {fmtDate(patient.admission_date)}
          </div>
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
        <span className="badge" title="A pharmacist must confirm every item.">
          Synthetic data · Not for clinical use
        </span>
        <button className="btn btn-primary run-btn" type="button" onClick={onRun} disabled={running || !canRun}>
          {running ? "Reconciling…" : "Run reconciliation"}
        </button>
      </div>
    </section>
  );
}
