import { useState } from "react";
import type { DiscrepancyType, Evidence, FeedbackReason, FeedbackResponse, Finding, Source, TrustAttribute } from "../types";
import { FEEDBACK_REASONS, SOURCES, TRUST_ATTRIBUTES } from "../types";
import { REASON_LABEL, ROW_TEXT_FIELDS, attributeLabel, cleanText, fmtDate, humanize, medName, sourceLabel, typeLabel } from "../format";
import { TechDetails } from "./TechDetails";

export interface FeedbackState {
  busy?: boolean;
  error?: string;
  result?: FeedbackResponse;
}

export interface FeedbackChoice {
  verdict: "confirm" | "reject";
  reason?: FeedbackReason;
  source?: Source;
  attribute?: TrustAttribute;
}

interface Props {
  findings: Finding[];
  summary: string;
  feedback: Record<string, FeedbackState>;
  onFeedback: (f: Finding, choice: FeedbackChoice) => void;
}

// A starting point for the "which attribute is outdated" picker, as Arnav
// suggested in HANDOFF (25 Oct). The pharmacist can change it; nothing is sent
// until they press Submit.
const SUGGESTED_ATTRIBUTE: Partial<Record<DiscrepancyType, TrustAttribute>> = {
  dose: "daily_dose",
  dose_unconfirmable: "daily_dose",
  omission: "existence",
  commission: "existence",
  frequency: "frequency",
  route: "route",
  formulation: "release",
};

const PRIORITY: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };

/** Sources the finding's own evidence comes from, in the UI's source order. */
function evidenceSources(f: Finding): Source[] {
  const seen = new Set(f.evidence.map((e) => e.source));
  return SOURCES.filter((s) => seen.has(s));
}

/** One source row as hover text: its source, its words as recorded, and the SQL template that fetched it. */
const rowTitle = (e: Evidence) =>
  `${sourceLabel(e.source)}: ${ROW_TEXT_FIELDS.filter((k) => e.fields[k])
    .map((k) => e.fields[k])
    .join(" · ")} — SQL template ${e.sql_template_id}`;

function FeedbackControls({ f, state, onFeedback }: { f: Finding; state?: FeedbackState; onFeedback: Props["onFeedback"] }) {
  const sources = evidenceSources(f);
  const [rejecting, setRejecting] = useState(false);
  // No default reason: a reject files the reason the pharmacist chose, never ours.
  const [reason, setReason] = useState<FeedbackReason | "">("");
  const [source, setSource] = useState<Source | "">(sources.length === 1 ? sources[0] : "");
  const [attribute, setAttribute] = useState<TrustAttribute | "">(SUGGESTED_ATTRIBUTE[f.type] ?? "");
  const outdated = reason === "source_outdated";
  const complete = reason !== "" && (!outdated || (source !== "" && attribute !== ""));

  if (state?.result) {
    const r = state.result;
    return (
      <div className="fb-done">
        <span className={`pill ${r.verdict === "confirm" ? "sev-low" : "sev-high"}`}>
          {r.verdict === "confirm" ? "Confirmed" : `Rejected — ${REASON_LABEL[r.reason ?? "other"]}`}
        </span>
        {r.trust_updates.map((u) => (
          <span key={u.hmem_record_id} className="fb-trust">
            {sourceLabel(u.source)} · {attributeLabel(u.attribute)}: {u.before.toFixed(2)} → {u.after.toFixed(2)}
          </span>
        ))}
      </div>
    );
  }
  if (!rejecting) {
    return (
      <div className="fb-btns">
        <button type="button" className="btn btn-primary" disabled={state?.busy} onClick={() => onFeedback(f, { verdict: "confirm" })}>
          Confirm
        </button>
        <button type="button" className="btn btn-quiet" disabled={state?.busy} onClick={() => setRejecting(true)}>
          Reject with reason
        </button>
        {state?.error && <p className="error">{state.error}</p>}
      </div>
    );
  }
  return (
    <div className="fb-form">
      <label>
        <span>Reason</span>
        <select value={reason} onChange={(e) => setReason(e.target.value as FeedbackReason)}>
          <option value="" disabled>
            Select a reason…
          </option>
          {FEEDBACK_REASONS.map((r) => (
            <option key={r} value={r}>
              {REASON_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
      {outdated && (
        <>
          <label>
            <span>Outdated source</span>
            <select value={source} onChange={(e) => setSource(e.target.value as Source)}>
              <option value="" disabled>
                Select…
              </option>
              {(sources.length ? sources : SOURCES).map((s) => (
                <option key={s} value={s}>
                  {sourceLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Outdated information</span>
            <select value={attribute} onChange={(e) => setAttribute(e.target.value as TrustAttribute)}>
              <option value="" disabled>
                Select…
              </option>
              {TRUST_ATTRIBUTES.map((a) => (
                <option key={a} value={a}>
                  {attributeLabel(a)}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <div className="fb-btns">
        <button
          type="button"
          className="btn btn-primary"
          disabled={state?.busy || !complete}
          onClick={() =>
            onFeedback(f, {
              verdict: "reject",
              reason: reason as FeedbackReason,
              ...(outdated ? { source: source as Source, attribute: attribute as TrustAttribute } : {}),
            })
          }
        >
          Submit rejection
        </button>
        <button type="button" className="btn btn-quiet" onClick={() => setRejecting(false)}>
          Cancel
        </button>
      </div>
      {state?.error && <p className="error">{state.error}</p>}
    </div>
  );
}

const DETAIL_SHOWN = new Set(["conflict", "statement", "bpmh_single_source"]);
const detailItems = (d: Record<string, unknown>): [string, string][] =>
  Object.keys(d)
    .filter((k) => !DETAIL_SHOWN.has(k) || k === "conflict")
    .map((k) => [k === "atc_class" ? "ATC class" : humanize(k), typeof d[k] === "object" ? JSON.stringify(d[k]) : String(d[k])]);

function FindingRow({ f, state, onFeedback }: { f: Finding; state?: FeedbackState; onFeedback: Props["onFeedback"] }) {
  const d = f.detail ?? {};
  const str = (k: string) => (d[k] === undefined || d[k] === null || d[k] === "" ? null : String(d[k]));
  return (
    <article className="finding">
      <div className="finding-head">
        <div className="finding-title">
          <h3>{medName(f.generic)}</h3>
          <span className="finding-type">{typeLabel(f.type)}</span>
          {f.high_risk_class && (
            <span className="pill apinchs" title={`APINCHS high-alert medicine, class ${f.high_risk_class}`}>
              APINCHS · {f.high_risk_class}
            </span>
          )}
        </div>
        <div className="finding-pills">
          {f.needs_pharmacist && <span className="pill pill-review">Pharmacist review required</span>}
          <span className={`pill sev-${f.severity}`}>{PRIORITY[f.severity] ?? humanize(f.severity)} priority</span>
        </div>
      </div>
      <p className="finding-text" title={f.explanation}>
        {cleanText(f.explanation)}
      </p>
      {d.conflict === "confirm" && (
        <p className="callout callout-warn">
          <strong>Verify before acting.</strong> Confirm with the patient or prescriber first. This is not an instruction to
          stop the medicine.
        </p>
      )}
      {str("statement") && <p className="finding-note">{cleanText(str("statement"))}</p>}
      {str("bpmh_single_source") && (
        <p className="finding-note warn-text">
          Single source: only {sourceLabel(str("bpmh_single_source"))} supports this, so the medication history is not
          verified.
        </p>
      )}
      {f.intent_status === "documented_intentional" && f.intent_reason && (
        <p className="finding-note">Documented as intentional: {f.intent_reason}</p>
      )}
      {f.intent_status === "possibly_intentional" && <p className="finding-note">May be intentional; check before acting.</p>}
      {f.evidence.length > 0 && (
        <div className="evidence-chips">
          <span className="chips-label">Supporting records</span>
          {f.evidence.map((e) => (
            <span key={e.row_id} className="chip" title={rowTitle(e)} tabIndex={0}>
              {e.row_id}
            </span>
          ))}
        </div>
      )}
      <details className="src-records">
        <summary>View source records</summary>
        <table>
          <thead>
            <tr>
              <th>Record</th>
              <th>Source</th>
              <th>As recorded</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {f.evidence.map((e) => (
              <tr key={e.row_id}>
                <td>
                  <span className="mono-id">{e.row_id}</span>
                </td>
                <td>{sourceLabel(e.source)}</td>
                <td>
                  {ROW_TEXT_FIELDS.filter((k) => k !== "doc_date" && e.fields[k])
                    .map((k) => e.fields[k])
                    .join(" · ")}
                </td>
                <td className="nowrap">{fmtDate(e.fields.doc_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <div className="finding-foot">
        <div className="finding-action">
          {f.tasks.length > 0 && (
            <>
              Recommended action: <span>{f.tasks.map(cleanText).join("; ")}</span>
            </>
          )}
        </div>
        <FeedbackControls f={f} state={state} onFeedback={onFeedback} />
      </div>
      <TechDetails
        items={[
          ["Finding", f.id],
          ["Original explanation", f.explanation !== cleanText(f.explanation) ? f.explanation : null],
          ["Source rows", f.evidence.map((e) => `${e.row_id} (${e.sql_template_id})`).join(", ")],
          ["Priority score", f.priority.toFixed(2)],
          ["Intent", humanize(f.intent_status)],
          ...detailItems(d),
          ["Trust", f.trust_explanation.length ? f.trust_explanation.join("; ") : null],
          ["Memory records", f.hmem_record_ids.length ? f.hmem_record_ids.join(", ") : null],
        ]}
      />
    </article>
  );
}

/**
 * Order comes from the API (needs_pharmacist, priority). The UI only puts
 * pharmacist-review items first, high-alert (APINCHS) ones at the top, as PLAN
 * 6.7 asks; documented-intentional items go last, never hidden.
 */
export function Flags({ findings, summary, feedback, onFeedback }: Props) {
  const must = findings.filter((f) => f.needs_pharmacist);
  const ordered = [
    ...must.filter((f) => f.high_risk_class),
    ...must.filter((f) => !f.high_risk_class),
    ...findings.filter((f) => !f.needs_pharmacist && f.intent_status !== "documented_intentional"),
    ...findings.filter((f) => !f.needs_pharmacist && f.intent_status === "documented_intentional"),
  ];
  const reviewed = findings.filter((f) => feedback[f.id]?.result).length;
  return (
    <>
      {summary && (
        <p className="tab-summary" title={summary}>
          {cleanText(summary)}
        </p>
      )}
      <div className="tab-intro">
        <div>Ranked by clinical risk. High-alert (APINCHS) medicines are listed first.</div>
        <div className="tab-intro-count">
          {reviewed} of {findings.length} reviewed
        </div>
      </div>
      {!findings.length && <p className="tab-empty">No discrepancies were identified.</p>}
      {ordered.map((f) => (
        <FindingRow key={f.id} f={f} state={feedback[f.id]} onFeedback={onFeedback} />
      ))}
    </>
  );
}
