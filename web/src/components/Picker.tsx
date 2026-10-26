import type { PatientSummary } from "../types";
import { API_MODE, MOCK_RUN_PATIENTS } from "../api";
import { fmtDate } from "../format";
import { Stepper } from "./Stepper";
import { TechDetails } from "./TechDetails";

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
  step: 1 | 2 | 3;
}

const SEX: Record<string, string> = { F: "Female", M: "Male" };
const fullName = (p: PatientSummary) => [p.name_given, p.name_family].filter(Boolean).join(" ") || "Unnamed patient";

function optionLabel(p: PatientSummary) {
  // Mock mode only has example runs for two patients; say so before Run, not after.
  const example = API_MODE === "mock" && MOCK_RUN_PATIENTS.includes(p.patient_id) ? " · example run" : "";
  return `${fullName(p)} — ${p.patient_id}${example}`;
}

/** The white patient banner: who is being reconciled, and the controls to pick and run. */
export function Picker({ patients, patientsState, onRetryPatients, selected, onSelect, onRun, running, error, step }: Props) {
  const p = patients.find((x) => x.patient_id === selected);
  const ready = patientsState.kind === "ready" && patients.length > 0;
  return (
    <section className="banner-pt">
      <div className="banner-pt-steps">
        <Stepper current={step} busy={running} />
      </div>
      <div className="banner-pt-inner">
        <div>
          <h1 className="pt-name">
            {p ? fullName(p) : patientsState.kind === "loading" ? "Loading patients…" : "Choose a patient to begin"}
            {patientsState.kind === "loading" && <span className="spinner spinner-sm" aria-hidden />}
          </h1>
          {p && (
            <div className="pt-facts">
              <div title={p.patient_id}>
                {/* "MRN0000001" reads as "MRN 0000001", as in the design; the full id is the tooltip. */}
                MRN <strong>{p.patient_id.replace(/^MRN/i, "")}</strong>
              </div>
              <div>
                Date of birth <strong>{fmtDate(p.dob)}</strong>
              </div>
              <div>
                Sex <strong>{p.sex ? SEX[p.sex] ?? p.sex : "—"}</strong>
              </div>
              <div>
                Admitted <strong>{fmtDate(p.admission_date)}</strong>
              </div>
            </div>
          )}
          {patientsState.kind === "error" && (
            <div className="friendly-err" role="alert">
              <span>The patient list didn't load. Check that the MedTrace API is running, then try again.</span>
              <button type="button" className="btn btn-quiet btn-sm" onClick={onRetryPatients}>
                Try again
              </button>
              <TechDetails items={[["Error", patientsState.message]]} />
            </div>
          )}
          {error && (
            <div className="friendly-err" role="alert">
              <span>The reconciliation didn't finish.</span>
              <button type="button" className="btn btn-quiet btn-sm" onClick={onRun} disabled={running || !ready || !selected}>
                Run again
              </button>
              <TechDetails items={[["Error", error]]} />
            </div>
          )}
        </div>
        <div className="pt-controls">
          <div className="pt-select">
            <label htmlFor="patient">Patient</label>
            <select id="patient" value={selected} onChange={(e) => onSelect(e.target.value)} disabled={running || !ready}>
              {patientsState.kind === "loading" && <option value="">Loading patients…</option>}
              {patientsState.kind === "error" && <option value="">Patients could not be loaded</option>}
              {patientsState.kind === "ready" && !patients.length && <option value="">No admitted patients</option>}
              {patients.map((x) => (
                <option key={x.patient_id} value={x.patient_id}>
                  {optionLabel(x)}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary run-btn" type="button" onClick={onRun} disabled={running || !ready || !selected}>
            {running ? "Reconciling…" : "Run reconciliation"}
          </button>
        </div>
      </div>
    </section>
  );
}
