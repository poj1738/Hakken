import { useState } from "react";
import type { Coverage, Evidence, EvidenceState, FusedMed, Source, TrustAttribute } from "../types";
import type { FeedbackState } from "./Flags";
import { SOURCES } from "../types";
import { ROW_TEXT_FIELDS, STATE_LABEL, attributeLabel, fmtValue, sourceLabel } from "../format";

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

function RowText({ e }: { e: Evidence }) {
  const shown = ROW_TEXT_FIELDS.filter((f) => e.fields[f] !== undefined && e.fields[f] !== null && e.fields[f] !== "");
  return (
    <div className="rowtext">
      <div className="rowtext-head">
        <code>{e.row_id}</code> · {sourceLabel(e.source)} · template <code>{e.sql_template_id}</code>
        {e.query_id && (
          <>
            {" "}
            · query <code>{e.query_id}</code>
          </>
        )}
      </div>
      <dl>
        {shown.map((f) => (
          <div key={f}>
            <dt>{f}</dt>
            <dd>{e.fields[f]}</dd>
          </div>
        ))}
      </dl>
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
      <div className="small muted">
        What {sourceLabel(source)} says. Where it disagrees, you can mark its value as outdated:
      </div>
      {values.map(({ v, said, dissents }) => {
        const st = feedback[gridFeedbackKey(med.generic, v.attribute, source)];
        const r = st?.result;
        return (
          <div key={v.attribute} className="cell-fb-row small">
            <span>
              {attributeLabel(v.attribute)}: <strong>{fmtValue(said)}</strong>
              {v.abstained ? <span className="warn-text"> (conflict)</span> : dissents ? <span className="warn-text"> (disagrees)</span> : null}
            </span>
            {!(v.abstained || dissents) ? null : r ? (
              <span className="badge neutral">
                Rejected as outdated
                {r.trust_updates.map((u) => ` · trust ${u.before.toFixed(2)} → ${u.after.toFixed(2)}`).join("")}
                {!r.trust_updates.length && " · no trust change"}
              </span>
            ) : (
              <button
                className="bad small-btn"
                disabled={st?.busy}
                onClick={() => onRejectCell(med.generic, v.attribute as TrustAttribute, source as Source)}
              >
                {sourceLabel(source)} {attributeLabel(v.attribute).toLowerCase()} is outdated
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
  return (
    <aside className="inspector" aria-live="polite">
      <div className="inspector-head">
        <strong>
          {med.generic} · {sourceLabel(source)}
        </strong>
        <span className={`state state-${state}`}>
          {GLYPH[state]} {STATE_LABEL[state]}
        </span>
        {pinned && (
          <button className="link" onClick={onClose}>
            close
          </button>
        )}
      </div>
      {state === "unknown" && (
        <p className="small">
          <strong>Unknown is not "not taking".</strong> We cannot see this source for this medicine
          {cov?.state === "not_found" ? ": no record was found." : "."}
        </p>
      )}
      {state === "absent_in_scope" && (
        <p className="small">The source was found and the part of it that would list this medicine does not.</p>
      )}
      {cov?.scope_notes.length ? <p className="small muted">Scope: {cov.scope_notes.join("; ")}</p> : null}
      {/* Buttons only on a pinned (clicked) cell, so a hover never fires feedback. */}
      {pinned && <CellFeedback med={med} source={source} feedback={feedback} onRejectCell={onRejectCell} />}
      {!pinned && sourceValues(med, source).length > 0 && (
        <p className="small muted">Click the cell to mark this source's value as outdated.</p>
      )}
      {rows.map((e) => (
        <RowText key={e.row_id} e={e} />
      ))}
      {!rows.length && state === "present" && (
        <p className="small warn-text">
          Present, but the API cited no row from this source, so there is no provenance to show.
        </p>
      )}
      {!rows.length && state !== "present" && <p className="small muted">No cited row from this source.</p>}
      {uncitedIds(med, idx).length > 0 && (
        <p className="small warn-text">
          Cited but not in <code>evidence_index</code>: {uncitedIds(med, idx).join(", ")}
        </p>
      )}
    </aside>
  );
}

export function Grid({ grid, evidenceIndex, coverage, feedback, onRejectCell }: Props) {
  const [hover, setHover] = useState<Cell | null>(null);
  const [pinned, setPinned] = useState<Cell | null>(null);
  const shown = pinned ?? hover;
  const same = (a: Cell | null, b: Cell) => !!a && a.med === b.med && a.source === b.source;

  return (
    <section className="card grid-card">
      <h2>Best possible medication history</h2>
      <p className="legend small">
        <span className="state state-present">● Present</span>
        <span className="state state-absent_in_scope">○ Absent</span>
        <span className="state state-unknown">? Unknown (cannot see)</span>
        <span className="state dissent-demo">disagrees</span>
        <span className="muted">Hover or click a cell for its source rows.</span>
      </p>
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
                  <th scope="row">
                    {med.generic}
                    {med.high_risk_class && (
                      <span className="badge apinchs" title="APINCHS high-risk class">
                        APINCHS {med.high_risk_class}
                      </span>
                    )}
                    {med.atc && <div className="muted small">{med.atc}</div>}
                  </th>
                  {SOURCES.map((s) => {
                    const st = med.per_source[s] ?? "unknown";
                    const cell = { med, source: s };
                    return (
                      <td
                        key={s}
                        tabIndex={0}
                        className={`state-cell state-${st} ${dissent.has(s) ? "dissent" : ""} ${same(pinned, cell) ? "pinned" : ""}`}
                        onMouseEnter={() => setHover(cell)}
                        onMouseLeave={() => setHover(null)}
                        onFocus={() => setHover(cell)}
                        onClick={() => setPinned(same(pinned, cell) ? null : cell)}
                        onKeyDown={(e) => e.key === "Enter" && setPinned(same(pinned, cell) ? null : cell)}
                      >
                        <span className="glyph">{GLYPH[st]}</span> {STATE_LABEL[st]}
                        {st === "present" && !rowsFor(med, s, evidenceIndex).length && (
                          <span className="no-row" title="No cited row from this source">
                            {" "}
                            · no row
                          </span>
                        )}
                        {dissent.has(s) && (
                          <div className="small dissent-val">
                            {Object.values(med.attributes)
                              .map((v) => v.dissenting[s])
                              .filter(Boolean)
                              .join("; ")}
                          </div>
                        )}
                      </td>
                    );
                  })}
                  <td className="resolved">
                    {Object.values(med.attributes)
                      .filter((v) => v.attribute !== "existence" || v.abstained)
                      .map((v) => (
                        <div key={v.attribute} className={v.abstained ? "abstained" : ""}>
                          <span className="muted">{attributeLabel(v.attribute)}:</span>{" "}
                          {v.abstained ? <strong>Conflict: ask patient</strong> : fmtValue(v.value)}
                          {!v.abstained && v.supporting.length > 0 && (
                            <span className="muted small"> ({v.supporting.map(sourceLabel).join(", ")})</span>
                          )}
                        </div>
                      ))}
                    {med.abstained
                      .filter((a) => !med.attributes[a])
                      .map((a) => (
                        <div key={a} className="abstained">
                          <span className="muted">{attributeLabel(a)}:</span> <strong>Conflict: ask patient</strong>
                        </div>
                      ))}
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
        <aside className="inspector empty muted small">Hover a cell to see where it came from.</aside>
      )}
    </section>
  );
}
