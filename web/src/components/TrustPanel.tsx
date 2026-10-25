import type { AcceptanceUpdate, FeedbackReason, TrustEntry, TrustUpdate } from "../types";
import { SOURCES } from "../types";
import { REASON_LABEL, TYPE_LABEL, attributeLabel, sourceLabel } from "../format";

/** A trust move from POST /feedback, with the run and finding it came from. */
export interface AppliedTrustUpdate extends TrustUpdate {
  runId: string;
  targetId: string;
  reason?: FeedbackReason | null;
}

interface Props {
  trust: TrustEntry[];
  runId: string;
  updates: AppliedTrustUpdate[];
  acceptance: AcceptanceUpdate[];
}

const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
const signed = (d: number) => `${d > 0 ? "+" : ""}${d.toFixed(2)}`;

/**
 * Which value the bar shows. In the run the feedback was given on, the feedback
 * response is newer than `run.trust`, so its `after` is current. In any later
 * run, that run's own `trust` is the API's current answer and wins; the earlier
 * move is still shown as history.
 */
function Bar({ entry, update, runId }: { entry?: TrustEntry; update?: AppliedTrustUpdate; runId: string }) {
  const thisRun = !!update && update.runId === runId;
  const value = thisRun || !entry ? update!.after : entry.value;
  const unc = entry?.uncertainty ?? null;
  return (
    <div className={`trust-row ${thisRun ? "changed" : ""}`}>
      <div className="bar" role="img" aria-label={`${value.toFixed(2)}${unc != null ? ` ± ${unc.toFixed(2)}` : ""}`}>
        {unc != null && (
          <span className="unc" style={{ left: pct(value - unc), width: pct(Math.min(1, value + unc) - Math.max(0, value - unc)) }} />
        )}
        {thisRun && <span className="fill before" style={{ width: pct(update!.before) }} />}
        <span className="fill" style={{ width: pct(value) }} />
      </div>
      <span className="trust-num">
        {thisRun ? (
          <>
            <s className="muted">{update!.before.toFixed(2)}</s> → <strong>{update!.after.toFixed(2)}</strong>{" "}
            <span className={update!.delta < 0 ? "down" : "up"}>({signed(update!.delta)})</span>
          </>
        ) : (
          <>
            {value.toFixed(2)}
            {unc != null && <span className="muted"> ± {unc.toFixed(2)}</span>}
          </>
        )}
      </span>
      {update && !thisRun && (
        <span className="trust-history small muted">
          earlier feedback: {update.before.toFixed(2)} → {update.after.toFixed(2)}
        </span>
      )}
    </div>
  );
}

export function TrustPanel({ trust, runId, updates, acceptance }: Props) {
  if (!trust.length && !updates.length) return null;
  // Latest update per (source, attribute) wins, so repeated feedback shows the newest move.
  const upd = new Map<string, AppliedTrustUpdate>();
  updates.forEach((u) => upd.set(`${u.source}/${u.attribute}`, u));
  const keys = new Map<string, { source: string; attribute: string }>();
  trust.forEach((t) => keys.set(`${t.source}/${t.attribute}`, t));
  updates.forEach((u) => keys.set(`${u.source}/${u.attribute}`, u));
  const entry = new Map(trust.map((t) => [`${t.source}/${t.attribute}`, t]));
  const all = [...keys.values()];
  const sources = [...SOURCES, ...all.map((k) => k.source)].filter(
    (s, i, a) => a.indexOf(s) === i && all.some((k) => k.source === s),
  );

  return (
    <section className="card trust" id="trust-panel">
      <h2>How much each source is trusted</h2>
      <p className="muted small">
        Learned from pharmacist feedback (H-MEM). The shaded band is the uncertainty. Reject a finding as "source outdated" to
        see the bar move.
      </p>
      {updates.length > 0 && (
        <div className="trust-changes" role="status">
          <h3>What your feedback changed</h3>
          <ul>
            {updates.map((u, i) => (
              <li key={i}>
                <strong>
                  {sourceLabel(u.source)} · {attributeLabel(u.attribute).toLowerCase()}
                </strong>
                : {u.before.toFixed(2)} → <strong>{u.after.toFixed(2)}</strong>{" "}
                <span className={u.delta < 0 ? "down" : "up"}>({signed(u.delta)})</span>
                <span className="muted small">
                  {" "}
                  — {u.targetId}
                  {u.reason ? `, ${REASON_LABEL[u.reason].toLowerCase()}` : ""}
                  {u.runId !== runId ? ", on an earlier run" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="trust-grid">
        {sources.map((s) => (
          <div key={s} className="trust-source">
            <h3>{sourceLabel(s)}</h3>
            {[...keys.entries()]
              .filter(([, k]) => k.source === s)
              .map(([key, k]) => (
                <div key={key} className="trust-item" title={entry.get(key)?.hmem_record_id ?? upd.get(key)?.hmem_record_id ?? undefined}>
                  <span className="trust-attr">{attributeLabel(k.attribute)}</span>
                  <Bar entry={entry.get(key)} update={upd.get(key)} runId={runId} />
                </div>
              ))}
          </div>
        ))}
      </div>
      {acceptance.length > 0 && (
        <div className="acceptance small">
          <h3>Learned acceptance</h3>
          {acceptance.map((a, i) => (
            <div key={i}>
              {TYPE_LABEL[a.type] ?? a.type} in <code>{a.atc_class}</code>: {a.before.toFixed(2)} → <strong>{a.after.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
