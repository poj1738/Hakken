import type { PatientSummary } from "../types";

interface Props {
  patients: PatientSummary[];
  selected: string;
  onSelect: (id: string) => void;
  onRun: () => void;
  running: boolean;
  error: string | null;
}

function label(p: PatientSummary) {
  const name = [p.name_given, p.name_family].filter(Boolean).join(" ") || "(no name)";
  return `${name} · ${p.patient_id}`;
}

export function Picker({ patients, selected, onSelect, onRun, running, error }: Props) {
  const p = patients.find((x) => x.patient_id === selected);
  return (
    <section className="card picker">
      <h2>Patient</h2>
      <label className="sr-only" htmlFor="patient">
        Admitted patient
      </label>
      <select id="patient" value={selected} onChange={(e) => onSelect(e.target.value)} disabled={running || !patients.length}>
        {!patients.length && <option>Loading patients…</option>}
        {patients.map((x) => (
          <option key={x.patient_id} value={x.patient_id}>
            {label(x)}
          </option>
        ))}
      </select>
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
      <button className="primary" onClick={onRun} disabled={running || !selected}>
        {running ? "Running…" : "Run reconciliation"}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
