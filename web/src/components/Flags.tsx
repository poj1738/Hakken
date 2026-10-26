import { useState } from "react";
import type { DiscrepancyType, FeedbackReason, FeedbackResponse, Finding, Source, TrustAttribute } from "../types";
import { FEEDBACK_REASONS, SOURCES, TRUST_ATTRIBUTES } from "../types";
import { REASON_LABEL, ROW_TEXT_FIELDS, TYPE_LABEL, attributeLabel, sourceLabel } from "../format";

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
  feedback: Record<string, FeedbackState>;
  onFeedback: (f: Finding, choice: FeedbackChoice) => void;
}

// A starting point for the "which attribute is outdated" picker, as Arnav
// suggested in HANDOFF (25 Oct). The pharmacist can change it; nothing is sent
// until they press Reject.
const SUGGESTED_ATTRIBUTE: Partial<Record<DiscrepancyType, TrustAttribute>> = {
  dose: "daily_dose",
  dose_unconfirmable: "daily_dose",
  omission: "existence",
  commission: "existence",
  frequency: "frequency",
  route: "route",
  formulation: "release",
};

/** Sources the finding's own evidence comes from, in the UI's source order. */
function evidenceSources(f: Finding): Source[] {
  const seen = new Set(f.evidence.map((e) => e.source));
  return SOURCES.filter((s) => seen.has(s));
}

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
        <span className={`badge ${r.verdict === "confirm" ? "ok" : "neutral"}`}>
          {r.verdict === "confirm" ? "Confirmed" : `Rejected · ${REASON_LABEL[r.reason ?? "other"]}`}
        </span>
        {r.trust_updates.map((u) => (
          <span key={u.hmem_record_id} className="small">
            {" "}
            Trust in {sourceLabel(u.source)} {attributeLabel(u.attribute).toLowerCase()}: {u.before.toFixed(2)} →{" "}
            {u.after.toFixed(2)}
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
          <button className="ok" disabled={state?.busy} onClick={() => onFeedback(f, { verdict: "confirm" })}>
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
              <option value="" disabled>
                Choose a reason…
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
              <label className="small">
                Outdated source{" "}
                <select value={source} onChange={(e) => setSource(e.target.value as Source)}>
                  <option value="" disabled>
                    Choose…
                  </option>
                  {(sources.length ? sources : SOURCES).map((s) => (
                    <option key={s} value={s}>
                      {sourceLabel(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="small">
                What is outdated{" "}
                <select value={attribute} onChange={(e) => setAttribute(e.target.value as TrustAttribute)}>
                  <option value="" disabled>
                    Choose…
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
          <button
            className="bad"
            disabled={state?.busy || !complete}
            onClick={() =>
              onFeedback(f, {
                verdict: "reject",
                reason: reason as FeedbackReason,
                ...(outdated ? { source: source as Source, attribute: attribute as TrustAttribute } : {}),
              })
            }
          >
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

const DETAIL_SHOWN_ELSEWHERE = new Set(["conflict", "statement", "atc_class", "bpmh_single_source", "subtype", "daily_dose_ratio"]);

/** `Finding.detail`, rendered as the API sent it. Unknown keys are listed, not dropped. */
function Detail({ d }: { d: Record<string, unknown> }) {
  const str = (k: string) => (d[k] === undefined || d[k] === null || d[k] === "" ? null : String(d[k]));
  const other = Object.keys(d).filter((k) => !DETAIL_SHOWN_ELSEWHERE.has(k));
  return (
    <>
      {d.conflict === "confirm" && (
        <p className="ask-first">
          <strong>Ask first.</strong> Confirm with the patient or prescriber before acting. This is not an instruction to stop
          the medicine.
        </p>
      )}
      {str("statement") && <p className="statement small">{str("statement")}</p>}
      {str("bpmh_single_source") && (
        <p className="small warn-text">
          Single source: only {sourceLabel(str("bpmh_single_source"))} supports this, so it is not a verified BPMH.
        </p>
      )}
      <div className="detail-tags small muted">
        {str("subtype") && <span>subtype {str("subtype")}</span>}
        {str("daily_dose_ratio") && <span>daily-dose ratio {str("daily_dose_ratio")}</span>}
        {str("atc_class") && (
          <span>
            ATC <code>{str("atc_class")}</code>
          </span>
        )}
        {other.map((k) => (
          <span key={k}>
            {k} {typeof d[k] === "object" ? JSON.stringify(d[k]) : String(d[k])}
          </span>
        ))}
      </div>
    </>
  );
}

function FlagCard({ f, state, onFeedback, evidenceOpen }: { f: Finding; state?: FeedbackState; onFeedback: Props["onFeedback"]; evidenceOpen: boolean }) {
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
      <Detail d={f.detail ?? {}} />
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
      <details open={evidenceOpen}>
        <summary>Evidence ({f.evidence.length} {f.evidence.length === 1 ? "row" : "rows"})</summary>
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
  const card = (f: Finding, open = false) => (
    <FlagCard key={f.id} f={f} state={feedback[f.id]} onFeedback={onFeedback} evidenceOpen={open} />
  );

  return (
    <section className="card flags">
      <h2>Flags</h2>
      {!findings.length && <p className="muted">No discrepancies found.</p>}
      {mustSorted.length > 0 && (
        <div className="tier must">
          <h3>Must review ({mustSorted.length})</h3>
          {mustSorted.map((f) => card(f, true))}
        </div>
      )}
      {rest.length > 0 && (
        // Open when nothing needs a pharmacist first, so a run's only findings are never hidden.
        <details className="tier" open={mustSorted.length === 0}>
          <summary>
            <h3>Other findings ({rest.length})</h3>
          </summary>
          {rest.map((f) => card(f))}
        </details>
      )}
      {intentional.length > 0 && (
        <div className="tier">
          <h3>Documented as intentional ({intentional.length})</h3>
          {/* Collapsed, never hidden: the reason is visible without opening it,
              because a documented reason can still be the wrong decision. */}
          {intentional.map((f) => (
            <details key={f.id} className="intentional">
              <summary>
                <strong>{f.generic}</strong> · {TYPE_LABEL[f.type] ?? f.type}
                <span className="muted"> — {f.intent_reason ?? "no reason recorded"}</span>
              </summary>
              {card(f)}
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
