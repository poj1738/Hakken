// Display labels and text formatting only. Nothing here decides a clinical fact:
// it turns the API's enum values, codes and machine-flavoured prose into words a
// pharmacist reads. Every place that rewrites API text keeps the original one
// click away (a "Technical details" toggle or a hover title).

import type { DiscrepancyType, EvidenceState, FeedbackReason, NoticeType } from "./types";

export const SOURCE_LABEL: Record<string, string> = {
  emr: "Admission chart",
  gp: "GP",
  pharmacy: "Pharmacy",
  patient: "Patient interview",
};
export const sourceLabel = (s: string | null | undefined) => (s ? SOURCE_LABEL[s] ?? humanize(s) : "");

/** Cell states, in the design's wording. Unknown must never read like absent. */
export const STATE_LABEL: Record<EvidenceState, string> = {
  present: "Listed",
  absent_in_scope: "Not listed",
  unknown: "No record available",
};
/** The shorter in-grid form; the full label is the cell's tooltip and the legend. */
export const STATE_SHORT: Record<EvidenceState, string> = {
  present: "Listed",
  absent_in_scope: "Not listed",
  unknown: "No record",
};

export const TYPE_LABEL: Record<DiscrepancyType, string> = {
  omission: "Omission",
  commission: "Unverified addition",
  dose: "Dose discrepancy",
  frequency: "Frequency discrepancy",
  formulation: "Formulation discrepancy",
  route: "Route discrepancy",
  duplication: "Therapeutic duplication",
  stale_listing: "Possibly discontinued",
  dose_unconfirmable: "Dose cannot be confirmed",
  unpropagated_discharge_change: "Discharge change not communicated",
  identity_uncertain: "Uncertain patient match",
};
export const typeLabel = (t: string) => TYPE_LABEL[t as DiscrepancyType] ?? humanize(t);

export const NOTICE_LABEL: Record<NoticeType, string> = {
  coverage_gap: "Coverage gap",
  bpmh_not_confirmable: "Medication history not confirmable",
  possible_second_pharmacy: "Possible second pharmacy",
  patient_only_item: "Patient-only item",
  conflict_abstained: "Unresolved — verify with patient",
  stale_document: "Stale document",
  known_shortage: "Known shortage",
};

export const REASON_LABEL: Record<FeedbackReason, string> = {
  wrong_patient: "Wrong patient",
  source_outdated: "Source outdated",
  intentional_change: "Intentional change",
  not_clinically_relevant: "Not clinically relevant",
  already_known: "Already known",
  other: "Other",
};

export const ATTRIBUTE_LABEL: Record<string, string> = {
  existence: "Existence",
  daily_dose: "Daily dose",
  frequency: "Frequency",
  release: "Release",
  route: "Route",
  strength: "Strength",
  intended_dose: "Intended dose",
  actually_taking: "Actually taking",
  name: "Name",
  admission_chart: "Admission chart",
};
export const attributeLabel = (a: string) => ATTRIBUTE_LABEL[a] ?? humanize(a);

/** Source-row field names, for the cell detail panel. */
export const FIELD_LABEL: Record<string, string> = {
  med_text: "Medicine as written",
  strength_text: "Strength",
  dose_text: "Dose",
  freq_text: "Frequency",
  route_text: "Route",
  status_text: "Status",
  qty: "Quantity",
  days_supply: "Days' supply",
  script_type: "Script type",
  pharmacy_id: "Pharmacy",
  doc_date: "Document date",
  note_text: "Note",
};
export const fieldLabel = (f: string) => FIELD_LABEL[f] ?? humanize(f);

/** "NEEDS_REVIEW" / "dose_unconfirmable" / "world_model" -> "Needs review" / "Dose unconfirmable" / "World model". */
export function humanize(s: string): string {
  const words = s.replace(/[_\-.]+/g, " ").trim().toLowerCase();
  return words ? words[0].toUpperCase() + words.slice(1) : s;
}

/** Medicine names in Title Case for display: "insulin aspart" -> "Insulin Aspart", "aspirin/clopidogrel" -> "Aspirin/Clopidogrel". */
export const medName = (g: string) => g.replace(/(^|[\s/(-])([a-z])/g, (_, sep: string, c: string) => sep + c.toUpperCase());

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const fmtValue = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

/** Viewer's local time, short: "3:21 pm". */
export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }).replace(/\s?([AP])M$/i, (_, p: string) => ` ${p.toLowerCase()}m`);
}

/** "2026-10-24" -> "24 Oct 2026"; anything else (e.g. "08/09/2026" from a source row) is shown as sent. */
export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return s;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  // Day-month-year, as in the design ("24 Feb 1951"): unambiguous for an Australian reader.
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const ROW_ID = /\b(?:EMR|GP|PHM|PAT)-[A-Z]*\d+\b/;
const RECORD_KEY = /\b(emr|gp|pharmacy|patient):[A-Z0-9]+\b/g;

/**
 * API prose, cleaned for the main view:
 * - "5 finding(s)" -> "5 findings", "1 near-miss(es)" -> "1 near-miss"
 * - snake_case finding types -> their labels, SCREAMING_CASE -> Sentence case
 * - record keys ("emr:MRN0000015") -> the source's name
 * - parentheticals that only carry internal ids (query UUIDs, audit seq, lists
 *   of source row ids) are dropped; the rows themselves are in the evidence.
 * The caller keeps the original reachable (hover title / Technical details).
 */
export function cleanText(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw;
  s = s.replace(/\(([^()]*)\)/g, (whole, inner: string) => {
    if (UUID.test(inner) || /audit seq/i.test(inner)) return "";
    const parts = inner.split(/[,;]\s*/).map((p) => p.trim()).filter(Boolean);
    const isId = (p: string) => ROW_ID.test(p) && p.split(/\s+/).length === 1;
    if (parts.length && parts.every(isId)) return "";
    // "(patient, PAT-000132)": keep the source's name, drop the row id.
    if (parts.some(isId) && parts.every((p) => isId(p) || p in SOURCE_LABEL)) {
      const names = parts.filter((p) => !isId(p)).map(sourceLabel);
      return names.length ? `(${names.join(", ")})` : "";
    }
    return whole;
  });
  s = s.replace(/[;,]?\s*audit seq\s*[\d-]+/gi, "");
  s = s.replace(/\b(\d+)((?:\s+[A-Za-z-]+){0,2}?)\s+([A-Za-z-]+)\((es|s)\)/g, (_, n: string, mid: string, w: string, suf: string) => `${n}${mid} ${Number(n) === 1 ? w : w + suf}`);
  s = s.replace(RECORD_KEY, (_, src: string) => sourceLabel(src));
  s = s.replace(/\b[a-z]+(?:_[a-z]+)+\b/g, (w) => (w in TYPE_LABEL ? typeLabel(w).toLowerCase() : w.replace(/_/g, " ")));
  s = s.replace(/\b[A-Z]{2,}(?:_[A-Z]+)+\b/g, (w) => humanize(w));
  s = s.replace(/Conflict:\s*ask patient\.?/gi, "Unresolved — verify with patient.");
  s = s.replace(/^([a-z])/, (c) => c.toUpperCase());
  return s.replace(/\s+([.,;:])/g, "$1").replace(/\s{2,}/g, " ").trim();
}

/** "grid:candesartan:daily_dose" -> "Candesartan daily dose"; "dose:rosuvastatin" -> "Rosuvastatin · Dose difference". */
export function targetLabel(id: string): string {
  const g = /^grid:(.+):([a-z_]+)$/.exec(id);
  if (g) return `${medName(g[1])} ${attributeLabel(g[2]).toLowerCase()}`;
  const f = /^([a-z_]+):(.+)$/.exec(id);
  if (f && f[1] in TYPE_LABEL) return `${medName(f[2])} · ${typeLabel(f[1])}`;
  return id;
}

/** The fields worth showing as "original text" for a source row, in reading order. */
export const ROW_TEXT_FIELDS = [
  "med_text",
  "strength_text",
  "dose_text",
  "freq_text",
  "route_text",
  "status_text",
  "qty",
  "days_supply",
  "script_type",
  "pharmacy_id",
  "doc_date",
  "note_text",
];
