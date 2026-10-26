import type { Coverage as Cov, Notice } from "../types";
import { SOURCES } from "../types";
import { NOTICE_LABEL, cleanText, fmtDate, medName, sourceLabel } from "../format";
import { TechDetails } from "./TechDetails";

const STATE_TEXT: Record<string, string> = {
  found: "Located",
  near_miss_pending: "Possible match — linkage under review",
  not_found: "No record available",
};

/**
 * The BPMH banner follows the API's `bpmh_confirmable`; `banner` is also used
 * for other messages (e.g. identity review), which show without the heading.
 */
export function BpmhBanner({ banner, bpmhConfirmable }: { banner?: string | null; bpmhConfirmable: boolean }) {
  if (!bpmhConfirmable) {
    return (
      <div className="alert alert-high" role="alert">
        <strong>Best possible medication history cannot be confirmed.</strong>{" "}
        {cleanText(banner) || "Fewer than two pre-admission sources were located."}
      </div>
    );
  }
  if (!banner) return null;
  return (
    <div className="alert alert-medium" role="status">
      {cleanText(banner)}
    </div>
  );
}

/** Record Sources: every one of the four sources, always listed; one the API left out is "Not reported". */
export function RecordSources({ coverage, notices }: { coverage: Partial<Record<string, Cov>>; notices: Notice[] }) {
  return (
    <div className="card side-card">
      <h2 className="side-title">Record Sources</h2>
      {SOURCES.map((s) => {
        const c = coverage[s];
        const state = c?.state ?? "unreported";
        return (
          <div key={s} className="src">
            <span className={`src-dot src-${state}`} aria-hidden />
            <div className="src-body">
              <div className="src-head">
                <span className="src-name">{sourceLabel(s)}</span>
                <span className="src-date">{c?.doc_date ? fmtDate(c.doc_date) : ""}</span>
              </div>
              <div className="src-note">{c ? STATE_TEXT[c.state] ?? c.state : "Not reported"}</div>
              {c?.scope_notes.map((n) => (
                <div key={n} className="src-note">
                  {cleanText(n)}
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {notices.length > 0 && (
        <div className="notices">
          <div className="eyebrow">Data quality notices</div>
          {notices.map((n, i) => (
            <div key={i} className="notice" title={n.row_ids.length ? `Records: ${n.row_ids.join(", ")}` : undefined}>
              <div className="notice-type">
                {NOTICE_LABEL[n.type] ?? n.type}
                {n.generic ? ` · ${medName(n.generic)}` : ""}
              </div>
              <div className="notice-text">{cleanText(n.detail)}</div>
            </div>
          ))}
        </div>
      )}
      <TechDetails
        items={[
          ...SOURCES.map((s): [string, string | null] => [`${sourceLabel(s)} record`, coverage[s]?.record_key ?? null]),
          ...notices.map((n, i): [string, string | null] => [`Notice ${i + 1} records`, n.row_ids.length ? n.row_ids.join(", ") : null]),
        ]}
      />
    </div>
  );
}
