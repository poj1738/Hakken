// Display labels only. Nothing here decides a clinical fact: it turns the API's
// enum values into words a pharmacist reads.

import type { DiscrepancyType, EvidenceState, FeedbackReason, NoticeType } from "./types";

export const SOURCE_LABEL: Record<string, string> = {
  emr: "Admission chart",
  gp: "GP",
  pharmacy: "Pharmacy",
  patient: "Patient interview",
};
export const sourceLabel = (s: string | null | undefined) => (s ? SOURCE_LABEL[s] ?? s : "");

export const STATE_LABEL: Record<EvidenceState, string> = {
  present: "Present",
  absent_in_scope: "Absent",
  unknown: "Unknown",
};

export const TYPE_LABEL: Record<DiscrepancyType, string> = {
  omission: "Omission",
  commission: "Commission",
  dose: "Dose",
  frequency: "Frequency",
  formulation: "Formulation",
  route: "Route",
  duplication: "Duplication",
  stale_listing: "Stale listing",
  dose_unconfirmable: "Dose unconfirmable",
  unpropagated_discharge_change: "Discharge change not passed on",
  identity_uncertain: "Identity uncertain",
};

export const NOTICE_LABEL: Record<NoticeType, string> = {
  coverage_gap: "Coverage gap",
  bpmh_not_confirmable: "BPMH not confirmable",
  possible_second_pharmacy: "Possible second pharmacy",
  patient_only_item: "Patient-only item",
  conflict_abstained: "Conflict: ask patient",
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
export const attributeLabel = (a: string) => ATTRIBUTE_LABEL[a] ?? a;

export const fmtValue = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
