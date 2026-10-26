import { useEffect, useRef } from "react";
import type { RunResponse, TraceEvent } from "../types";
import { OFFLINE_MODEL, cleanText, engineLabel, fmtTime, humanize, plural } from "../format";
import { TechDetails } from "./TechDetails";

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

/**
 * The processing log. `compact` is the live view while a run is in progress:
 * steps only, newest last. The full section adds each step's message and the
 * Technical details (per-step routed model, model calls, SQL).
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
          {run.trace.map((e, i) => {
            const warn = e.status === "blocked" || e.status === "error" || !!e.error;
            const raw = e.message ?? e.output_summary ?? e.action;
            return (
              <div key={`${e.timestamp}-${i}`} className="log-item">
                <span className={`tl-dot ${warn ? "warn" : ""}`} aria-hidden />
                <div className="log-body">
                  <div className="log-head">
                    <span className="log-step">
                      {stepLabel(e)}
                      {e.status === "blocked" && <span className="log-flag"> · Withheld</span>}
                      {e.retry_count > 0 && <span className="log-flag"> · Retried {e.retry_count}×</span>}
                    </span>
                    <span className="log-tags">
                      <StepTags e={e} />
                      <time dateTime={e.timestamp} title={new Date(e.timestamp).toLocaleString()}>
                        {fmtTime(e.timestamp)}
                      </time>
                    </span>
                  </div>
                  {!compact && (
                    <div className="log-text" title={raw}>
                      {cleanText(raw)}
                    </div>
                  )}
                  {e.error && <div className="log-err">{e.error}</div>}
                </div>
              </div>
            );
          })}
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
                  <td>{e.agent_name}</td>
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
                    <td>{c.role}</td>
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
