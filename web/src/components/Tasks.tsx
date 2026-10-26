import type { Finding, Notice } from "../types";
import { NOTICE_LABEL, cleanText, medName, typeLabel } from "../format";
import { InfoTip } from "./InfoTip";

interface Props {
  tasks: string[];
  findings: Finding[];
  notices: Notice[];
  done: Record<number, boolean>;
  onToggle: (i: number, done: boolean) => void;
}

/** Which findings and notices list this exact task text. A lookup, not a judgement. */
function originsOf(task: string, findings: Finding[], notices: Notice[]): string[] {
  const out: string[] = [];
  for (const f of findings) if (f.tasks.includes(task)) out.push(`${medName(f.generic)} · ${typeLabel(f.type)}`);
  for (const n of notices) if (n.tasks.includes(task)) out.push(`${n.generic ? `${medName(n.generic)} · ` : ""}${NOTICE_LABEL[n.type] ?? n.type}`);
  return out;
}

// The task list itself, and its order, come from the API (`RunResponse.tasks`).
// Ticks live only on this screen: they are not sent anywhere and a re-run clears them.
export function Tasks({ tasks, findings, notices, done, onToggle }: Props) {
  return (
    <>
      <div className="sec-head">
        <h2 className="sec-title">Actions</h2>
        <InfoTip text="Checklist for this session only. Ticks are not saved or sent anywhere." />
        <span className="sec-meta">
          {tasks.filter((_, i) => done[i]).length} of {tasks.length} done
        </span>
      </div>
      {!tasks.length && <p className="sec-empty">✓ No actions are required.</p>}
      {tasks.map((t, i) => {
        const origins = originsOf(t, findings, notices);
        return (
          <label key={i} className={`action ${done[i] ? "done" : ""}`}>
            <input type="checkbox" className="check" checked={!!done[i]} onChange={(e) => onToggle(i, e.target.checked)} />
            <span>
              <span className="action-text" title={t}>
                {cleanText(t)}
              </span>
              <span className="action-from">{origins.length ? origins.join("; ") : "Not linked to a discrepancy or notice"}</span>
            </span>
          </label>
        );
      })}
    </>
  );
}
