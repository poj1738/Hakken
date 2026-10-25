import { useState } from "react";
import type { Coverage, Evidence, EvidenceState, FusedMed } from "../types";
import { SOURCES } from "../types";
import { ROW_TEXT_FIELDS, STATE_LABEL, attributeLabel, fmtValue, sourceLabel } from "../format";

interface Props {
  grid: FusedMed[];
  evidenceIndex: Record<string, Evidence>;
  coverage: Partial<Record<string, Coverage>>;
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

function Inspector({ cell, idx, coverage, pinned, onClose }: { cell: Cell; idx: Record<string, Evidence>; coverage: Props["coverage"]; pinned: boolean; onClose: () => void }) {
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
      {rows.length ? rows.map((e) => <RowText key={e.row_id} e={e} />) : <p className="small muted">No cited row from this source.</p>}
    </aside>
  );
}

export function Grid({ grid, evidenceIndex, coverage }: Props) {
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
                      .filter((v) => v.attribute !== "existence")
                      .map((v) => (
                        <div key={v.attribute} className={v.abstained ? "abstained" : ""}>
                          <span className="muted">{attributeLabel(v.attribute)}:</span>{" "}
                          {v.abstained ? <strong>Conflict: ask patient</strong> : fmtValue(v.value)}
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
        <Inspector cell={shown} idx={evidenceIndex} coverage={coverage} pinned={!!pinned} onClose={() => setPinned(null)} />
      ) : (
        <aside className="inspector empty muted small">Hover a cell to see where it came from.</aside>
      )}
    </section>
  );
}
