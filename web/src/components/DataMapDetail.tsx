// Static lines are taken from the repo's source notes. A date, licence or
// identifier that those notes do not state is left out. Every number comes
// from that node's own query result.

export interface DetailEntry {
  phase: "running" | "done" | "error";
  error?: string;
  result?: {
    data: (string | null)[][];
    executed_at: string;
    latency_ms: number | null;
    sql: string;
  };
}

const AU_COUNT = new Intl.NumberFormat("en-AU");
const AU_SECONDS = new Intl.NumberFormat("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function formatCount(raw: string | number | null | undefined): string | null {
  if (raw == null || raw === "") return null;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return String(raw);
  return AU_COUNT.format(n);
}

function formatSeconds(ms: number): string {
  return `${AU_SECONDS.format(ms / 1000)} s`;
}

function soleCell(result: { data: (string | null)[][] } | undefined): string | null {
  const value = result?.data[0]?.[0];
  if (value == null || value === "") return null;
  return String(value);
}

export interface NodeCopy {
  title: string;
  lines: readonly string[];
}

export const NODE_COPY: Record<string, NodeCopy> = {
  emr: {
    title: "Hospital chart",
    lines: [
      "What was charted in hospital.",
      "Medicine, strength, dose and frequency on the admission chart and earlier discharges. Synthetic.",
      "Patient IDs look like MRN0000008.",
    ],
  },
  gp: {
    title: "GP record",
    lines: [
      "What the GP prescribed.",
      "Medicine, strength and directions. The list is often stale, and often says “as directed”. Synthetic.",
      "Patient IDs look like GPP000008.",
    ],
  },
  pharmacy: {
    title: "Pharmacy dispensing",
    lines: [
      "What was actually supplied, and when.",
      "Brand, PBS code, quantity and days' supply for each fill. Synthetic.",
      "Patient IDs look like C000008.",
    ],
  },
  patient: {
    title: "Patient interview",
    lines: [
      "What the patient says they take, in their own words.",
      "For example, “sugar tablet”. No code is attached, which is why this source has no high-risk class. Synthetic.",
      "Patient IDs look like INT00008.",
    ],
  },
  lexicon: {
    title: "PBS medicines list",
    lines: [
      "Australia's list of subsidised medicines.",
      "Each product's PBS code, brand, generic name, strength, form and pack size. MedTrace uses it to tell when two differently coded lines are the same medicine, and which strengths exist.",
      "Real data: Pharmaceutical Benefits Scheme, Department of Health, Schedule 4751 (Oct 2026). Copyright retained; copied with no modification.",
    ],
  },
  apinchs: {
    title: "High-risk medicines (ACSQHC)",
    lines: [
      "Medicines a pharmacist must review first.",
      "The ACSQHC APINCHS list, keyed by ATC. It includes insulins, anticoagulants, opioids and others. MedTrace ranks a discrepancy in these classes first.",
      "Real data from the Australian Commission on Safety and Quality in Health Care.",
    ],
  },
  tga: {
    title: "TGA shortage reports",
    lines: [
      "Medicine shortages reported to the TGA.",
      "Current and anticipated shortages, matched to our medicines by their ingredients. MedTrace checks this separately, so it is not part of the semantic layer.",
      "Real data. Non-commercial use cleared 25 Oct.",
    ],
  },
  usl: {
    title: "Zetaris semantic layer",
    lines: [
      "Built once in Zetaris. Every question after that is one SELECT.",
      "Three tables: medicine (each product, from the PBS list), high_risk_class (the ACSQHC classes) and medication_statement (every medicine line from the four records, in one format, with a generic name, an ATC code and a high-risk class).",
      "The data-quality rule strength_is_a_real_product runs on medication_statement.",
    ],
  },
  medtrace: {
    title: "MedTrace",
    lines: [
      "Reconciles one patient's medicines.",
      "The Planner splits the job, the Executor queries Zetaris, the Evaluator re-checks every cited row in Zetaris, and the Writer explains each finding for a pharmacist.",
      "Every model call goes through Meterless Nightshift to NVIDIA Nemotron.",
    ],
  },
};

export function NodeDetail({
  nodeId,
  entry,
  present = false,
  quality,
  showQuality = false,
}: {
  nodeId: string;
  entry?: DetailEntry;
  present?: boolean;
  quality?: DetailEntry;
  showQuality?: boolean;
}) {
  const copy = NODE_COPY[nodeId];
  if (!copy) return null;
  return (
    <div
      className={`panel panel-pad dm-detail${present ? " dm-detail-present" : ""}`}
      role="dialog"
      aria-label={copy.title}
      id={`dm-detail-${nodeId}`}
    >
      <h3>{copy.title}</h3>
      {copy.lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
      {nodeId !== "medtrace" && <LiveFacts entry={entry} />}
      {showQuality && <QualityLine entry={quality} />}
    </div>
  );
}

function LiveFacts({ entry }: { entry?: DetailEntry }) {
  if (!entry || entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error ?? "The query failed"}</p>;
  const result = entry.result;
  const count = formatCount(soleCell(result));
  if (!result || count == null) return <p className="dm-wait">querying Zetaris…</p>;
  return (
    <div className="dm-live-facts">
      <p className="dm-num">{count} rows</p>
      {result.executed_at && <p>queried at {localTime(result.executed_at)}</p>}
      {result.latency_ms != null && <p>took {formatSeconds(result.latency_ms)}</p>}
      {result.sql && <pre className="dm-code">{result.sql}</pre>}
    </div>
  );
}

function QualityLine({ entry }: { entry?: DetailEntry }) {
  if (!entry || entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  const count = formatCount(soleCell(entry.result));
  if (count == null) return <p className="dm-wait">querying Zetaris…</p>;
  return (
    <p>
      <strong className="dm-q-num dm-num">{count}</strong> medicine lines have a strength that isn't a real product.{" "}
      <span className="dm-rule">strength_is_a_real_product</span>
    </p>
  );
}

function localTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "medium" });
}
