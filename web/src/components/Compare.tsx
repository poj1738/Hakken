import { useState } from "react";
import type { Coverage, Evidence, FusedMed } from "../types";
import { SOURCES } from "../types";
import { fmtValue, medName, sourceLabel, withUnit } from "../format";
import { asWritten, fillSummary, groupRows, latest, rowDate, says } from "../records";
import { InfoTip } from "./InfoTip";

/**
 * Side by side: one column per source, one row per attribute, each cell in the
 * source's own words (its newest row) with the value the API read from it.
 * A cell is highlighted only where the API says that source disagrees
 * (`dissenting`) or the attribute is unresolved (`abstained`); the screen never
 * compares values itself. Used by the grid's cell panel and by finding cards.
 */
const ROWS: { label: string; attrs: string[]; words: (e: Evidence) => string }[] = [
  { label: "Dose", attrs: ["daily_dose", "strength", "intended_dose"], words: (e) => [e.fields.dose_text, e.fields.strength_text].filter(Boolean).join(" · ") },
  { label: "Frequency", attrs: ["frequency"], words: (e) => e.fields.freq_text ?? "" },
  { label: "Form · route", attrs: ["release", "route"], words: (e) => e.fields.route_text ?? "" },
  { label: "Status", attrs: ["existence", "actually_taking"], words: (e) => e.fields.status_text ?? "" },
];

const NOT_REACHED: Record<string, string> = { not_found: "Not reached", near_miss_pending: "Link under review" };

export function Compare({
  generic,
  rows,
  med,
  coverage,
  unit,
}: {
  generic: string;
  rows: Evidence[];
  med?: FusedMed;
  coverage: Partial<Record<string, Coverage>>;
  unit?: string;
}) {
  const bySource = (s: string) => rows.filter((e) => e.source === s);
  const cols = SOURCES.filter((s) => bySource(s).length || med?.per_source[s] || coverage[s]);
  // Is this (source, row) one the API marks as disagreeing or unresolved?
  const flagged = (s: string, attrs: string[]) =>
    !!med &&
    attrs.some((a) => {
      const v = med.attributes[a];
      return !!v && (s in v.dissenting || (v.abstained && (v.supporting.includes(s) || s in v.dissenting)));
    });
  // What the API read from this source for these attributes (dissenting value, or the resolved one it supports).
  const read = (s: string, attrs: string[]) => {
    if (!med) return null;
    for (const a of attrs) {
      const v = med.attributes[a];
      if (!v) continue;
      if (s in v.dissenting) return fmtValue(v.dissenting[s]);
      if (v.supporting.includes(s) && !v.abstained && v.value != null) return a === "daily_dose" ? withUnit(v.value, unit) : fmtValue(v.value);
    }
    return null;
  };
  const anyFlag = cols.some((s) => ROWS.some((r) => flagged(s, r.attrs)));

  return (
    <div className="cmp" role="group" aria-label={`${medName(generic)}: what each source says`}>
      <div className="cmp-head">
        <span className="eyebrow">Side by side</span>
        {anyFlag && <span className="cmp-key">Highlighted: sources disagree</span>}
        <InfoTip text="Newest record per source, as written. Small text: the value MedTrace read. Highlight: disagreement or unresolved." />
      </div>
      <div className="cmp-scroll">
        <table className="cmp-table">
          <thead>
            <tr>
              <th scope="col" />
              {cols.map((s) => (
                <th key={s} scope="col">
                  {sourceLabel(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Read as</th>
              {cols.map((s) => {
                const st = med?.per_source[s];
                const missing = !bySource(s).length && coverage[s] && NOT_REACHED[coverage[s]!.state];
                return (
                  <td key={s} className={flagged(s, ["existence"]) ? "cmp-diff" : ""}>
                    {missing || (st ? says(st, bySource(s).length, med?.attributes.existence ? med.attributes.existence.dissenting[s] ?? (med.attributes.existence.supporting.includes(s) ? med.attributes.existence.value : undefined) : undefined).label : bySource(s).length ? "Listed" : "No record")}
                  </td>
                );
              })}
            </tr>
            {ROWS.map((r) => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                {cols.map((s) => {
                  const e = latest(bySource(s));
                  const words = e ? r.words(e) : "";
                  const v = read(s, r.attrs);
                  return (
                    <td key={s} className={flagged(s, r.attrs) ? "cmp-diff" : ""}>
                      {words ? <q>{words}</q> : <span className="muted">—</span>}
                      {v && <span className="cmp-read">read as {v}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <th scope="row">Date</th>
              {cols.map((s) => {
                const rs = bySource(s);
                const e = latest(rs);
                return <td key={s}>{e ? (rs.length > 1 && s === "pharmacy" ? `${rs.length} fills · last ${rowDate(e.fields.doc_date)}` : rowDate(e.fields.doc_date)) : <span className="muted">—</span>}</td>;
              })}
            </tr>
            <tr>
              <th scope="row">Record</th>
              {cols.map((s) => {
                const e = latest(bySource(s));
                return <td key={s}>{e ? <span className="mono-id" title={asWritten(e)}>{e.row_id}</span> : <span className="muted">—</span>}</td>;
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The raw rows, collapsed: identical pharmacy fills become one expandable line (S38). */
export function SourceRecords({ rows }: { rows: Evidence[] }) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  if (!rows.length) return null;
  const groups = groupRows(rows);
  return (
    <details className="src-records">
      <summary>View source records ({rows.length})</summary>
      <table className="src-table">
        <thead>
          <tr>
            <th>Record</th>
            <th>Source</th>
            <th>As written</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g, i) =>
            g.kind === "row" ? (
              <tr key={g.row.row_id}>
                <td>
                  <span className="mono-id">{g.row.row_id}</span>
                </td>
                <td>{sourceLabel(g.row.source)}</td>
                <td>{asWritten(g.row)}</td>
                <td className="nowrap">{rowDate(g.row.fields.doc_date)}</td>
              </tr>
            ) : (
              <FillRows key={`g${i}`} rows={g.rows} open={!!open[i]} onToggle={() => setOpen((o) => ({ ...o, [i]: !o[i] }))} />
            ),
          )}
        </tbody>
      </table>
    </details>
  );
}

function FillRows({ rows, open, onToggle }: { rows: Evidence[]; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="fill-group">
        <td>
          <button type="button" className="lnk" aria-expanded={open} onClick={onToggle}>
            {open ? "▾" : "▸"} {rows.length} records
          </button>
        </td>
        <td>Pharmacy</td>
        <td>
          {asWritten(rows[0])}
          <div className="fill-sum">{fillSummary(rows)}</div>
        </td>
        <td className="nowrap">{rowDate(rows[rows.length - 1].fields.doc_date)}</td>
      </tr>
      {open &&
        rows.map((e) => (
          <tr key={e.row_id} className="fill-row">
            <td>
              <span className="mono-id">{e.row_id}</span>
            </td>
            <td />
            <td className="muted">{asWritten(e)}</td>
            <td className="nowrap">{rowDate(e.fields.doc_date)}</td>
          </tr>
        ))}
    </>
  );
}
