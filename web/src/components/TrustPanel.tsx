import type { AcceptanceUpdate, TrustEntry, TrustUpdate } from "../types";
import { SOURCES } from "../types";
import { TYPE_LABEL, attributeLabel, sourceLabel } from "../format";

interface Props {
  trust: TrustEntry[];
  updates: TrustUpdate[];
  acceptance: AcceptanceUpdate[];
}

const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;

function Bar({ entry, update }: { entry?: TrustEntry; update?: TrustUpdate }) {
  const value = update ? update.after : entry!.value;
  const unc = entry?.uncertainty ?? null;
  return (
    <div className={`trust-row ${update ? "changed" : ""}`}>
      <div className="bar" role="img" aria-label={`${value.toFixed(2)}${unc != null ? ` ± ${unc.toFixed(2)}` : ""}`}>
        {unc != null && (
          <span className="unc" style={{ left: pct(value - unc), width: pct(Math.min(1, value + unc) - Math.max(0, value - unc)) }} />
        )}
        {update && <span className="fill before" style={{ width: pct(update.before) }} />}
        <span className="fill" style={{ width: pct(value) }} />
      </div>
      <span className="trust-num">
        {update ? (
          <>
            <s className="muted">{update.before.toFixed(2)}</s> → <strong>{update.after.toFixed(2)}</strong>{" "}
            <span className={update.delta < 0 ? "down" : "up"}>
              ({update.delta > 0 ? "+" : ""}
              {update.delta.toFixed(2)})
            </span>
          </>
        ) : (
          <>
            {value.toFixed(2)}
            {unc != null && <span className="muted"> ± {unc.toFixed(2)}</span>}
          </>
        )}
      </span>
    </div>
  );
}

export function TrustPanel({ trust, updates, acceptance }: Props) {
  if (!trust.length && !updates.length) return null;
  // Latest update per (source, attribute) wins, so repeated feedback shows the newest move.
  const upd = new Map<string, TrustUpdate>();
  updates.forEach((u) => upd.set(`${u.source}/${u.attribute}`, u));
  const keys = new Map<string, { source: string; attribute: string }>();
  trust.forEach((t) => keys.set(`${t.source}/${t.attribute}`, t));
  updates.forEach((u) => keys.set(`${u.source}/${u.attribute}`, u));
  const entry = new Map(trust.map((t) => [`${t.source}/${t.attribute}`, t]));
  const sources = [...SOURCES, ...new Set([...keys.values()].map((k) => k.source))].filter(
    (s, i, a) => a.indexOf(s) === i && [...keys.values()].some((k) => k.source === s),
  );

  return (
    <section className="card trust">
      <h2>How much each source is trusted</h2>
      <p className="muted small">
        Learned from pharmacist feedback (H-MEM). The shaded band is the uncertainty. Reject a finding as "source outdated" to
        see the bar move.
      </p>
      <div className="trust-grid">
        {sources.map((s) => (
          <div key={s} className="trust-source">
            <h3>{sourceLabel(s)}</h3>
            {[...keys.entries()]
              .filter(([, k]) => k.source === s)
              .map(([key, k]) => (
                <div key={key} className="trust-item">
                  <span className="trust-attr">{attributeLabel(k.attribute)}</span>
                  <Bar entry={entry.get(key)} update={upd.get(key)} />
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
