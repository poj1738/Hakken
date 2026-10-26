import { useState } from "react";
import type { Finding, Notice } from "../types";
import { NOTICE_LABEL, cleanText, medName, typeLabel } from "../format";

interface Props {
  tasks: string[];
  findings: Finding[];
  notices: Notice[];
}

interface Origin {
  key: string;
  label: string;
  highRisk?: string | null;
  mustReview?: boolean;
}

/** Which findings and notices list this exact task text. A lookup, not a judgement. */
function originsOf(task: string, findings: Finding[], notices: Notice[]): Origin[] {
  const out: Origin[] = [];
  for (const f of findings) {
    if (f.tasks.includes(task)) {
      out.push({
        key: f.id,
        label: `${medName(f.generic)} · ${typeLabel(f.type)}`,
        highRisk: f.high_risk_class,
        mustReview: f.needs_pharmacist,
      });
    }
  }
  notices.forEach((n, i) => {
    if (n.tasks.includes(task)) out.push({ key: `n${i}`, label: NOTICE_LABEL[n.type] ?? n.type });
  });
  return out;
}

// The task list itself, and its order, come from the API (`RunResponse.tasks`).
// Ticks live only on this screen: they are not sent anywhere and a re-run clears them.
export function Tasks({ tasks, findings, notices }: Props) {
  const [done, setDone] = useState<Record<number, boolean>>({});
  if (!tasks.length) return null;
  const ticked = tasks.filter((_, i) => done[i]).length;
  return (
    <section className="card tasks">
      <div className="section-head">
        <h2>Tasks</h2>
        <span className="section-note">
          {ticked} of {tasks.length} done
        </span>
      </div>
      <p className="section-sub">A checklist for this screen only. Ticks are not saved or sent.</p>
      <ul>
        {tasks.map((t, i) => {
          const origins = originsOf(t, findings, notices);
          return (
            <li key={i}>
              <label className={done[i] ? "done" : ""}>
                <input type="checkbox" checked={!!done[i]} onChange={(e) => setDone({ ...done, [i]: e.target.checked })} />{" "}
                <span>{cleanText(t)}</span>
              </label>
              <div className="task-origin small muted">
                {origins.length ? (
                  origins.map((o) => (
                    <span key={o.key}>
                      {o.label}
                      {o.highRisk && <span className="badge risk">APINCHS {o.highRisk}</span>}
                      {o.mustReview && <span className="badge warn">Pharmacist review</span>}
                    </span>
                  ))
                ) : (
                  <span>not linked to a finding or notice</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
