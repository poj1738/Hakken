import type { RunResponse } from "../types";
import { REASON_LABEL, attributeLabel, cleanText, sourceLabel, targetLabel } from "../format";
import type { AppliedTrustUpdate } from "./TrustPanel";

const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;

/**
 * The learning moment, shown big: what pharmacist feedback changed, as a
 * before/after bar. Values come from POST /feedback (`trust_updates`); on a
 * later run the "now" value is that run's own `trust` entry, and any H-MEM
 * memory the run recalled (`memory_used`) is named beside it.
 */
export function LearningHero({ run, updates }: { run: RunResponse; updates: AppliedTrustUpdate[] }) {
  // Latest move per (source, attribute).
  const latest = new Map<string, AppliedTrustUpdate>();
  updates.forEach((u) => latest.set(`${u.source}/${u.attribute}`, u));
  const moves = [...latest.values()];
  const memories = run.memory_used;
  if (!moves.length && !memories.length) return null;
  return (
    <section className="learn card" aria-label="System learned">
      <div className="learn-head">
        <span className="learn-badge">System learned</span>
        <span className="learn-sub">from pharmacist feedback</span>
      </div>
      {moves.map((u) => {
        const earlier = u.runId !== run.run_id;
        const now = earlier ? run.trust.find((t) => t.source === u.source && t.attribute === u.attribute)?.value ?? u.after : u.after;
        return (
          <div key={`${u.source}/${u.attribute}`} className="learn-move">
            <div className="learn-line">
              <strong>
                {sourceLabel(u.source)} {attributeLabel(u.attribute).toLowerCase()}
              </strong>{" "}
              <span className="learn-nums">
                {u.before.toFixed(2)} → {now.toFixed(2)}
              </span>
              {earlier && <span className="learn-tag">Applied to this run</span>}
            </div>
            <div className="learn-bars" role="img" aria-label={`Confidence before ${u.before.toFixed(2)}, now ${now.toFixed(2)}`}>
              <div className="learn-bar">
                <span className="learn-k">Before</span>
                <span className="bar">
                  <span className="bar-before" style={{ width: pct(u.before) }} />
                </span>
              </div>
              <div className="learn-bar">
                <span className="learn-k">Now</span>
                <span className="bar">
                  <span className="bar-fill" style={{ width: pct(now) }} />
                </span>
              </div>
            </div>
            <div className="learn-why" title={u.targetId}>
              {u.targetName ?? targetLabel(u.targetId)}
              {u.reason ? ` · ${REASON_LABEL[u.reason].toLowerCase()}` : ""}
              {earlier ? " · earlier patient" : ""}
            </div>
          </div>
        );
      })}
      {memories.length > 0 && (
        <div className="learn-mem">
          <span className="learn-eng">H-MEM</span> recalled {memories.length === 1 ? "a memory" : `${memories.length} memories`} for this run:{" "}
          {memories.map((m) => (
            <span key={m.memory_id} className="learn-memtext" title={`${m.memory_id} · score ${m.score.toFixed(2)}${m.retrieval_reason ? ` · ${m.retrieval_reason}` : ""}`}>
              {cleanText(m.content)}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
