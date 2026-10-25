import { useState } from "react";
import type { FeedbackReason, FeedbackResponse, Finding } from "../types";
import { FEEDBACK_REASONS } from "../types";
import { REASON_LABEL, ROW_TEXT_FIELDS, TYPE_LABEL, sourceLabel } from "../format";

export interface FeedbackState {
  busy?: boolean;
  error?: string;
  result?: FeedbackResponse;
}

interface Props {
  findings: Finding[];
  feedback: Record<string, FeedbackState>;
  onFeedback: (f: Finding, verdict: "confirm" | "reject", reason?: FeedbackReason) => void;
}

function FeedbackControls({ f, state, onFeedback }: { f: Finding; state?: FeedbackState; onFeedback: Props["onFeedback"] }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState<FeedbackReason>("source_outdated");
  if (state?.result) {
    const r = state.result;
    return (
      <div className="fb-done">
        <span className={`badge ${r.verdict === "confirm" ? "ok" : "neutral"}`}>
          {r.verdict === "confirm" ? "Confirmed" : `Rejected · ${REASON_LABEL[r.reason ?? "other"]}`}
        </span>
        {r.trust_updates.map((u) => (
          <span key={u.hmem_record_id} className="small">
            {" "}
            Trust in {sourceLabel(u.source)} {u.attribute.replace("_", " ")}: {u.before.toFixed(2)} → {u.after.toFixed(2)}
          </span>
        ))}
        {!r.trust_updates.length && !r.acceptance_updates.length && <span className="small muted"> No trust change.</span>}
      </div>
    );
  }
  return (
    <div className="fb">
      {!rejecting ? (
        <>
          <button className="ok" disabled={state?.busy} onClick={() => onFeedback(f, "confirm")}>
            Confirm
          </button>
          <button disabled={state?.busy} onClick={() => setRejecting(true)}>
            Reject…
          </button>
        </>
      ) : (
        <>
          <label className="small">
            Reason{" "}
            <select value={reason} onChange={(e) => setReason(e.target.value as FeedbackReason)}>
              {FEEDBACK_REASONS.map((r) => (
                <option key={r} value={r}>
                  {REASON_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          <button className="bad" disabled={state?.busy} onClick={() => onFeedback(f, "reject", reason)}>
            Reject
          </button>
          <button className="link" onClick={() => setRejecting(false)}>
            cancel
          </button>
        </>
      )}
      {state?.busy && <span className="spinner" />}
      {state?.error && <p className="error">{state.error}</p>}
    </div>
  );
}

function FlagCard({ f, state, onFeedback }: { f: Finding; state?: FeedbackState; onFeedback: Props["onFeedback"] }) {
  return (
    <article className={`flag sev-${f.severity}`}>
      <header>
        <span className={`badge sev-${f.severity}`}>{f.severity}</span>
        <span className="flag-type">{TYPE_LABEL[f.type] ?? f.type}</span>
        <strong className="flag-med">{f.generic}</strong>
        {f.high_risk_class && (
          <span className="badge apinchs" title="APINCHS high-risk class">
            APINCHS {f.high_risk_class}
          </span>
        )}
        {f.needs_pharmacist && <span className="badge warn">Pharmacist must review</span>}
        <span className="muted small flag-id">{f.id}</span>
      </header>
      <p className="explanation">{f.explanation}</p>
      {f.intent_status === "documented_intentional" && f.intent_reason && (
        <p className="intent small">Documented as intentional: {f.intent_reason}</p>
      )}
      {f.intent_status === "possibly_intentional" && <p className="intent small">Possibly intentional — check before acting.</p>}
      {f.tasks.length > 0 && (
        <ul className="tasks-inline">
          {f.tasks.map((t) => (
            <li key={t}>☐ {t}</li>
          ))}
        </ul>
      )}
      <details>
        <summary>Evidence ({f.evidence.length} rows)</summary>
        <table className="evidence">
          <thead>
            <tr>
              <th>Row</th>
              <th>Source</th>
              <th>Original text</th>
              <th>Template</th>
            </tr>
          </thead>
          <tbody>
            {f.evidence.map((e) => (
              <tr key={e.row_id}>
                <td>
                  <code>{e.row_id}</code>
                </td>
                <td>{sourceLabel(e.source)}</td>
                <td>
                  {ROW_TEXT_FIELDS.filter((k) => e.fields[k])
                    .map((k) => e.fields[k])
                    .join(" · ")}
                </td>
                <td>
                  <code>{e.sql_template_id}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {f.trust_explanation.length > 0 && (
          <ul className="small muted">
            {f.trust_explanation.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
      </details>
      <FeedbackControls f={f} state={state} onFeedback={onFeedback} />
    </article>
  );
}

export function Flags({ findings, feedback, onFeedback }: Props) {
  // Tiering and order come from the API (needs_pharmacist, priority). The UI
  // only puts high-risk items first inside the must-review tier, as PLAN 6.7 asks.
  const must = findings.filter((f) => f.needs_pharmacist);
  const mustSorted = [...must.filter((f) => f.high_risk_class), ...must.filter((f) => !f.high_risk_class)];
  const rest = findings.filter((f) => !f.needs_pharmacist && f.intent_status !== "documented_intentional");
  const intentional = findings.filter((f) => !f.needs_pharmacist && f.intent_status === "documented_intentional");
  const card = (f: Finding) => <FlagCard key={f.id} f={f} state={feedback[f.id]} onFeedback={onFeedback} />;

  return (
    <section className="card flags">
      <h2>Flags</h2>
      {!findings.length && <p className="muted">No discrepancies found.</p>}
      {mustSorted.length > 0 && (
        <div className="tier must">
          <h3>Must review ({mustSorted.length})</h3>
          {mustSorted.map(card)}
        </div>
      )}
      {rest.length > 0 && (
        <details className="tier">
          <summary>
            <h3>Other findings ({rest.length})</h3>
          </summary>
          {rest.map(card)}
        </details>
      )}
      {intentional.length > 0 && (
        <details className="tier">
          <summary>
            <h3>Documented as intentional ({intentional.length})</h3>
          </summary>
          {intentional.map(card)}
        </details>
      )}
    </section>
  );
}
