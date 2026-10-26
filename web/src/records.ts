// Source rows for display: their own words, and repeated pharmacy fills grouped
// into one line (S38). Nothing here decides a clinical fact; it arranges what
// the rows say and counts them.
import type { Evidence } from "./types";
import { fmtDate } from "./format";

/** A row date as sent: ISO (2026-10-24) or Australian day-first (08/09/2026). */
export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
  if (m) return new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
  return null;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
/** A row date in the screen's format, whichever way the source wrote it. */
export const rowDate = (s: string | null | undefined) => {
  const d = parseDate(s);
  return d ? fmtDate(iso(d)) : fmtDate(s);
};

/** Pharmacy rows are "the same fill" when everything but the date matches. */
const FILL_KEY = ["med_text", "strength_text", "dose_text", "freq_text", "route_text", "qty", "days_supply", "pharmacy_id", "script_type"];
const fillKey = (e: Evidence) => FILL_KEY.map((k) => e.fields[k] ?? "").join("|");

export type RowGroup = { kind: "row"; row: Evidence } | { kind: "fills"; rows: Evidence[] };

/** Rows in their order, with identical pharmacy fills (2 or more) gathered into one group at the first one's place. */
export function groupRows(rows: Evidence[]): RowGroup[] {
  const byKey = new Map<string, Evidence[]>();
  for (const e of rows) if (e.source === "pharmacy") byKey.set(fillKey(e), [...(byKey.get(fillKey(e)) ?? []), e]);
  const out: RowGroup[] = [];
  const done = new Set<string>();
  for (const e of rows) {
    const g = e.source === "pharmacy" ? byKey.get(fillKey(e))! : null;
    if (g && g.length > 1) {
      if (done.has(fillKey(e))) continue;
      done.add(fillKey(e));
      out.push({ kind: "fills", rows: [...g].sort((a, b) => (parseDate(a.fields.doc_date)?.getTime() ?? 0) - (parseDate(b.fields.doc_date)?.getTime() ?? 0)) });
    } else out.push({ kind: "row", row: e });
  }
  return out;
}

/** "8 fills, 24 Oct 2025 – 30 Sep 2026, same pack about every 49 days" — counted from the rows' own dates. */
export function fillSummary(rows: Evidence[]): string {
  const dates = rows.map((r) => parseDate(r.fields.doc_date)).filter((d): d is Date => !!d).sort((a, b) => a.getTime() - b.getTime());
  if (dates.length < 2) return `${rows.length} fills`;
  const first = dates[0];
  const last = dates[dates.length - 1];
  const every = Math.round((last.getTime() - first.getTime()) / 86400000 / (dates.length - 1));
  return `${rows.length} fills, ${fmtDate(iso(first))} – ${fmtDate(iso(last))}, same pack about every ${every} days`;
}

/** The newest row of a set (by its own date), for "what this source last said". */
export function latest(rows: Evidence[]): Evidence | undefined {
  return [...rows].sort((a, b) => (parseDate(b.fields.doc_date)?.getTime() ?? 0) - (parseDate(a.fields.doc_date)?.getTime() ?? 0))[0];
}

/** The fields worth reading in a records table, as written. */
export const AS_WRITTEN = ["med_text", "strength_text", "dose_text", "freq_text", "route_text", "status_text", "qty", "days_supply", "script_type", "pharmacy_id", "note_text"];
// Bare numbers get their field's name, so "1 · 30" reads "qty 1 · 30 days".
const LABELLED: Record<string, (v: string) => string> = { qty: (v) => `qty ${v}`, days_supply: (v) => `${v} days` };
export const asWritten = (e: Evidence) =>
  AS_WRITTEN.filter((k) => e.fields[k])
    .map((k) => (LABELLED[k] ? LABELLED[k](e.fields[k] as string) : e.fields[k]))
    .join(" · ");
