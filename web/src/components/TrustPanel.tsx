import type { AcceptanceUpdate, FeedbackReason, TrustEntry, TrustUpdate } from "../types";
import { SOURCES } from "../types";
import { REASON_LABEL, attributeLabel, sourceLabel, targetLabel, typeLabel } from "../format";
import { InfoTip } from "./InfoTip";

/** A trust move from POST /feedback, with the run and finding it came from. */
export interface AppliedTrustUpdate extends TrustUpdate {
  runId: string;
  targetId: string;
  /** What the pharmacist gave feedback on, as words ("Escitalopram · Dose discrepancy"), captured when it was sent. */
  targetName?: string;
  reason?: FeedbackReason | null;
}

interface Props {
  trust: TrustEntry[];
  runId: string;
  updates: AppliedTrustUpdate[];
  acceptance: AcceptanceUpdate[];
}

const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
const signed = (d: number) => `${d > 0 ? "+" : d < 0 ? "−" : ""}${Math.abs(d).toFixed(2)}`;

/**
 * Which value the bar shows. In the run the feedback was given on, the feedback
 * response is newer than `run.trust`, so its `after` is current. In any later
 * run, that run's own `trust` is the API's current answer and wins; the earlier
 * move is still shown as history.
 */
function TrustRow({ label, entry, update, runId, title }: { label: string; entry?: TrustEntry; update?: AppliedTrustUpdate; runId: string; title?: string }) {
  const thisRun = !!update && update.runId === runId;
  const value = thisRun || !entry ? update!.after : entry.value;
  const unc = entry?.uncertainty ?? null;
  return (
    <div className={`trow ${thisRun ? "changed" : ""}`} title={title}>
      <div className="trow-head">
        <span className="trow-attr">{label}</span>
        <span className="mono">
          {thisRun ? (
            <>
              <s className="muted">{update!.before.toFixed(2)}</s> → {update!.after.toFixed(2)}
            </>
          ) : (
            <>
              {value.toFixed(2)}
              {unc != null && <span className="muted"> ± {unc.toFixed(2)}</span>}
            </>
          )}
        </span>
      </div>
      <div className="bar" role="img" aria-label={`${value.toFixed(2)}${unc != null ? ` ± ${unc.toFixed(2)}` : ""}`}>
        {unc != null && <span className="bar-unc" style={{ left: pct(value - unc), width: pct(Math.min(1, value + unc) - Math.max(0, value - unc)) }} />}
        {thisRun && <span className="bar-before" style={{ width: pct(update!.before) }} />}
        <span className="bar-fill" style={{ width: pct(value) }} />
      </div>
      {update && !thisRun && (
        <div className="trow-hist">
          Earlier feedback: {update.before.toFixed(2)} → {update.after.toFixed(2)}
        </div>
      )}
    </div>
  );
}

export function TrustPanel({ trust, runId, updates, acceptance }: Props) {
  // Latest update per (source, attribute) wins, so repeated feedback shows the newest move.
  const upd = new Map<string, AppliedTrustUpdate>();
  updates.forEach((u) => upd.set(`${u.source}/${u.attribute}`, u));
  const keys = new Map<string, { source: string; attribute: string }>();
  trust.forEach((t) => keys.set(`${t.source}/${t.attribute}`, t));
  updates.forEach((u) => keys.set(`${u.source}/${u.attribute}`, u));
  const entry = new Map(trust.map((t) => [`${t.source}/${t.attribute}`, t]));
  const all = [...keys.values()];
  const sources = [...SOURCES, ...all.map((k) => k.source)].filter((s, i, a) => a.indexOf(s) === i && all.some((k) => k.source === s));

  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Source confidence</h2>
        <InfoTip text="How far each record source is relied upon for each kind of information, learned from pharmacist feedback (H-MEM). The shaded band shows the uncertainty." />
      </div>
      <div className="sec-pad">
      {updates.length > 0 && (
        <div className="change-box" role="status">
          <div className="change-title">Change from pharmacist feedback</div>
          {updates.map((u, i) => (
            <div key={i} className="change-line">
              {sourceLabel(u.source)} · {attributeLabel(u.attribute)}:{" "}
              <strong>
                {u.before.toFixed(2)} → {u.after.toFixed(2)}
              </strong>{" "}
              <span className={u.delta < 0 ? "down" : "up"}>({signed(u.delta)})</span>
              <span className="change-why">
                {" "}
                — <span title={u.targetId}>{u.targetName ?? targetLabel(u.targetId)}</span>
                {u.reason ? ` rejected as ${REASON_LABEL[u.reason].toLowerCase()}` : ""}
                {u.runId !== runId ? " (earlier reconciliation)" : ""}
              </span>
            </div>
          ))}
        </div>
      )}
      {!all.length && <p className="sec-empty">No source confidence values were returned for this reconciliation.</p>}
      <div className="trust-grid">
        {sources.map((s) => (
          <div key={s}>
            <div className="trust-src">{sourceLabel(s)}</div>
            {[...keys.entries()]
              .filter(([, k]) => k.source === s)
              .map(([key, k]) => (
                <TrustRow
                  key={key}
                  label={attributeLabel(k.attribute)}
                  entry={entry.get(key)}
                  update={upd.get(key)}
                  runId={runId}
                  title={entry.get(key)?.hmem_record_id ?? upd.get(key)?.hmem_record_id ?? undefined}
                />
              ))}
          </div>
        ))}
      </div>
      {acceptance.length > 0 && (
        <div className="change-box acceptance">
          <div className="change-title">Learned acceptance</div>
          {acceptance.map((a, i) => (
            <div key={i} className="change-line">
              {typeLabel(a.type)} (ATC <span className="mono">{a.atc_class}</span>): {a.before.toFixed(2)} → <strong>{a.after.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}
