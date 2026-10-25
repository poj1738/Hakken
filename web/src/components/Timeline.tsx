import { useEffect, useRef } from "react";
import type { ModelCall, RunResponse, TraceEvent } from "../types";
import { fmtTime } from "../format";

function routedModel(e: TraceEvent): string | null {
  const m = e.meterless?.["routed_model"];
  return typeof m === "string" ? m : e.model ?? null;
}

function Event({ e }: { e: TraceEvent }) {
  const blocked = e.status === "blocked";
  const failed = e.status === "error" || !!e.error;
  const model = routedModel(e);
  return (
    <li className={`event ${blocked ? "blocked" : ""} ${failed ? "failed" : ""}`}>
      <div className="event-head">
        <span className="step">{e.step ?? e.action}</span>
        <span className="agent">{e.agent_name}</span>
        <time>{fmtTime(e.timestamp)}</time>
      </div>
      <p className="event-msg">
        {blocked && <strong className="blocked-tag">Blocked · </strong>}
        {e.message ?? e.output_summary ?? e.action}
      </p>
      {e.error && <p className="event-err">{e.error}</p>}
      {(model || e.engine || e.row_count != null || e.latency_ms != null) && (
        <div className="event-meta">
          {model && (
            <span title={e.route ? `requested ${e.route}` : undefined}>
              🧠 <code>{model}</code>
              {e.route && <span className="muted"> via {e.route}</span>}
            </span>
          )}
          {e.engine && (
            <span>
              ⚙ {e.engine}
              {e.engine_op ? `.${e.engine_op}` : ""}
            </span>
          )}
          {e.row_count != null && <span>{e.row_count} rows</span>}
          {e.latency_ms != null && <span>{(e.latency_ms / 1000).toFixed(1)} s</span>}
        </div>
      )}
      {e.sql && (
        <details className="sql">
          <summary>SQL sent to Zetaris</summary>
          <pre>{e.sql}</pre>
        </details>
      )}
    </li>
  );
}

function ModelCalls({ calls }: { calls: ModelCall[] }) {
  if (!calls.length) return null;
  return (
    <details className="model-calls">
      <summary>{calls.length} model calls through Nightshift</summary>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Requested</th>
            <th>Answered by</th>
            <th>Tokens</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((c, i) => (
            <tr key={c.request_id ?? i}>
              <td>{c.role}</td>
              <td>
                <code>{c.requested_route}</code>
              </td>
              <td>
                <code>{c.routed_model ?? "—"}</code>
                {c.truncated && <span className="badge warn">truncated</span>}
              </td>
              <td>
                {c.tokens.prompt_tokens ?? "?"} → {c.tokens.completion_tokens ?? "?"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export function Timeline({ run, polling }: { run: RunResponse | null; polling: boolean }) {
  const end = useRef<HTMLLIElement>(null);
  const n = run?.trace.length ?? 0;
  useEffect(() => {
    if (polling) end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [n, polling]);

  return (
    <section className="card timeline">
      <h2>
        Agent timeline {polling && <span className="spinner" aria-label="running" />}
      </h2>
      {!run && <p className="muted">Pick a patient and run. Each agent step appears here as it happens.</p>}
      {run && (
        <>
          <ol className="events">
            {run.trace.map((e, i) => (
              <Event key={`${e.timestamp}-${i}`} e={e} />
            ))}
            {polling && (
              <li className="event pending" ref={end}>
                <p className="muted">Working…</p>
              </li>
            )}
          </ol>
          {!polling && (
            <p className="run-stats muted">
              {run.query_count} Zetaris queries · {(run.zetaris_ms / 1000).toFixed(1)} s in Zetaris ·{" "}
              {run.execution_time_seconds.toFixed(1)} s total · trace <code>{run.log_file}</code>
            </p>
          )}
          <ModelCalls calls={run.model_calls} />
        </>
      )}
    </section>
  );
}
