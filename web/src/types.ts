// Hand-copied from app/schemas.py and app/domain/packs/medtrace/types.py.
// When Arnav announces a schema change in docs/HANDOFF.md, update this file in
// the same PR. Field names and literals must match the Python exactly.

export type Source = "emr" | "gp" | "pharmacy" | "patient";
export const SOURCES: Source[] = ["emr", "gp", "pharmacy", "patient"];

export type EvidenceState = "present" | "absent_in_scope" | "unknown";

export type DiscrepancyType =
  | "omission"
  | "commission"
  | "dose"
  | "frequency"
  | "formulation"
  | "route"
  | "duplication"
  | "stale_listing"
  | "dose_unconfirmable"
  | "unpropagated_discharge_change"
  | "identity_uncertain";

export type NoticeType =
  | "coverage_gap"
  | "bpmh_not_confirmable"
  | "possible_second_pharmacy"
  | "patient_only_item"
  | "conflict_abstained"
  | "stale_document"
  | "known_shortage";

export type TrustAttribute =
  | "existence"
  | "daily_dose"
  | "frequency"
  | "release"
  | "route"
  | "strength"
  | "intended_dose"
  | "actually_taking"
  | "name"
  | "admission_chart";
export const TRUST_ATTRIBUTES: TrustAttribute[] = [
  "existence",
  "daily_dose",
  "frequency",
  "release",
  "route",
  "strength",
  "intended_dose",
  "actually_taking",
  "name",
  "admission_chart",
];

export type Severity = "high" | "medium" | "low";
export type IntentStatus = "documented_intentional" | "possibly_intentional" | "likely_unintentional";
export type IdentityBand = "auto-merge" | "review" | "new";
export type IdentityTier = "ihi_exact" | "ihi_conflict" | "probabilistic";
export type CoverageState = "found" | "near_miss_pending" | "not_found";

export type RunStatus = "success" | "partial" | "error" | "running" | "needs_review";
export type AgentName = "Planner" | "Executor" | "Evaluator" | "Writer";
export type FeedbackVerdict = "confirm" | "reject";
export type FeedbackReason =
  | "wrong_patient"
  | "source_outdated"
  | "intentional_change"
  | "not_clinically_relevant"
  | "already_known"
  | "other";
export const FEEDBACK_REASONS: FeedbackReason[] = [
  "wrong_patient",
  "source_outdated",
  "intentional_change",
  "not_clinically_relevant",
  "already_known",
  "other",
];
export type HmemFeedbackKind = "helpful" | "not_helpful" | "wrong";

// ---- domain types (types.py) ----

export interface SourceRow {
  source: Source;
  row_id: string;
  source_patient_id: string;
  ihi_syn?: string | null;
  name_given?: string | null;
  name_family?: string | null;
  name_previous?: string | null;
  dob?: string | null;
  dob_raw?: string | null;
  sex?: string | null;
  postcode?: string | null;
  record_kind?: string | null;
  doc_date?: string | null;
  med_text?: string | null;
  med_code?: string | null;
  code_system?: string | null;
  strength_text?: string | null;
  dose_text?: string | null;
  route_text?: string | null;
  freq_text?: string | null;
  status_text?: string | null;
  note_text?: string | null;
  qty?: number | null;
  days_supply?: number | null;
  pharmacy_id?: string | null;
  script_type?: string | null;
}

export interface IdentityLink {
  anchor_id: string;
  candidate_id: string;
  match_weight: number;
  probability: number;
  band: IdentityBand;
  tier: IdentityTier;
  field_evidence: Record<string, string>;
  guards: string[];
}

export interface Coverage {
  source: Source;
  state: CoverageState;
  scope_notes: string[];
  record_key?: string | null;
  doc_date?: string | null;
}

export interface FusedValue {
  attribute: string;
  value?: string | number | null;
  score: number;
  runner_up?: string | number | null;
  runner_up_score: number;
  margin: number;
  abstained: boolean;
  supporting: string[];
  dissenting: Record<string, string>;
  row_ids: string[];
}

export interface FusedMed {
  generic: string;
  atc?: string | null;
  high_risk_class?: string | null;
  per_source: Partial<Record<string, EvidenceState>>;
  attributes: Record<string, FusedValue>;
  abstained: string[];
  row_ids: string[];
}

export interface Notice {
  type: NoticeType;
  detail: string;
  source?: string | null;
  generic?: string | null;
  row_ids: string[];
  tasks: string[];
}

// ---- API types (schemas.py) ----

export interface EvidenceItem {
  claim: string;
  value?: string | number | null;
  unit?: string | null;
  sql: string;
  source: string;
  row_count?: number | null;
  verified: boolean;
  world_model_entity_id?: string | null;
}

export interface Recommendation {
  text: string;
  rationale?: string | null;
  confidence: number;
  requires_human_review: boolean;
}

export interface MemoryUsed {
  memory_id: string;
  content: string;
  layer: string;
  score: number;
  retrieval_reason?: string | null;
}

export interface RunOutput {
  summary: string;
  recommendations: Recommendation[];
  evidence: EvidenceItem[];
  caveats: string[];
  artifacts: string[];
}

export interface AgentRecord {
  name: string;
  role: string;
  iterations: number;
  models_used: string[];
  routes_requested: string[];
  status: string;
}

export interface ErrorInfo {
  type: string;
  message: string;
  recoverable: boolean;
}

export interface Evidence {
  source: string;
  row_id: string;
  sql_template_id: string;
  query_id?: string | null;
  fields: Record<string, string | null>;
}

export interface Finding {
  id: string;
  type: DiscrepancyType;
  generic: string;
  high_risk_class?: string | null;
  severity: Severity;
  intent_status: IntentStatus;
  intent_reason?: string | null;
  priority: number;
  explanation: string;
  // Passed through from DiscrepancyCandidate.detail: atc_class, conflict
  // ("confirm" = ask first), bpmh_single_source, subtype, statement,
  // daily_dose_ratio. Free-form, so unknown keys are shown, never dropped.
  detail: Record<string, unknown>;
  evidence: Evidence[];
  evidence_states: Partial<Record<string, EvidenceState>>;
  tasks: string[];
  needs_pharmacist: boolean;
  trust_explanation: string[];
  hmem_record_ids: string[];
}

export interface IdentityReview {
  anchor: SourceRow;
  candidates: IdentityLink[];
  records: Record<string, SourceRow>;
}

export interface IdentityDecisionRequest {
  candidate_id: string;
  same_person: boolean;
}

export interface ModelCall {
  role: AgentName;
  requested_route: string;
  routed_model?: string | null;
  request_id?: string | null;
  tokens: Record<string, number>;
  truncated: boolean;
}

export interface TrustEntry {
  source: string;
  attribute: string;
  value: number;
  uncertainty?: number | null;
  hmem_record_id?: string | null;
}

export interface PatientSummary {
  patient_id: string;
  record_key: string;
  name_given?: string | null;
  name_family?: string | null;
  dob?: string | null;
  sex?: string | null;
  admission_date?: string | null;
}

export interface PatientsResponse {
  patients: PatientSummary[];
}

export interface TraceEvent {
  timestamp: string;
  run_id: string;
  agent_name: string;
  action: string;
  input_summary?: string | null;
  output_summary?: string | null;
  target_agent?: string | null;
  model?: string | null;
  confidence?: number | null;
  retry_count: number;
  status: string;
  step?: string | null;
  message?: string | null;
  route?: string | null;
  latency_ms?: number | null;
  tokens?: Record<string, unknown> | null;
  sql?: string | null;
  row_count?: number | null;
  engine?: string | null;
  engine_op?: string | null;
  memory_ids: string[];
  error?: string | null;
  meterless?: Record<string, unknown> | null;
}

export interface RunRequest {
  patient_id?: string | null;
  question?: string;
  domain_pack?: string | null;
  max_iterations?: number | null;
  sample_mode?: boolean | null;
  context?: Record<string, unknown>;
}

export interface RunResponse {
  run_id: string;
  status: RunStatus;
  output: RunOutput;
  agents: AgentRecord[];
  trace_id: string;
  log_file: string;
  execution_time_seconds: number;
  error?: ErrorInfo | null;
  memory_used: MemoryUsed[];
  sample_mode: boolean;
  provider_state?: string | null;
  patient_id?: string | null;
  coverage: Partial<Record<string, Coverage>>;
  bpmh_confirmable: boolean;
  banner?: string | null;
  grid: FusedMed[];
  /** generic -> unit of the grid's resolved daily_dose ("mg", "units", "mL"). Absent where the rows state none or disagree (#47). */
  dose_units?: Record<string, string>;
  findings: Finding[];
  notices: Notice[];
  tasks: string[];
  identity_review?: IdentityReview | null;
  evidence_index: Record<string, Evidence>;
  trust: TrustEntry[];
  trace: TraceEvent[];
  query_count: number;
  zetaris_ms: number;
  model_calls: ModelCall[];
}

export interface HealthResponse {
  status: string;
  sample_mode: boolean;
  domain_pack: string;
  zetaris: string;
  meterless: string;
  meterless_routes: string[];
  last_routed_model?: string | null;
}

export interface FeedbackRequest {
  run_id: string;
  target_id: string;
  verdict: FeedbackVerdict;
  reason?: FeedbackReason | null;
  // Required by the API when reason is "source_outdated": the H-MEM record to lower.
  source?: Source | null;
  attribute?: TrustAttribute | null;
}

export interface TrustUpdate {
  source: string;
  attribute: string;
  hmem_record_id: string;
  kind: HmemFeedbackKind;
  before: number;
  after: number;
  delta: number;
}

export interface AcceptanceUpdate {
  type: DiscrepancyType;
  atc_class: string;
  before: number;
  after: number;
}

export interface FeedbackResponse {
  run_id: string;
  target_id: string;
  verdict: FeedbackVerdict;
  reason?: FeedbackReason | null;
  trust_updates: TrustUpdate[];
  acceptance_updates: AcceptanceUpdate[];
}
