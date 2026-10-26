import type { Coverage as Cov, Notice } from "../types";
import { SOURCES } from "../types";
import { NOTICE_LABEL, cleanText, fmtDate, sourceLabel } from "../format";
import { TechDetails } from "./TechDetails";

const STATE_TEXT: Record<string, string> = {
  found: "Found",
  near_miss_pending: "Possible match, pending review",
  not_found: "No record found",
};

export function CoverageStrip({
  coverage,
  banner,
  bpmhConfirmable,
}: {
  coverage: Partial<Record<string, Cov>>;
  banner?: string | null;
  bpmhConfirmable: boolean;
}) {
  // All four sources are always listed: one the API left out is "not reported",
  // never silently missing from the strip.
  const found = SOURCES.filter((s) => coverage[s]?.state === "found");
  const stateText = (s: string) => (coverage[s] ? STATE_TEXT[coverage[s]!.state] ?? coverage[s]!.state : "Not reported");
  return (
    <section className="coverage-wrap">
      {/* The BPMH heading follows bpmh_confirmable; `banner` is also used for
          other messages (e.g. identity review), which show without it. */}
      {!bpmhConfirmable ? (
        <div className="banner" role="alert">
          <strong>Best possible medication history cannot be confirmed.</strong>{" "}
          {cleanText(banner) || "Fewer than 2 pre-admission sources were found."}
        </div>
      ) : (
        banner && (
          <div className="banner banner-warn" role="status">
            {cleanText(banner)}
          </div>
        )
      )}
      <div className="card coverage">
        <div className="section-head">
          <h2>Sources</h2>
          <span className="section-note">
            Found in {found.length} of {SOURCES.length}
            {coverage.emr?.state === "found" ? ", including the admission chart" : ""}
          </span>
        </div>
        <ul className="coverage-chips">
          {SOURCES.map((s) => {
            const c = coverage[s];
            return (
              <li key={s} className={`cov cov-${c?.state ?? "unreported"}`} title={c?.record_key ?? undefined}>
                <div className="cov-head">
                  <span className="dot" aria-hidden /> {sourceLabel(s)}
                </div>
                <div className="cov-state">
                  {stateText(s)}
                  {c?.doc_date ? <span className="muted"> · {fmtDate(c.doc_date)}</span> : null}
                </div>
                {c?.scope_notes.map((n) => (
                  <div key={n} className="cov-note">
                    {cleanText(n)}
                  </div>
                ))}
              </li>
            );
          })}
        </ul>
        <TechDetails items={SOURCES.map((s): [string, string | null] => [sourceLabel(s), coverage[s]?.record_key ?? null])} label="Record identifiers" />
      </div>
    </section>
  );
}

export function Notices({ notices }: { notices: Notice[] }) {
  if (!notices.length) return null;
  return (
    <section className="card notices">
      <h2>About the Evidence</h2>
      <p className="section-sub">These describe gaps in the records, not the patient's medicines.</p>
      <ul>
        {notices.map((n, i) => (
          <li key={i} className={`notice notice-${n.type}`} title={n.row_ids.length ? `Rows: ${n.row_ids.join(", ")}` : undefined}>
            <span className="tag">{NOTICE_LABEL[n.type] ?? n.type}</span>
            <span>{cleanText(n.detail)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
