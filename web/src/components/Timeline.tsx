import { useEffect, useRef, useState } from "react";
import type { RunResponse, TraceEvent } from "../types";
import { OFFLINE_MODEL, cleanText, engineLabel, fmtTime, humanize, plural } from "../format";
import { TechDetails } from "./TechDetails";
import { AgentTag } from "./Agent";
import { type LogFilter, matches, routedModel } from "../trace";

// Step names from the orchestrator, as a reader would say them.
const STEP_LABEL: Record<string, string> = {
  START: "Started",
  PLAN: "Planning",
  FIND_IDENTITY: "Identity resolution",
  NEEDS_REVIEW: "Identity review required",
  COVERAGE: "Source coverage",
  FETCH_MEDS: "Record retrieval",
  NORMALISE: "Normalisation",
  RESOLVE_FREE_TEXT: "Free-text resolution",
  FUSE: "Comparison",
  DETECT: "Discrepancy detection",
  PRIORITISE: "Prioritisation",
  DRAFT: "Report drafting",
  VERIFY: "Verification",
  CRITIQUE: "Review",
  DONE: "Report prepared",
};
// The API records an agent step its offline fallback answered with
// routed_model "offline-heuristic"; only the rest reached Nightshift.
const OFFLINE = OFFLINE_MODEL;
function footModels(calls: RunResponse["model_calls"]): string {
  const live = calls.filter((c) => c.routed_model && c.routed_model !== OFFLINE).length;
  const offline = calls.length - live;
  const parts = [];
  if (live || !offline) parts.push(`${plural(live, "model call")} via Nightshift`);
  if (offline) parts.push(`${plural(offline, "agent step")} offline`);
  return parts.join(" · ");
}

const stepLabel = (e: TraceEvent) => STEP_LABEL[e.step ?? ""] ?? humanize(e.step ?? e.action);

/** One step's tags: the Meterless engine it used, and the model that answered it, both from the trace. */
function StepTags({ e }: { e: TraceEvent }) {
  const m = routedModel(e);
  return (
    <>
      {e.engine && (
        <span className="tag tag-engine" title={`Meterless ${engineLabel(e.engine)}${e.engine_op ? `: ${e.engine_op}` : ""}`}>
          {engineLabel(e.engine)}
        </span>
      )}
      {m &&
        (m === OFFLINE ? (
          <span className="tag tag-off" title="Answered by the offline fallback; no model was called">
            Offline
          </span>
        ) : (
          <span className="tag tag-model" title={`Answered by ${m}${e.route ? ` (requested ${e.route})` : ""}`}>
            {m.replace(/^nvidia\//, "")}
          </span>
        ))}
    </>
  );
}

/**
 * Item 10: each step's one-line summary is a fixed plain-English label, plus a
 * count only where the API gives it as a structured field (row_count, coverage).
 * The free-text message is never parsed or cut; it stays under "Show details".
 */
const SUMMARY: Record<string, string> = {
  FIND_IDENTITY: "Matched the patient across sources",
  NEEDS_REVIEW: "Paused for an identity check",
  FETCH_MEDS: "Gathered medicine records",
  NORMALISE: "Standardised medicine names",
  RESOLVE_FREE_TEXT: "Interpreted free-text entries",
  FUSE: "Compared sources",
  DETECT: "Checked for discrepancies",
  PRIORITISE: "Ranked findings by risk",
  CHECK_SHORTAGES: "Checked known shortages",
  DRAFT: "Prepared the report",
  VERIFY: "Verified findings against source records",
  CRITIQUE: "Checked the wording against the evidence",
  DONE: "Report ready",
  PARTIAL: "Stopped early with a partial result",
  ERROR: "Stopped with an error",
};
/** The executor's actions (TraceEvent.action), as the plan's step labels. */
const ACTION_LABEL: [string, string][] = [
  ["find_identities", "Find identities"],
  ["fetch_meds", "Gather medicines"],
  ["resolve_free_text", "Resolve free text"],
  ["check_shortages", "Check shortages"],
  ["verify", "Verify"],
];

export interface SummaryCtx {
  trace: TraceEvent[];
  patientName?: string | null;
  sourcesFound?: number | null;
}

function summarize(g: TraceEvent[], ctx: SummaryCtx): string {
  const step = g[g.length - 1].step ?? "";
  if (step === "START") return ctx.patientName ? `Started reconciliation for ${ctx.patientName}` : "Started reconciliation";
  if (step === "PLAN") {
    const acts = new Set(ctx.trace.map((e) => e.action));
    const labels = ACTION_LABEL.filter(([a]) => acts.has(a)).map(([, l]) => l);
    return labels.length ? labels.join(" · ") : "Planned the reconciliation steps";
  }
  const base = SUMMARY[step] ?? humanize(step || g[0].action);
  if (step === "FIND_IDENTITY" && ctx.sourcesFound) return `${base} · ${ctx.sourcesFound} sources found`;
  const rows = g.filter((e) => e.row_count !== null && e.row_count !== undefined).reduce((n, e) => n + (e.row_count ?? 0), 0);
  if (step === "FETCH_MEDS" && rows) return `${base} · ${rows} records`;
  return base;
}

const raw = (e: TraceEvent) => e.message ?? e.output_summary ?? e.action;

/** Consecutive events of the same step become one line ("Record retrieval ×3"). */
function groupSteps(trace: TraceEvent[]): TraceEvent[][] {
  const out: TraceEvent[][] = [];
  for (const e of trace) {
    const last = out[out.length - 1];
    if (last && stepLabel(last[0]) === stepLabel(e) && e.status !== "blocked" && last[0].status !== "blocked") last.push(e);
    else out.push([e]);
  }
  return out;
}

function StepLine({ g, ctx }: { g: TraceEvent[]; ctx: SummaryCtx }) {
  const [open, setOpen] = useState(false);
  const lastE = g[g.length - 1];
  const warn = g.some((e) => e.status === "blocked" || e.status === "error" || !!e.error);
  const summary = summarize(g, ctx);
  // "Show details" only when there is something more than the summary: a message.
  const more = g.some((e) => !!(e.message ?? e.output_summary));
  const agents = [...new Set(g.map((e) => e.agent_name).filter(Boolean))];
  const tagged = g.filter((e) => e.engine || routedModel(e));
  // One tag per distinct engine/model in the group.
  const seen = new Set<string>();
  const tags = tagged.filter((e) => {
    const k = `${e.engine ?? ""}|${routedModel(e) ?? ""}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return (
    <div className="log-item">
      <span className={`tl-dot ${warn ? "warn" : ""}`} aria-hidden />
      <div className="log-body">
        <div className="log-line">
          <span className="log-step">
            {stepLabel(lastE)}
            {g.length > 1 && <span className="log-count"> ×{g.length}</span>}
            {g.some((e) => e.status === "blocked") && <span className="log-flag"> · Withheld</span>}
            {g.some((e) => e.retry_count > 0) && <span className="log-flag"> · Retried</span>}
          </span>
          <span className="log-sum">{summary}</span>
          <span className="log-tags">
            {agents.map((a) => (
              <AgentTag key={a} name={a} small />
            ))}
            {tags.map((e, i) => (
              <StepTags key={i} e={e} />
            ))}
            <time dateTime={lastE.timestamp} title={new Date(lastE.timestamp).toLocaleString()}>
              {fmtTime(lastE.timestamp)}
            </time>
          </span>
        </div>
        {more && (
          <button type="button" className="log-more" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide details" : "Show details"}
          </button>
        )}
        {open && (
          <ul className="log-details">
            {g.map((e, i) => (
              <li key={i}>
                <span className="log-dt">
                  {fmtTime(e.timestamp)} · <AgentTag name={e.agent_name} small />
                </span>{" "}
                {cleanText(raw(e))}
              </li>
            ))}
          </ul>
        )}
        {g.map((e, i) => e.error && <div key={i} className="log-err">{e.error}</div>)}
      </div>
    </div>
  );
}

const ENGINE_NAME: Record<string, string> = { hmem: "H-MEM", world_model: "World Model" };
const filterLabel = (f: LogFilter) =>
  f.kind === "agent" ? `${f.agent} steps` : f.kind === "zetaris" ? "Zetaris queries" : f.kind === "engine" ? `${ENGINE_NAME[f.engine] ?? f.engine} steps` : "model calls";

/**
 * The processing log, condensed: one line per step (repeats collapsed), a short
 * summary, and small agent / engine / model tags; each step's full messages sit
 * behind "Show details". `compact` is the live view while a run is in progress.
 */
export function Timeline({
  run,
  polling,
  warning,
  compact = false,
  patientName,
  filter = null,
  onClearFilter,
}: {
  run: RunResponse | null;
  polling: boolean;
  warning: string | null;
  compact?: boolean;
  patientName?: string | null;
  /** Set by clicking a node in the Powered-by pipeline. */
  filter?: LogFilter | null;
  onClearFilter?: () => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const n = run?.trace.length ?? 0;
  const shown = run ? (filter ? run.trace.filter((e) => matches(e, filter)) : run.trace) : [];
  const ctx: SummaryCtx = {
    trace: run?.trace ?? [],
    patientName,
    sourcesFound: run && Object.keys(run.coverage).length ? Object.values(run.coverage).filter((c) => c?.state === "found").length : null,
  };
  useEffect(() => {
    if (polling) end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [n, polling]);

  return (
    <div className="timeline">
      {!compact && (
        <div className="sec-head">
          <h2 className="sec-title">Processing log</h2>
          {polling ? <span className="spinner" aria-label="running" /> : run && <span className="sec-meta">{run.execution_time_seconds < 0.05 ? "< 0.1" : run.execution_time_seconds.toFixed(1)} s</span>}
        </div>
      )}
      {!run && !polling && <p className="sec-empty">Each step is logged here as it happens.</p>}
      {run && (
        <div className={`log ${compact ? "log-compact" : ""}`}>
          {filter && (
            <div className="log-filter" role="status">
              Showing {filterLabel(filter)} · {plural(shown.length, "step")}
              <button type="button" className="lnk" onClick={onClearFilter}>
                Show all
              </button>
            </div>
          )}
          {groupSteps(shown).map((g, i) => (
            <StepLine key={`${g[0].timestamp}-${i}`} g={g} ctx={ctx} />
          ))}
          {filter && !shown.length && <p className="sec-empty">No steps in this run.</p>}
        </div>
      )}
      {polling && (
        <div className="log-item" ref={end}>
          <span className="tl-dot tl-pending" aria-hidden />
          <div className="log-body">
            <div className="log-text muted">Processing…</div>
            {warning && <div className="log-err">{warning}</div>}
          </div>
        </div>
      )}
      {run && !polling && !compact && (
        <div className="side-foot">
          {plural(run.query_count, "data query", "data queries")} · {footModels(run.model_calls)}
        </div>
      )}
      {run && !compact && (
        <TechDetails
          items={[
            ["Run", run.run_id],
            ["Trace file", run.log_file],
            ["Time in Zetaris", `${(run.zetaris_ms / 1000).toFixed(1)} s`],
            ["Provider state", run.provider_state ?? null],
          ]}
        >
          <table className="mini-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Step</th>
                <th>Agent</th>
                <th>Answered by</th>
                <th>Requested</th>
                <th>Tool</th>
              </tr>
            </thead>
            <tbody>
              {run.trace.map((e, i) => (
                <tr key={i} title={e.message ?? ""}>
                  <td className="nowrap">{fmtTime(e.timestamp)}</td>
                  <td>{e.step ?? e.action}</td>
                  <td>
                    <AgentTag name={e.agent_name} small />
                  </td>
                  <td>{routedModel(e) ?? "—"}</td>
                  <td>{e.route ?? "—"}</td>
                  <td>{e.engine ? `${e.engine}${e.engine_op ? `.${e.engine_op}` : ""}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {run.model_calls.length > 0 && (
            <table className="mini-table">
              <thead>
                <tr>
                  <th>Model call</th>
                  <th>Requested</th>
                  <th>Answered by</th>
                  <th>Tokens in → out</th>
                </tr>
              </thead>
              <tbody>
                {run.model_calls.map((c, i) => (
                  <tr key={c.request_id ?? i}>
                    <td>
                      <AgentTag name={c.role} small />
                    </td>
                    <td>{c.requested_route}</td>
                    <td>
                      {c.routed_model ?? "—"}
                      {c.truncated ? " (truncated)" : ""}
                    </td>
                    <td>
                      {c.tokens.prompt_tokens ?? "?"} → {c.tokens.completion_tokens ?? "?"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {run.trace
            .filter((e) => e.sql)
            .map((e, i) => (
              <pre key={i} className="code">
                {e.sql}
              </pre>
            ))}
        </TechDetails>
      )}
    </div>
  );
}
