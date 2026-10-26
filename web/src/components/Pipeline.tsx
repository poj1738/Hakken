import type { HealthResponse, RunResponse } from "../types";
import type { ReactNode } from "react";
import { OFFLINE_MODEL, engineLabel, humanize, plural } from "../format";
import { AgentTag } from "./Agent";

/**
 * "Powered by": Zetaris → agents → Meterless Nightshift → NVIDIA Nemotron, read
 * from this run (query_count, trace, model_calls) or, before a run, from GET
 * /status. A model is named only if the API says it answered; offline-heuristic
 * steps are never counted as Nemotron calls.
 */
const STATUS: Record<string, string> = { sample_mode: "sample mode", connected: "connected", online: "online", offline: "offline", unauthorized: "unauthorised" };
const said = (v: string | undefined) => (v ? STATUS[v] ?? humanize(v).toLowerCase() : "unknown");

function Stage({ name, value, title, tone = "" }: { name: string; value: ReactNode; title?: string; tone?: string }) {
  return (
    <li className={`pipe-stage ${tone}`} title={title}>
      <span className="pipe-name">{name}</span>
      <span className="pipe-value">{value}</span>
    </li>
  );
}

export function Pipeline({ run, health }: { run: RunResponse | null; health: HealthResponse | null }) {
  const live = run ? run.model_calls.filter((c) => c.routed_model && c.routed_model !== OFFLINE_MODEL) : [];
  const models = [...new Set(live.map((c) => c.routed_model as string))];
  const agents = run ? [...new Set(run.trace.map((e) => e.agent_name).filter((a) => a && a !== "orchestrator"))] : [];
  const engines = run ? [...new Set(run.trace.map((e) => e.engine).filter((e): e is string => !!e))] : [];
  const sample = run?.sample_mode ?? health?.sample_mode ?? false;

  let nemotron: string;
  let nemoTitle: string;
  if (run) {
    nemotron = models.length ? models.map((m) => m.replace(/^nvidia\//, "")).join(", ") : sample ? "not called · sample mode" : "not called";
    nemoTitle = models.length ? `${plural(live.length, "call")} answered by ${models.join(", ")}` : "No model answered in this run";
  } else {
    nemotron = health?.last_routed_model?.replace(/^nvidia\//, "") ?? (sample ? "not called · sample mode" : "not yet called");
    nemoTitle = "The model that most recently answered (GET /status)";
  }

  return (
    <section className="pipe" aria-label="Powered by">
      <span className="pipe-lead">Powered by</span>
      <ol className="pipe-row">
        <Stage
          name="Zetaris"
          value={run ? plural(run.query_count, "SQL query", "SQL queries") : said(health?.zetaris)}
          title="Every fact comes from SQL sent to Zetaris"
        />
        <Stage
          name={agents.length ? plural(agents.length, "agent") : "Agents"}
          value={
            agents.length ? (
              <span className="pipe-agents">
                {agents.map((a) => (
                  <AgentTag key={a} name={a} small />
                ))}
              </span>
            ) : (
              "ready"
            )
          }
          title={engines.length ? `Meterless engines used: ${engines.map(engineLabel).join(", ")}` : undefined}
        />
        {engines.length > 0 && <Stage name="Meterless engines" value={engines.map(engineLabel).join(" · ")} tone="pipe-engine" />}
        <Stage name="Meterless Nightshift" value={said(health?.meterless)} title="Every model call goes through Nightshift" />
        <Stage name="NVIDIA Nemotron" value={nemotron} title={nemoTitle} tone={models.length ? "pipe-live" : "pipe-off"} />
      </ol>
    </section>
  );
}
