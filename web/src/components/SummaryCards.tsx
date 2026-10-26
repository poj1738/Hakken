import type { RunResponse } from "../types";
import { SOURCES } from "../types";

/**
 * The four headline numbers. Each is a count of what the API returned (coverage,
 * grid, findings, tasks) or of the checklist ticks on this screen; nothing here
 * is a clinical judgement.
 */
export function SummaryCards({ run, actionsDone }: { run: RunResponse; actionsDone: number }) {
  const located = SOURCES.filter((s) => run.coverage[s]?.state === "found").length;
  const review = run.findings.filter((f) => f.needs_pharmacist).length;
  const remaining = Math.max(0, run.tasks.length - actionsDone);
  return (
    <div className="kpis">
      <div className="card kpi">
        <div className="eyebrow">Sources located</div>
        <div className="kpi-num">
          {located} <span className="kpi-of">of {SOURCES.length}</span>
        </div>
        <div className="kpi-sub">
          {run.bpmh_confirmable ? "Best possible medication history confirmable" : "Best possible medication history not confirmable"}
        </div>
      </div>
      <div className="card kpi">
        <div className="eyebrow">Medicines reconciled</div>
        <div className="kpi-num">{run.grid.length}</div>
        <div className="kpi-sub">Across admission chart, GP, pharmacy and interview</div>
      </div>
      <div className={`card kpi ${review ? "kpi-alert" : ""}`}>
        <div className="eyebrow">Discrepancies</div>
        <div className="kpi-num">{run.findings.length}</div>
        <div className="kpi-sub">
          {review ? `${review} ${review === 1 ? "requires" : "require"} pharmacist review` : "None require pharmacist review"}
        </div>
      </div>
      <div className="card kpi">
        <div className="eyebrow">Actions outstanding</div>
        <div className="kpi-num">
          {remaining} <span className="kpi-of">of {run.tasks.length}</span>
        </div>
        <div className="kpi-sub">Checklist for this session</div>
      </div>
    </div>
  );
}
