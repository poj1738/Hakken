import type { Notice } from "../types";
import { NOTICE_LABEL, cleanText, fmtDate, medName, scopeNote } from "../format";
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

/**
 * The API's notice text without echoing its own label: "Stale document: GP list…"
 * under the heading "Stale document" drops the prefix, and a trailing "Unresolved."
 * under "Unresolved" is dropped. ISO dates read as dates. The words are otherwise as sent.
 */
function noticeText(raw: string, label: string): string {
  let t = cleanText(raw);
  if (t.toLowerCase().startsWith(`${label.toLowerCase()}:`)) t = t.slice(label.length + 1).trim();
  if (label === "Unresolved") t = t.replace(/\s*Unresolved\.?$/, "");
  t = t.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (d) => fmtDate(d));
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Data quality notices from the API (stale documents, patient-only items, unresolved conflicts…), as sent. */
export function Notices({ notices }: { notices: Notice[] }) {
  return (
    <>
      <div className="sec-head">
        <h2 className="sec-title">Notices</h2>
        <InfoTip text="Gaps and conflicts in the sources. Not discrepancies." />
      </div>
      {!notices.length && <p className="sec-empty">No notices</p>}
      {notices.map((n, i) => (
        <div key={i} className="notice" title={n.row_ids.length ? `Records: ${n.row_ids.join(", ")}` : undefined}>
          <div className="notice-type">
            {NOTICE_LABEL[n.type] ?? n.type}
            {n.generic ? ` · ${medName(n.generic)}` : ""}
          </div>
          <div className="notice-text">{typeof n.detail === "string" ? noticeText(n.detail, NOTICE_LABEL[n.type] ?? n.type) : ""}</div>
        </div>
      ))}
      <div className="sec-pad">
        <TechDetails items={notices.map((n, i): [string, string | null] => [`Notice ${i + 1} records`, n.row_ids.length ? n.row_ids.join(", ") : null])} />
      </div>
    </>
  );
}

/** S41: scope notes one per line, each with its short label (One pharmacy only · Private scripts · Old GP list). */
export function ScopeNotes({ notes, className = "scope-notes" }: { notes: string[]; className?: string }) {
  if (!notes.length) return null;
  return (
    <ul className={className}>
      {notes.map((n) => {
        const { label, text } = scopeNote(n);
        return (
          <li key={n} title={n}>
            {label && <span className="scope-label">{label}</span>} {text}
          </li>
        );
      })}
    </ul>
  );
}
