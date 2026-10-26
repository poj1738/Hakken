import { useEffect, useRef } from "react";
import type { ModelCall, RunResponse, TraceEvent } from "../types";
import { cleanText, fmtTime, humanize, plural } from "../format";
import { TechDetails } from "./TechDetails";

// The model that answered: the Meterless receipt's routed_model when the event
// carries one, else `model`, which the API fills with the model that answered.
function routedModel(e: TraceEvent): string | null {
  const m = e.meterless?.["routed_model"];
  return typeof m === "string" ? m : e.model ?? null;
}

function Event({ e }: { e: TraceEvent }) {
  const blocked = e.status === "blocked";
  const failed = e.status === "error" || !!e.error;
  const model = routedModel(e);
  const raw = e.message ?? e.output_summary ?? e.action;
  return (
    <li className={`event ${blocked ? "blocked" : ""} ${failed ? "failed" : ""}`}>
      <div className="event-head">
        <span className="step">{humanize(e.step ?? e.action)}</span>
        <span className="agent">{e.agent_name}</span>
        {blocked && <span className="badge bad">Blocked</span>}
        {failed && <span className="badge bad">Error</span>}
        {e.retry_count > 0 && <span className="badge warn">Retry {e.retry_count}</span>}
        <time dateTime={e.timestamp} title={new Date(e.timestamp).toLocaleString()}>
          {fmtTime(e.timestamp)}
        </time>
      </div>
      <p className="event-msg">{cleanText(raw)}</p>
      {e.error && <p className="event-err">{e.error}</p>}
      {model && <p className="event-meta">Answered by {model}</p>}
      <TechDetails
        items={[
          ["Original message", raw !== cleanText(raw) ? raw : null],
          ["Action", e.action],
          ["Tool", e.engine ? `${e.engine}${e.engine_op ? `.${e.engine_op}` : ""}` : null],
          ["Model requested", e.route],
          ["Rows", e.row_count ?? null],
          ["Time taken", e.latency_ms != null ? `${(e.latency_ms / 1000).toFixed(1)} s` : null],
          ["Memory records", e.memory_ids.length ? e.memory_ids.join(", ") : null],
        ]}
      >
        {e.sql && <pre className="code">{e.sql}</pre>}
      </TechDetails>
    </li>
  );
}

function ModelCalls({ calls }: { calls: ModelCall[] }) {
  if (!calls.length) return null;
  return (
    <table className="mini-table">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Requested</th>
          <th>Answered by</th>
          <th>Tokens in → out</th>
        </tr>
      </thead>
      <tbody>
        {calls.map((c, i) => (
          <tr key={c.request_id ?? i}>
            <td>{c.role}</td>
            <td>{c.requested_route}</td>
            <td>
              {c.routed_model ?? "—"}
              {c.truncated && <span className="badge warn">Truncated</span>}
            </td>
            <td>
              {c.tokens.prompt_tokens ?? "?"} → {c.tokens.completion_tokens ?? "?"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Timeline({ run, polling, warning }: { run: RunResponse | null; polling: boolean; warning: string | null }) {
  const end = useRef<HTMLLIElement>(null);
  const n = run?.trace.length ?? 0;
  useEffect(() => {
    if (polling) end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [n, polling]);

  return (
    <section className="card timeline">
      <h2>
        Agent Activity {polling && <span className="spinner" aria-label="running" />}
      </h2>
      {!run && <p className="muted">Choose a patient and run a reconciliation. Each step appears here as it happens.</p>}
      {run && (
        <>
          <ol className="events">
            {run.trace.map((e, i) => (
              <Event key={`${e.timestamp}-${i}`} e={e} />
            ))}
            {polling && (
              <li className="event pending" ref={end}>
                <p className="muted">Working…</p>
                {warning && <p className="event-err">{warning}</p>}
              </li>
            )}
          </ol>
          {!polling && (
            <div className="run-footer">
              <p className="run-stats">
                {plural(run.query_count, "data query", "data queries")} · {run.execution_time_seconds.toFixed(1)} s
                {run.model_calls.length > 0 && <> · {plural(run.model_calls.length, "model call")}</>}
              </p>
              <TechDetails
                label="Run details"
                items={[
                  ["Run", run.run_id],
                  ["Trace file", run.log_file],
                  ["Time in Zetaris", `${(run.zetaris_ms / 1000).toFixed(1)} s`],
                  ["Provider state", run.provider_state ?? null],
                ]}
              >
                <ModelCalls calls={run.model_calls} />
              </TechDetails>
            </div>
          )}
        </>
      )}
    </section>
  );
}
