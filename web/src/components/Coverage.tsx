import type { Coverage as Cov, Notice } from "../types";
import { SOURCES } from "../types";
import { NOTICE_LABEL, sourceLabel } from "../format";

const STATE_TEXT: Record<string, string> = {
  found: "found",
  near_miss_pending: "possible match, pending review",
  not_found: "no record found",
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
  const missing = SOURCES.filter((s) => coverage[s]?.state !== "found");
  const stateText = (s: string) => (coverage[s] ? STATE_TEXT[coverage[s]!.state] ?? coverage[s]!.state : "not reported");
  return (
    <section className="coverage-wrap">
      {/* The BPMH heading follows bpmh_confirmable; `banner` is also used for
          other messages (e.g. identity review), which show without it. */}
      {!bpmhConfirmable ? (
        <div className="banner" role="alert">
          <strong>BPMH cannot be confirmed.</strong> {banner ?? "Fewer than 2 pre-admission sources were found."}
        </div>
      ) : (
        banner && (
          <div className="banner banner-warn" role="status">
            {banner}
          </div>
        )
      )}
      <div className="card coverage">
        <p className="coverage-line">
          Found in <strong>{found.length}</strong> of {SOURCES.length} sources
          {coverage.emr?.state === "found" ? ", including the admission chart" : ""}.
          {missing.map((s) => (
            <span key={s}>
              {" "}
              {sourceLabel(s)}: {stateText(s)}.
            </span>
          ))}
        </p>
        <ul className="coverage-chips">
          {SOURCES.map((s) => {
            const c = coverage[s];
            return (
              <li key={s} className={`cov cov-${c?.state ?? "unreported"}`}>
                <div className="cov-head">
                  <span className="dot" /> {sourceLabel(s)}
                  <span className="muted small"> {c?.record_key ?? ""}</span>
                </div>
                <div className="small">
                  {stateText(s)}
                  {c?.doc_date ? ` · dated ${c.doc_date}` : ""}
                </div>
                {c?.scope_notes.map((n) => (
                  <div key={n} className="small muted">
                    {n}
                  </div>
                ))}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

export function Notices({ notices }: { notices: Notice[] }) {
  if (!notices.length) return null;
  return (
    <section className="card notices">
      <h2>About our evidence</h2>
      <p className="muted small">Notices describe gaps in the records, not the patient's medicines.</p>
      <ul>
        {notices.map((n, i) => (
          <li key={i} className={`notice notice-${n.type}`}>
            <span className="badge neutral">{NOTICE_LABEL[n.type] ?? n.type}</span> {n.detail}
            {n.row_ids.length > 0 && <span className="rowids"> {n.row_ids.join(", ")}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
