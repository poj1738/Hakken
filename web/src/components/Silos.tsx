import type { ReactNode } from "react";
import type { RunResponse } from "../types";
import { SOURCES } from "../types";
import { cleanText, fmtDate, sourceLabel } from "../format";
import { InfoTip } from "./InfoTip";
import { TechDetails } from "./TechDetails";

/**
 * "Four silos, one view": the Track 01 story in one picture. Each tile is one
 * record source with the state the API's `coverage` reports for it; the hub
 * counts what the API returned. Nothing here is decided by the screen.
 */
const ICON: Record<string, ReactNode> = {
  // Hospital: a building with a cross.
  emr: <path d="M4 21V8l8-4 8 4v13M9 21v-4h6v4M12 8v5M9.5 10.5h5" />,
  // GP: a stethoscope.
  gp: <path d="M6 3v6a4 4 0 0 0 8 0V3M10 13v3a4 4 0 0 0 8 0v-2M18 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" />,
  // Pharmacy: a capsule.
  pharmacy: <path d="M10.5 3.5a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7-7l7-7zM7 7l7 7" />,
  // Patient: a person.
  patient: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0" />,
};

const STATE: Record<string, { label: string; cls: string }> = {
  found: { label: "Found", cls: "s-found" },
  not_found: { label: "Not found", cls: "s-none" },
  near_miss_pending: { label: "Under review", cls: "s-review" },
  unreported: { label: "Not reported", cls: "s-idle" },
  idle: { label: "Not searched", cls: "s-idle" },
  searching: { label: "Searching…", cls: "s-idle" },
};

const CLAIM_3 = "Consistent with NSQHS Actions 4.05 and 4.06, and ACSQHC guidance that a BPMH needs at least two sources.";

export function Silos({ run, searching }: { run: RunResponse | null; searching: boolean }) {
  const cov = run?.coverage ?? {};
  const hasCov = Object.keys(cov).length > 0;
  const result = !!run && hasCov && run.status !== "running" && run.status !== "needs_review";
  const highAlert = run ? run.findings.filter((f) => f.high_risk_class).length : 0;
  return (
    <section className="silos" aria-label="Four record sources, one view">
      <ol className="silo-row">
        {SOURCES.map((s) => {
          const c = cov[s];
          const key = c ? c.state : hasCov ? "unreported" : searching ? "searching" : "idle";
          const st = STATE[key] ?? STATE.unreported;
          const notes = [
            ...(c?.scope_notes.map(cleanText) ?? []),
            ...(c?.state === "not_found" ? ["No record available — this is not the same as “not taking”."] : []),
          ];
          return (
            <li key={s} className={`silo ${st.cls}`}>
              <svg className="silo-ico" viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                {ICON[s]}
              </svg>
              <div className="silo-body">
                <div className="silo-name">
                  {s === "emr" ? "Hospital chart" : sourceLabel(s)}
                  {notes.length > 0 && <InfoTip label={`${sourceLabel(s)} limitations`} text={notes.join(" ")} />}
                </div>
                <div className="silo-state">
                  <span className="silo-dot" aria-hidden />
                  {st.label}
                </div>
                {c?.doc_date && <div className="silo-date">{fmtDate(c.doc_date)}</div>}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="silo-join" aria-hidden>
        <svg viewBox="0 0 40 120" preserveAspectRatio="none" width="40" height="100%">
          <path d="M0 15 C 24 15, 16 60, 40 60 M0 45 C 22 45, 22 60, 40 60 M0 75 C 22 75, 22 60, 40 60 M0 105 C 24 105, 16 60, 40 60" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>
      <div className="hub">
        <div className="hub-title">
          <span className="hub-logo" aria-hidden>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12h4l3-7 4 14 3-7h4" />
            </svg>
          </span>
          MedTrace · one view
        </div>
        {result ? (
          <>
            <div className="hub-stats">
              <span>
                <strong>{run!.grid.length}</strong> {run!.grid.length === 1 ? "medicine" : "medicines"}
              </span>
              <span>
                <strong>{run!.findings.length}</strong> {run!.findings.length === 1 ? "discrepancy" : "discrepancies"}
              </span>
              {highAlert > 0 && (
                <span className="hub-alert">
                  <strong>{highAlert}</strong> high-alert
                </span>
              )}
            </div>
            <div className={`hub-bpmh ${run!.bpmh_confirmable ? "" : "hub-bpmh-no"}`}>
              {run!.bpmh_confirmable ? "History confirmable" : "History not confirmable"}
              <InfoTip label="About confirmability" text={CLAIM_3} />
            </div>
          </>
        ) : (
          <div className="hub-idle">A pre-populated medication history for clinician verification</div>
        )}
      </div>
      {hasCov && (
        <div className="silo-tech">
          <TechDetails items={SOURCES.map((s): [string, string | null] => [`${sourceLabel(s)} record`, cov[s]?.record_key ?? null])} />
        </div>
      )}
    </section>
  );
}
