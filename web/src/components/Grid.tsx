import { useState } from "react";
import type { Coverage, Evidence, EvidenceState, FusedMed, FusedValue, Source, TrustAttribute } from "../types";
import type { FeedbackState } from "./Flags";
import { SOURCES } from "../types";
import { ROW_TEXT_FIELDS, STATE_LABEL, attributeLabel, cleanText, fieldLabel, fmtValue, medName, sourceLabel } from "../format";
import { TechDetails } from "./TechDetails";

export const gridFeedbackKey = (generic: string, attribute: string, source: string) => `grid:${generic}:${attribute}:${source}`;

interface Props {
  grid: FusedMed[];
  evidenceIndex: Record<string, Evidence>;
  coverage: Partial<Record<string, Coverage>>;
  feedback: Record<string, FeedbackState>;
  onRejectCell: (generic: string, attribute: TrustAttribute, source: Source) => void;
}

interface Cell {
  med: FusedMed;
  source: string;
}

const GLYPH: Record<EvidenceState, string> = { present: "●", absent_in_scope: "○", unknown: "?" };
const NO_ROW_TEXT = "Present, but no source row was cited for it, so there is no provenance to show.";

/** The cited rows behind one cell: the med's row_ids that came from this source. */
function rowsFor(med: FusedMed, source: string, idx: Record<string, Evidence>): Evidence[] {
  return med.row_ids.map((id) => idx[id]).filter((e): e is Evidence => !!e && e.source === source);
}

/** Row ids the med cites that the API sent no evidence for. Shown, never dropped. */
function uncitedIds(med: FusedMed, idx: Record<string, Evidence>): string[] {
  return med.row_ids.filter((id) => !idx[id]);
}

/** Sources the API recorded as disagreeing with a resolved or abstained attribute. */
function dissentingSources(med: FusedMed): Set<string> {
  const s = new Set<string>();
  for (const v of Object.values(med.attributes)) Object.keys(v.dissenting).forEach((k) => s.add(k));
  return s;
}

/** A short code like "IR" or "PO" is shown as sent, with a tooltip; the UI does not expand it. */
function Value({ v }: { v: unknown }) {
  const s = fmtValue(v);
  if (/^[A-Z]{2,4}$/.test(s)) {
    return (
      <abbr title={`"${s}" as recorded in the source data`} className="abbr">
        {s}
      </abbr>
    );
  }
  return <>{s}</>;
}

function NoRowIcon() {
  return (
    <span className="no-row" title={NO_ROW_TEXT} aria-label={NO_ROW_TEXT} role="img">
      <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden>
        <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2 1.6" />
      </svg>
    </span>
  );
}

function RowText({ e }: { e: Evidence }) {
  const shown = ROW_TEXT_FIELDS.filter((f) => e.fields[f] !== undefined && e.fields[f] !== null && e.fields[f] !== "");
  return (
    <div className="rowtext">
      <dl>
        {shown.map((f) => (
          <div key={f}>
            <dt>{fieldLabel(f)}</dt>
            <dd>{e.fields[f]}</dd>
          </div>
        ))}
      </dl>
      <TechDetails
        items={[
          ["Source row", e.row_id],
          ["SQL template", e.sql_template_id],
          ["Query", e.query_id ?? null],
        ]}
      />
    </div>
  );
}

/** What this source said for each resolved attribute, as the API reports it. */
function sourceValues(med: FusedMed, source: string) {
  return Object.values(med.attributes)
    .map((v) => ({
      v,
      said: v.dissenting[source] ?? (v.supporting.includes(source) ? v.value : undefined),
      dissents: source in v.dissenting,
    }))
    .filter((x) => x.said !== undefined && x.said !== null);
}

function CellFeedback({ med, source, feedback, onRejectCell }: { med: FusedMed; source: string; feedback: Props["feedback"]; onRejectCell: Props["onRejectCell"] }) {
  const values = sourceValues(med, source);
  if (!values.length) return null;
  return (
    <div className="cell-feedback">
      <h4>What {sourceLabel(source)} says</h4>
      {values.map(({ v, said, dissents }) => {
        const st = feedback[gridFeedbackKey(med.generic, v.attribute, source)];
        const r = st?.result;
        return (
          <div key={v.attribute} className="cell-fb-row">
            <span className="kv">
              <span className="k">{attributeLabel(v.attribute)}</span>
              <span className="v">
                <Value v={said} />
              </span>
              {v.abstained ? <span className="tag tag-warn">Conflict</span> : dissents ? <span className="tag tag-warn">Disagrees</span> : null}
            </span>
            {!(v.abstained || dissents) ? null : r ? (
              <span className="tag">
                Marked outdated
                {r.trust_updates.map((u) => ` · trust ${u.before.toFixed(2)} → ${u.after.toFixed(2)}`).join("")}
                {!r.trust_updates.length && " · no trust change"}
              </span>
            ) : (
              <button
                className="small-btn"
                disabled={st?.busy}
                onClick={() => onRejectCell(med.generic, v.attribute as TrustAttribute, source as Source)}
              >
                Mark {sourceLabel(source)} {attributeLabel(v.attribute).toLowerCase()} as outdated
              </button>
            )}
            {st?.error && <span className="error"> {st.error}</span>}
          </div>
        );
      })}
    </div>
  );
}

function Inspector({ cell, idx, coverage, pinned, onClose, feedback, onRejectCell }: { cell: Cell; idx: Record<string, Evidence>; coverage: Props["coverage"]; pinned: boolean; onClose: () => void; feedback: Props["feedback"]; onRejectCell: Props["onRejectCell"] }) {
  const { med, source } = cell;
  const state = med.per_source[source] ?? "unknown";
  const rows = rowsFor(med, source, idx);
  const cov = coverage[source];
  const uncited = uncitedIds(med, idx);
  return (
    <aside className="inspector" aria-live="polite">
      <div className="inspector-head">
        <strong>{medName(med.generic)}</strong>
        <span className="muted">in {sourceLabel(source)}</span>
        <span className={`state state-${state}`}>
          <span className="glyph">{GLYPH[state]}</span> {STATE_LABEL[state]}
        </span>
        {pinned && (
          <button className="link" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      {state === "unknown" && (
        <p className="note">
          <strong>Unknown does not mean "not taking".</strong> This source cannot be seen for this medicine
          {cov?.state === "not_found" ? ": no record was found." : "."}
        </p>
      )}
      {state === "absent_in_scope" && <p className="note">The source was found, and the part of it that would list this medicine does not.</p>}
      {cov?.scope_notes.length ? <p className="note muted">Scope: {cov.scope_notes.map(cleanText).join("; ")}</p> : null}
      {/* Buttons only on a pinned (clicked) cell, so a hover never fires feedback. */}
      {pinned && <CellFeedback med={med} source={source} feedback={feedback} onRejectCell={onRejectCell} />}
      {!pinned && sourceValues(med, source).some((x) => x.dissents || x.v.abstained) && (
        <p className="note muted">Click the cell to mark this source's value as outdated.</p>
      )}
      {rows.length > 0 && <h4>Source {rows.length === 1 ? "record" : "records"}</h4>}
      {rows.map((e) => (
        <RowText key={e.row_id} e={e} />
      ))}
      {!rows.length && state === "present" && <p className="note warn-text">{NO_ROW_TEXT}</p>}
      {!rows.length && state !== "present" && <p className="note muted">No source row cited.</p>}
      <TechDetails
        items={[
          ["ATC code", med.atc ?? null],
          ["High-risk class", med.high_risk_class ? `APINCHS ${med.high_risk_class}` : null],
          ["Rows cited for this medicine", med.row_ids.join(", ")],
          ["Cited but not included in this result", uncited.length ? uncited.join(", ") : null],
        ]}
      />
    </aside>
  );
}

function Resolved({ med }: { med: FusedMed }) {
  const values = Object.values(med.attributes).filter((v) => v.attribute !== "existence" || v.abstained);
  const extra = med.abstained.filter((a) => !med.attributes[a]);
  if (!values.length && !extra.length) return <span className="muted">—</span>;
  const from = (v: FusedValue) => (v.supporting.length ? `From ${v.supporting.map(sourceLabel).join(", ")}` : undefined);
  return (
    <dl className="resolved-list">
      {values.map((v) => (
        <div key={v.attribute} className={v.abstained ? "abstained" : ""} title={from(v)}>
          <dt>{attributeLabel(v.attribute)}</dt>
          <dd>{v.abstained ? <strong>Conflict — ask patient</strong> : <Value v={v.value} />}</dd>
        </div>
      ))}
      {extra.map((a) => (
        <div key={a} className="abstained">
          <dt>{attributeLabel(a)}</dt>
          <dd>
            <strong>Conflict — ask patient</strong>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Grid({ grid, evidenceIndex, coverage, feedback, onRejectCell }: Props) {
  const [hover, setHover] = useState<Cell | null>(null);
  const [pinned, setPinned] = useState<Cell | null>(null);
  const shown = pinned ?? hover;
  const same = (a: Cell | null, b: Cell) => !!a && a.med === b.med && a.source === b.source;

  return (
    <section className="card grid-card">
      <div className="section-head">
        <h2>Best Possible Medication History</h2>
        <span className="section-note">{grid.length} {grid.length === 1 ? "medicine" : "medicines"}</span>
      </div>
      <div className="legend">
        <span className="state state-present">
          <span className="glyph">●</span> Present
        </span>
        <span className="state state-absent_in_scope">
          <span className="glyph">○</span> Absent
        </span>
        <span className="state state-unknown">
          <span className="glyph">?</span> Unknown
        </span>
        <span className="legend-item">
          <span className="dissent-demo" /> Sources disagree
        </span>
        <span className="legend-item">
          <NoRowIcon /> No source row cited
        </span>
        <span className="legend-hint">Select a cell to see its source records.</span>
      </div>
      <div className="table-scroll">
        <table className="bpmh">
          <thead>
            <tr>
              <th>Medicine</th>
              {SOURCES.map((s) => (
                <th key={s}>{sourceLabel(s)}</th>
              ))}
              <th>Resolved</th>
            </tr>
          </thead>
          <tbody>
            {grid.map((med) => {
              const dissent = dissentingSources(med);
              return (
                <tr key={med.generic} className={med.abstained.length ? "row-abstained" : ""}>
                  <th scope="row" title={med.atc ? `ATC ${med.atc}` : undefined}>
                    <span className="med-name">{medName(med.generic)}</span>
                    {med.high_risk_class && (
                      <span className="badge risk" title={`APINCHS high-risk medicine, class ${med.high_risk_class}`}>
                        APINCHS {med.high_risk_class}
                      </span>
                    )}
                  </th>
                  {SOURCES.map((s) => {
                    const st = med.per_source[s] ?? "unknown";
                    const cell = { med, source: s };
                    // The existence value ("absent") would only repeat the chip; the panel shows it.
                    const dissentVals = Object.values(med.attributes)
                      .filter((v) => v.attribute !== "existence")
                      .map((v) => v.dissenting[s])
                      .filter(Boolean);
                    return (
                      <td
                        key={s}
                        tabIndex={0}
                        className={`state-cell cell-${st} ${dissent.has(s) ? "dissent" : ""} ${same(pinned, cell) ? "pinned" : ""}`}
                        onMouseEnter={() => setHover(cell)}
                        onMouseLeave={() => setHover(null)}
                        onFocus={() => setHover(cell)}
                        onClick={() => setPinned(same(pinned, cell) ? null : cell)}
                        onKeyDown={(e) => e.key === "Enter" && setPinned(same(pinned, cell) ? null : cell)}
                      >
                        <span className={`state state-${st}`}>
                          <span className="glyph">{GLYPH[st]}</span> {STATE_LABEL[st]}
                        </span>
                        {st === "present" && !rowsFor(med, s, evidenceIndex).length && <NoRowIcon />}
                        {dissentVals.length > 0 && <div className="dissent-val">{dissentVals.join("; ")}</div>}
                      </td>
                    );
                  })}
                  <td className="resolved">
                    <Resolved med={med} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {shown ? (
        <Inspector cell={shown} idx={evidenceIndex} coverage={coverage} pinned={!!pinned && shown === pinned} onClose={() => setPinned(null)} feedback={feedback} onRejectCell={onRejectCell} />
      ) : (
        <aside className="inspector empty">Select a cell to see where it came from.</aside>
      )}
    </section>
  );
}
