import { useEffect, useRef, useState } from "react";
import type { RunResponse, TraceEvent } from "../types";
import { OFFLINE_MODEL, cleanText, engineLabel, fmtTime, humanize, plural } from "../format";
import { TechDetails } from "./TechDetails";
import { AgentTag } from "./Agent";

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

// The model that answered: the Meterless receipt's routed_model when the event
// carries one, else `model`, which the API fills with the model that answered.
function routedModel(e: TraceEvent): string | null {
  const m = e.meterless?.["routed_model"];
  return typeof m === "string" ? m : e.model ?? null;
}

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

/** A one-line summary of a step's message: its first sentence, cut at a word to about 80 characters. */
function short(raw: string): string {
  const t = cleanText(raw);
  const first = t.match(/^.+?[.!?](\s|$)/)?.[0].trim() ?? t;
  if (first.length <= 80) return first;
  const cut = first.slice(0, 80);
  return `${cut.slice(0, cut.lastIndexOf(" ") > 50 ? cut.lastIndexOf(" ") : 80).replace(/[,;:]$/, "")}…`;
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

function StepLine({ g }: { g: TraceEvent[] }) {
  const [open, setOpen] = useState(false);
  const lastE = g[g.length - 1];
  const warn = g.some((e) => e.status === "blocked" || e.status === "error" || !!e.error);
  const summary = short(raw(lastE));
  const more = g.length > 1 || cleanText(raw(lastE)) !== summary;
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
          <span className="log-sum" title={cleanText(raw(lastE))}>
            {summary}
          </span>
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

/**
 * The processing log, condensed: one line per step (repeats collapsed), a short
 * summary, and small agent / engine / model tags; each step's full messages sit
 * behind "Show details". `compact` is the live view while a run is in progress.
 */
export function Timeline({ run, polling, warning, compact = false }: { run: RunResponse | null; polling: boolean; warning: string | null; compact?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const n = run?.trace.length ?? 0;
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
          {groupSteps(run.trace).map((g, i) => (
            <StepLine key={`${g[0].timestamp}-${i}`} g={g} />
          ))}
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
