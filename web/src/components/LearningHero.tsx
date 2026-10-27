import type { RunResponse } from "../types";
import { REASON_LABEL, attributeLabel, cleanText, medName, sourceLabel, targetLabel } from "../format";
import type { AppliedTrustUpdate } from "./TrustPanel";

const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;

/**
 * Where this run's resolved values involved the changed record: medicines whose
 * resolved (or unresolved) value for that attribute had the changed source
 * disagreeing. That is where a lowered trust decides the outcome. Read straight
 * from the grid's `dissenting`; every run reports the trust value itself, so the
 * trust table alone cannot say whether a run used it.
 */
function usedIn(run: RunResponse, u: AppliedTrustUpdate) {
  return run.grid
    .map((m) => ({ m, v: m.attributes[u.attribute] }))
    .filter(({ v }) => v && u.source in v.dissenting)
    .map(({ m, v }) => ({ generic: m.generic, said: v.dissenting[u.source], resolved: !v.abstained }));
}

/**
 * The learning moment. Shown big on the run the feedback was given in, and on a
 * later run only where that run's own resolved values used the changed record.
 * Elsewhere a quiet one-line note says earlier feedback is on file.
 */
export function LearningHero({ run, updates }: { run: RunResponse; updates: AppliedTrustUpdate[] }) {
  // Latest move per (source, attribute).
  const latest = new Map<string, AppliedTrustUpdate>();
  updates.forEach((u) => latest.set(`${u.source}/${u.attribute}`, u));
  const moves = [...latest.values()].map((u) => ({ u, here: u.runId === run.run_id, used: usedIn(run, u) }));
  const loud = moves.filter((x) => x.here || x.used.length);
  const quiet = moves.filter((x) => !x.here && !x.used.length);
  if (!loud.length && !quiet.length) return null;

  return (
    <>
      {loud.length > 0 && (
        <section className="learn panel" aria-label="System learned">
          <div className="learn-head">
            <span className="learn-badge">System learned</span>
            <span className="learn-sub">from pharmacist feedback</span>
          </div>
          {loud.map(({ u, here, used }) => {
            const now = here ? u.after : run.trust.find((t) => t.source === u.source && t.attribute === u.attribute)?.value ?? u.after;
            return (
              <div key={`${u.source}/${u.attribute}`} className="learn-move">
                <div className="learn-info">
                <div className="learn-line">
                  <strong>
                    {sourceLabel(u.source)} {attributeLabel(u.attribute).toLowerCase()}
                  </strong>{" "}
                  <span className="learn-nums">
                    {u.before.toFixed(2)} → {now.toFixed(2)}
                  </span>
                  {!here && <span className="learn-tag">Applied to this run</span>}
                </div>
                {!here && (
                  <div className="learn-used">
                    Used here:{" "}
                    {used.map((x, i) => (
                      <span key={x.generic}>
                        {i > 0 && "; "}
                        <strong>{medName(x.generic)}</strong> {attributeLabel(u.attribute).toLowerCase()}, {sourceLabel(u.source)} {x.said}{" "}
                        {x.resolved ? "outweighed" : "still disagrees"}
                      </span>
                    ))}
                  </div>
                )}
                <div className="learn-why" title={u.targetId}>
                  {here ? "From" : "Learned from"} {u.targetName ?? targetLabel(u.targetId)}
                  {u.reason ? ` · ${REASON_LABEL[u.reason].toLowerCase()}` : ""}
                  {here ? "" : " · earlier patient"}
                </div>
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
              </div>
            );
          })}
          {run.memory_used.length > 0 && loud.some((x) => !x.here) && (
            <div className="learn-mem">
              <span className="learn-eng">H-MEM</span> recalled {run.memory_used.length === 1 ? "a memory" : `${run.memory_used.length} memories`} for this run:{" "}
              {run.memory_used.map((m) => (
                <span key={m.memory_id} className="learn-memtext" title={`${m.memory_id} · score ${m.score.toFixed(2)}${m.retrieval_reason ? ` · ${m.retrieval_reason}` : ""}`}>
                  {cleanText(m.content)}
                </span>
              ))}
            </div>
          )}
        </section>
      )}
      {quiet.length > 0 && (
        <p className="learn-quiet" title="This run's resolved values did not involve the changed record.">
          Earlier feedback on file:{" "}
          {quiet.map(({ u }) => `${sourceLabel(u.source)} ${attributeLabel(u.attribute).toLowerCase()} ${u.before.toFixed(2)} → ${u.after.toFixed(2)}`).join("; ")}
        </p>
      )}
    </>
  );
}
