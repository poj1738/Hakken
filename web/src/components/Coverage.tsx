import type { Notice } from "../types";
import { NOTICE_LABEL, cleanText, medName } from "../format";
import { InfoTip } from "./InfoTip";
import { TechDetails } from "./TechDetails";

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

/** Data quality notices from the API (stale documents, patient-only items, unresolved conflicts…), as sent. */
export function Notices({ notices }: { notices: Notice[] }) {
  return (
    <>
      <div className="sec-head">
        <h2 className="sec-title">Notices</h2>
        <InfoTip text="Data quality notices: what the sources could not show or did not agree on. They are not discrepancies." />
      </div>
      {!notices.length && <p className="sec-empty">✓ No data quality notices.</p>}
      {notices.map((n, i) => (
        <div key={i} className="notice" title={n.row_ids.length ? `Records: ${n.row_ids.join(", ")}` : undefined}>
          <div className="notice-type">
            {NOTICE_LABEL[n.type] ?? n.type}
            {n.generic ? ` · ${medName(n.generic)}` : ""}
          </div>
          <div className="notice-text">{cleanText(n.detail)}</div>
        </div>
      ))}
      <div className="sec-pad">
        <TechDetails items={notices.map((n, i): [string, string | null] => [`Notice ${i + 1} records`, n.row_ids.length ? n.row_ids.join(", ") : null])} />
      </div>
    </>
  );
}
