import type { PatientSummary } from "../types";
import { API_MODE, MOCK_RUN_PATIENTS } from "../api";

export type PatientsState = { kind: "loading" } | { kind: "ready" } | { kind: "error"; message: string };

interface Props {
  patients: PatientSummary[];
  patientsState: PatientsState;
  onRetryPatients: () => void;
  selected: string;
  onSelect: (id: string) => void;
  onRun: () => void;
  running: boolean;
  error: string | null;
}

function label(p: PatientSummary) {
  const name = [p.name_given, p.name_family].filter(Boolean).join(" ") || "(no name)";
  // Mock mode only has example runs for two patients; say so before Run, not after.
  const example = API_MODE === "mock" && MOCK_RUN_PATIENTS.includes(p.patient_id) ? " · example run" : "";
  return `${name} · ${p.patient_id}${example}`;
}

export function Picker({ patients, patientsState, onRetryPatients, selected, onSelect, onRun, running, error }: Props) {
  const p = patients.find((x) => x.patient_id === selected);
  const ready = patientsState.kind === "ready" && patients.length > 0;
  return (
    <section className="card picker">
      <h2>Patient</h2>
      <label className="sr-only" htmlFor="patient">
        Admitted patient
      </label>
      <select id="patient" value={selected} onChange={(e) => onSelect(e.target.value)} disabled={running || !ready}>
        {patientsState.kind === "loading" && <option value="">Loading patients…</option>}
        {patientsState.kind === "error" && <option value="">Patients could not be loaded</option>}
        {patientsState.kind === "ready" && !patients.length && <option value="">No admitted patients</option>}
        {patients.map((x) => (
          <option key={x.patient_id} value={x.patient_id}>
            {label(x)}
          </option>
        ))}
      </select>
      {patientsState.kind === "error" && (
        <p className="error">
          {patientsState.message}{" "}
          <button className="link" onClick={onRetryPatients}>
            Retry
          </button>
        </p>
      )}
      {p && (
        <dl className="demo">
          <div>
            <dt>DOB</dt>
            <dd>{p.dob ?? "—"}</dd>
          </div>
          <div>
            <dt>Sex</dt>
            <dd>{p.sex ?? "—"}</dd>
          </div>
          <div>
            <dt>Admitted</dt>
            <dd>{p.admission_date ?? "—"}</dd>
          </div>
        </dl>
      )}
      <button className="primary" onClick={onRun} disabled={running || !ready || !selected}>
        {running ? "Running…" : "Run reconciliation"}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
