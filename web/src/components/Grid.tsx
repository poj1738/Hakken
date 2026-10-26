import { useState } from "react";
import type { Coverage, Evidence, EvidenceState, FusedMed, FusedValue, Source, TrustAttribute } from "../types";
import type { FeedbackState } from "./Flags";
import { SOURCES } from "../types";
import { ROW_TEXT_FIELDS, STATE_LABEL, STATE_SHORT, attributeLabel, cleanText, fieldLabel, medName, sourceLabel, withUnit } from "../format";
import { InfoTip } from "./InfoTip";
import { Compare } from "./Compare";
import { TechDetails } from "./TechDetails";

export const gridFeedbackKey = (generic: string, attribute: string, source: string) => `grid:${generic}:${attribute}:${source}`;

interface Props {
  grid: FusedMed[];
  evidenceIndex: Record<string, Evidence>;
  coverage: Partial<Record<string, Coverage>>;
  /** RunResponse.dose_units: the unit of each medicine's resolved daily dose, when the API knows it. */
  doseUnits: Record<string, string>;
  feedback: Record<string, FeedbackState>;
  onRejectCell: (generic: string, attribute: TrustAttribute, source: Source) => void;
}

interface Cell {
  med: FusedMed;
  source: string;
}

type CellKind = "listed" | "absent" | "unknown" | "conflict" | "review";
const KIND_OF_STATE: Record<EvidenceState, CellKind> = { present: "listed", absent_in_scope: "absent", unknown: "unknown" };
const KIND_SHORT: Record<CellKind, string> = {
  listed: STATE_SHORT.present,
  absent: STATE_SHORT.absent_in_scope,
  unknown: STATE_SHORT.unknown,
  conflict: "Disagrees",
  review: "Under review",
};
const NO_ROW_TEXT = "Listed, but no source record was cited for it, so there is no provenance to show.";

/** The cited rows behind one cell: the med's row_ids that came from this source. */
function rowsFor(med: FusedMed, source: string, idx: Record<string, Evidence>): Evidence[] {
  return med.row_ids.map((id) => idx[id]).filter((e): e is Evidence => !!e && e.source === source);
}

/** Row ids the med cites that the API sent no evidence for. Shown, never dropped. */
function uncitedIds(med: FusedMed, idx: Record<string, Evidence>): string[] {
  return med.row_ids.filter((id) => !idx[id]);
}

/** Sources the API recorded as disagreeing with a resolved or unresolved attribute. */
function dissentingSources(med: FusedMed): Set<string> {
  const s = new Set<string>();
  for (const v of Object.values(med.attributes)) Object.keys(v.dissenting).forEach((k) => s.add(k));
  return s;
}

/**
 * How a cell is drawn. All three inputs are API values: the source's linkage
 * state (coverage), whether the API lists it as dissenting, and its evidence state.
 */
function kindOf(med: FusedMed, source: string, coverage: Props["coverage"], dissent: Set<string>): CellKind {
  if (coverage[source]?.state === "near_miss_pending") return "review";
  if (dissent.has(source)) return "conflict";
  return KIND_OF_STATE[med.per_source[source] ?? "unknown"];
}

/** A short code like "IR" or "PO" is shown as sent, with a tooltip; the UI does not expand it. */
function Value({ v, unit }: { v: unknown; unit?: string | null }) {
  const s = withUnit(v, unit);
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
      <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden>
        <circle cx="6" cy="6" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2 1.6" />
      </svg>
    </span>
  );
}

function RowText({ e }: { e: Evidence }) {
  const shown = ROW_TEXT_FIELDS.filter((f) => e.fields[f] !== undefined && e.fields[f] !== null && e.fields[f] !== "");
  return (
    <div className="rec">
      <div className="rec-head">
        <span className="mono-id">{e.row_id}</span>
        <span className="rec-tpl">SQL template {e.sql_template_id}</span>
      </div>
      <dl>
        {shown.map((f) => (
          <div key={f}>
            <dt>{fieldLabel(f)}</dt>
            <dd>{e.fields[f]}</dd>
          </div>
        ))}
      </dl>
      <TechDetails label="Query ID" items={[["Query", e.query_id ?? null]]} />
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
      // Only the resolved value carries the API's unit; a dissenting value is shown as sent.
      resolved: !(source in v.dissenting) && v.supporting.includes(source) && !v.abstained,
    }))
    .filter((x) => x.said !== undefined && x.said !== null);
}

function CellFeedback({ med, source, unit, feedback, onRejectCell }: { med: FusedMed; source: string; unit?: string; feedback: Props["feedback"]; onRejectCell: Props["onRejectCell"] }) {
  const values = sourceValues(med, source);
  if (!values.length) return null;
  return (
    <div className="insp-section">
      <div className="eyebrow">Recorded by {sourceLabel(source)}</div>
      {values.map(({ v, said, dissents, resolved }) => {
        const st = feedback[gridFeedbackKey(med.generic, v.attribute, source)];
        const r = st?.result;
        return (
          <div key={v.attribute} className="insp-row">
            <span className="insp-k">{attributeLabel(v.attribute)}</span>
            <span className="insp-v">
              <Value v={said} unit={resolved && v.attribute === "daily_dose" ? unit : null} />
            </span>
            {v.abstained ? (
              <span className="pill sev-medium">Unresolved</span>
            ) : dissents ? (
              <span className="pill sev-medium">Disagrees</span>
            ) : null}
            {!(v.abstained || dissents) ? null : r ? (
              <span className="pill sev-low">
                Marked outdated
                {r.trust_updates.map((u) => ` · confidence ${u.before.toFixed(2)} → ${u.after.toFixed(2)}`).join("")}
              </span>
            ) : (
              <button
                type="button"
                className="btn btn-line btn-sm"
                aria-label={`Mark ${sourceLabel(source)} ${attributeLabel(v.attribute).toLowerCase()} as outdated`}
                title={`Mark ${sourceLabel(source)} ${attributeLabel(v.attribute).toLowerCase()} as outdated`}
                disabled={st?.busy}
                onClick={() => onRejectCell(med.generic, v.attribute as TrustAttribute, source as Source)}
              >
                Mark outdated
              </button>
            )}
            {st?.error && <span className="error"> {st.error}</span>}
          </div>
        );
      })}
    </div>
  );
}

function Inspector({ cell, idx, coverage, unit, pinned, onClose, feedback, onRejectCell }: { cell: Cell; idx: Record<string, Evidence>; coverage: Props["coverage"]; unit?: string; pinned: boolean; onClose: () => void; feedback: Props["feedback"]; onRejectCell: Props["onRejectCell"] }) {
  const { med, source } = cell;
  const state = med.per_source[source] ?? "unknown";
  const rows = rowsFor(med, source, idx);
  const cov = coverage[source];
  const uncited = uncitedIds(med, idx);
  // Sources disagree or a value is unresolved: open with the side-by-side view of every source.
  const disputed = dissentingSources(med).size > 0 || med.abstained.length > 0 || Object.values(med.attributes).some((v) => v.abstained);
  const allRows = med.row_ids.map((id) => idx[id]).filter((e): e is Evidence => !!e);
  return (
    <aside className="insp" aria-live="polite">
      <div className="insp-head">
        <strong>{medName(med.generic)}</strong>
        <span className="insp-src">{sourceLabel(source)}</span>
        <span className={`cell c-${KIND_OF_STATE[state]}`}>
          <span className="dot" />
          {STATE_LABEL[state]}
        </span>
        {pinned && (
          <button type="button" className="lnk insp-close" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      {pinned && disputed && <Compare generic={med.generic} rows={allRows} med={med} coverage={coverage} unit={unit} />}
      {state === "unknown" && (
        <p className="insp-note" title="This source cannot be seen for this medicine.">
          <strong>No record</strong> — not the same as "not taking".
        </p>
      )}
      {state === "absent_in_scope" && <p className="insp-note">Source found; this medicine isn't in it.</p>}
      {cov?.state === "near_miss_pending" && <p className="insp-note">Link to the patient under review.</p>}
      {cov?.scope_notes.length ? (
        <ul className="insp-scope">
          {cov.scope_notes.map((n) => (
            <li key={n} title={n}>
              {cleanText(n)}
            </li>
          ))}
        </ul>
      ) : null}
      {/* Buttons only on a pinned (clicked) cell, so a hover never fires feedback. */}
      {pinned && <CellFeedback med={med} source={source} unit={unit} feedback={feedback} onRejectCell={onRejectCell} />}
      {!pinned && sourceValues(med, source).some((x) => x.dissents || x.v.abstained) && (
        <p className="insp-note muted">Click to compare or mark outdated.</p>
      )}
      {rows.length > 0 && (
        <div className="insp-section">
          <div className="eyebrow">Source {rows.length === 1 ? "record" : "records"}</div>
          {rows.map((e) => (
            <RowText key={e.row_id} e={e} />
          ))}
        </div>
      )}
      {!rows.length && state === "present" && <p className="insp-note warn-text">{NO_ROW_TEXT}</p>}
      {!rows.length && state !== "present" && <p className="insp-note muted">No source record cited.</p>}
      <TechDetails
        items={[
          ["ATC code", med.atc ?? null],
          ["High-alert class", med.high_risk_class ? `APINCHS ${med.high_risk_class}` : null],
          ["Records cited for this medicine", med.row_ids.join(", ")],
          ["Cited but not included in this result", uncited.length ? uncited.join(", ") : null],
          ["Linkage", cov?.record_key ?? null],
        ]}
      />
    </aside>
  );
}

/** The reconciled column: what the API resolved, as a main line and its basis. */
function Reconciled({ med, unit }: { med: FusedMed; unit?: string }) {
  const attrs = Object.values(med.attributes);
  const unresolved = attrs.filter((v) => v.abstained).map((v) => v.attribute);
  for (const a of med.abstained) if (!unresolved.includes(a)) unresolved.push(a);
  const shown = attrs.filter((v) => !v.abstained && v.attribute !== "existence");
  const from = (v: FusedValue) => (v.supporting.length ? `From ${v.supporting.map(sourceLabel).join(", ")}` : undefined);
  if (unresolved.length) {
    const disagreeing = attrs
      .filter((v) => v.abstained)
      .flatMap((v) => Object.entries(v.dissenting).map(([s, val]) => `${sourceLabel(s)} ${val}`));
    return (
      <div className="recon">
        <div className="recon-main warn-text" title="Sources disagree and no value won: verify with the patient.">
          Unresolved
        </div>
        <div className="recon-basis">
          {unresolved.map(attributeLabel).join(", ")}
          {disagreeing.length ? `: ${disagreeing.join(" vs ")}` : ""}
        </div>
      </div>
    );
  }
  if (!shown.length) return <div className="recon-basis">—</div>;
  const supporters = [...new Set(shown.flatMap((v) => v.supporting))];
  return (
    <div className="recon">
      <div className="recon-main">
        {shown.map((v, i) => (
          <span key={v.attribute} title={`${attributeLabel(v.attribute)}${from(v) ? ` · ${from(v)}` : ""}`}>
            {i > 0 && " · "}
            {v.attribute === "daily_dose" ? "Daily dose " : ""}
            <Value v={v.value} unit={v.attribute === "daily_dose" ? unit : null} />
          </span>
        ))}
      </div>
      <div className="recon-basis">From {supporters.map(sourceLabel).join(", ")}</div>
    </div>
  );
}

export function Grid({ grid, evidenceIndex, coverage, doseUnits, feedback, onRejectCell }: Props) {
  const [hover, setHover] = useState<Cell | null>(null);
  const [pinned, setPinned] = useState<Cell | null>(null);
  const shown = pinned ?? hover;
  const same = (a: Cell | null, b: Cell) => !!a && a.med === b.med && a.source === b.source;
  // The legend lists only the states this grid uses; "No record" vs "Not listed" is always explained.
  const kinds = new Set<CellKind>(["listed", "absent", "unknown"]);
  let anyNoRow = false;
  for (const med of grid) {
    const dissent = dissentingSources(med);
    for (const s of SOURCES) {
      kinds.add(kindOf(med, s, coverage, dissent));
      if (med.per_source[s] === "present" && !rowsFor(med, s, evidenceIndex).length) anyNoRow = true;
    }
  }

  return (
    <>
      <div className="sec-head">
        <h2 className="sec-title">Medication history</h2>
        <InfoTip text="Each medicine across the four sources. Select a cell to see its source record, original text and the SQL template that retrieved it." />
      </div>
      <div className="legend">
        <span className="cell c-listed">
          <span className="dot" />
          Listed
        </span>
        <span className="cell c-absent">
          <span className="dot" />
          Not listed
        </span>
        <span className="cell c-unknown" title="No record available: not the same as &quot;not taking&quot;">
          <span className="dot" />
          No record
        </span>
        {kinds.has("conflict") && (
          <span className="cell c-conflict">
            <span className="dot" />
            Sources disagree
          </span>
        )}
        {kinds.has("review") && (
          <span className="cell c-review">
            <span className="dot" />
            Linkage under review
          </span>
        )}
        {anyNoRow && (
          <span className="legend-item">
            <NoRowIcon /> No source record cited
          </span>
        )}
      </div>
      <div className="grid-scroll">
        <div className="grid-inner" role="table" aria-label="Medication history by source">
          <div className="row row-head" role="row">
            <div role="columnheader">Medicine</div>
            {SOURCES.map((s) => (
              <div key={s} role="columnheader">
                {sourceLabel(s)}
              </div>
            ))}
          </div>
          {grid.map((med) => {
            const dissent = dissentingSources(med);
            return (
              <div key={med.generic} className={`row ${med.abstained.length ? "row-unresolved" : ""} ${med.high_risk_class ? "row-alert" : ""}`} role="row">
                <div role="rowheader">
                  <div className="med-name">
                    {medName(med.generic)}
                    {med.high_risk_class && (
                      <span className="pill apinchs pill-xs" title={`High-alert medicine, APINCHS class ${med.high_risk_class}`}>
                        APINCHS · {med.high_risk_class}
                      </span>
                    )}
                  </div>
                  <Reconciled med={med} unit={doseUnits[med.generic]} />
                </div>
                {SOURCES.map((s) => {
                  const st = med.per_source[s] ?? "unknown";
                  const kind = kindOf(med, s, coverage, dissent);
                  const cell = { med, source: s };
                  const vals = Object.values(med.attributes)
                    .filter((v) => v.attribute !== "existence")
                    .map((v) => v.dissenting[s])
                    .filter(Boolean);
                  const label = `${medName(med.generic)}, ${sourceLabel(s)}: ${STATE_LABEL[st]}${kind === "conflict" ? ", sources disagree" : ""}${kind === "review" ? ", linkage under review" : ""}`;
                  return (
                    <div
                      key={s}
                      role="cell"
                      tabIndex={0}
                      aria-label={label}
                      className={`gcell ${same(pinned, cell) ? "pinned" : ""}`}
                      onMouseEnter={() => setHover(cell)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(cell)}
                      onClick={() => setPinned(same(pinned, cell) ? null : cell)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setPinned(same(pinned, cell) ? null : cell);
                        }
                      }}
                    >
                      <span className={`cell c-${kind}`} title={label}>
                        <span className="dot" />
                        {KIND_SHORT[kind]}
                      </span>
                      {st === "present" && !rowsFor(med, s, evidenceIndex).length && <NoRowIcon />}
                      {vals.length > 0 && <div className="cell-val">{vals.join("; ")}</div>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
      <div className="insp-wrap">
        {shown ? (
          <Inspector
            cell={shown}
            idx={evidenceIndex}
            coverage={coverage}
            unit={doseUnits[shown.med.generic]}
            pinned={!!pinned && shown === pinned}
            onClose={() => setPinned(null)}
            feedback={feedback}
            onRejectCell={onRejectCell}
          />
        ) : (
          <aside className="insp insp-empty">Select a cell to see its source record.</aside>
        )}
      </div>
    </>
  );
}
