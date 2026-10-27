import { useId, type CSSProperties, type ReactNode } from "react";
import type { HealthResponse, RunResponse, TraceEvent } from "../types";
import { OFFLINE_MODEL, plural } from "../format";
import { type LogFilter, isQuery, modelAnswered, routedModel, sameFilter } from "../trace";
import { AGENT_COLOR } from "./Agent";

/**
 * The live "Powered by" pipeline: Zetaris → the four agents → Meterless engines →
 * Nightshift → NVIDIA Nemotron. Every light comes from the API: trace events as
 * GET /run/{id} polling brings them in (agent_name, engine, sql/row_count) and the
 * model calls (routed_model). Nothing lights that the API did not report: in
 * SAMPLE_MODE no model answers, so Nightshift and Nemotron stay dimmed.
 * A node is dimmed (outline) until used, filled with a count once used, and
 * pulses while it handles the current step. Click a node to filter the log.
 */
const AGENTS = ["Planner", "Executor", "Evaluator", "Writer"];
const ROLE: Record<string, string> = {
  Zetaris: "Data layer: every fact comes by SQL.",
  Planner: "Chooses the steps.",
  Executor: "Runs queries, links records.",
  Evaluator: "Compares sources, checks findings.",
  Writer: "Writes explanations and the summary.",
  hmem: "Meterless H-MEM: pharmacist-taught trust.",
  world_model: "Meterless World Model: identity memory.",
  Nightshift: "Meterless Nightshift: routes every model call.",
  Nemotron: "NVIDIA Nemotron: answers the agents' model calls.",
};
const ENGINES: [string, string][] = [
  ["hmem", "H-MEM"],
  ["world_model", "World Model"],
];

type State = "idle" | "used" | "now" | "off";

function Node({
  label,
  sub,
  state,
  role,
  color,
  filter,
  active,
  onFilter,
  flashKey,
  small = false,
}: {
  label: string;
  sub: ReactNode;
  state: State;
  role: string;
  color?: string;
  filter?: LogFilter;
  active: boolean;
  onFilter: (f: LogFilter) => void;
  flashKey?: number;
  small?: boolean;
}) {
  const id = useId();
  const words = state === "now" ? "working now" : state === "used" ? "used" : state === "off" ? "not used" : "not used yet";
  return (
    <div className={`pn pn-${state} ${small ? "pn-small" : ""} ${active ? "pn-active" : ""}`} style={color ? ({ "--c": color } as CSSProperties) : undefined}>
      <button
        type="button"
        className="pn-btn"
        aria-pressed={filter ? active : undefined}
        aria-describedby={id}
        aria-label={`${label}: ${words}. ${typeof sub === "string" ? sub : ""}${filter ? " Click to filter the processing log." : ""}`}
        onClick={() => filter && onFilter(filter)}
        aria-disabled={!filter || undefined}
      >
        <span className="pn-dot" aria-hidden />
        <span className="pn-text">
          <span className="pn-label">
            {label}
            {state === "now" && <span className="pn-now"> · now</span>}
          </span>
          <span className={`pn-sub ${flashKey ? "pn-flash" : ""}`} key={flashKey}>
            {sub}
          </span>
        </span>
      </button>
      <span role="tooltip" id={id} className="pn-tip">
        {role}
        {typeof sub === "string" && sub ? ` This run: ${sub}.` : ""}
      </span>
    </div>
  );
}

function Link({ flowing }: { flowing: boolean }) {
  return <span className={`pl ${flowing ? "pl-flow" : ""}`} aria-hidden />;
}

export function Pipeline({
  run,
  health,
  live,
  filter,
  onFilter,
}: {
  run: RunResponse | null;
  health: HealthResponse | null;
  /** The run is still going (polling, or paused for an identity check). */
  live: boolean;
  filter: LogFilter | null;
  onFilter: (f: LogFilter) => void;
}) {
  const trace: TraceEvent[] = run?.trace ?? [];
  const last = live ? trace[trace.length - 1] : undefined;
  const sample = run?.sample_mode ?? health?.sample_mode ?? health?.meterless === "sample_mode";

  const queries = trace.filter(isQuery);
  const rows = queries.reduce((n, e) => n + (e.row_count ?? 0), 0);
  const zState: State = last && isQuery(last) ? "now" : queries.length ? "used" : "idle";

  const calls = run ? run.model_calls.filter((c) => c.routed_model && c.routed_model !== OFFLINE_MODEL) : [];
  const models = [...new Set(calls.map((c) => c.routed_model as string))];
  const modelNow = !!last && modelAnswered(last);
  const mState: State = modelNow ? "now" : calls.length ? "used" : sample ? "off" : "idle";

  const stateOf = (count: number, isNow: boolean): State => (isNow ? "now" : count ? "used" : "idle");
  const agentCount = (a: string) => trace.filter((e) => e.agent_name === a).length;
  const engineCount = (k: string) => trace.filter((e) => e.engine === k).length;

  const head = !run ? "Ready" : live ? "Running…" : "This run";
  const nowAt = !last ? "" : isQuery(last) ? "zetaris" : last.engine ? "engine" : modelAnswered(last) ? "model" : "agent";

  return (
    <section className="pipe2 panel" aria-label="Powered by">
      <div className="pipe2-head">
        <h2 className="pipe2-title">Powered by</h2>
        <span className="pipe2-state">{head}</span>
        {filter && (
          <button type="button" className="lnk pipe2-clear" onClick={() => onFilter(filter)}>
            Clear log filter
          </button>
        )}
      </div>
      <div className="pipe2-row">
        <Node
          label="Zetaris"
          sub={queries.length ? `${plural(queries.length, "SQL query", "SQL queries")} · ${plural(rows, "row")}` : run ? "no queries yet" : "data layer"}
          state={zState}
          role={ROLE.Zetaris}
          filter={{ kind: "zetaris" }}
          active={sameFilter(filter, { kind: "zetaris" })}
          onFilter={onFilter}
          flashKey={queries.length}
        />
        <Link flowing={live && (nowAt === "zetaris" || nowAt === "agent")} />
        <div className="pg pg-agents" role="group" aria-label="Agents">
          {AGENTS.map((a) => {
            const n = agentCount(a);
            const f: LogFilter = { kind: "agent", agent: a };
            return (
              <Node
                key={a}
                label={a}
                sub={n ? plural(n, "step") : "not used yet"}
                state={stateOf(n, last?.agent_name === a)}
                role={ROLE[a]}
                color={AGENT_COLOR[a]}
                filter={f}
                active={sameFilter(filter, f)}
                onFilter={onFilter}
              />
            );
          })}
        </div>
      </div>
      {/* Second row: engines and models, so the pipeline wraps at a meaningful point. */}
      <div className="pipe2-row pipe2-row2">
        <span className="pl-turn" aria-hidden />
        <div className="pg pg-engines" role="group" aria-label="Meterless engines">
          <span className="pg-label">Meterless engines</span>
          {ENGINES.map(([k, name]) => {
            const n = engineCount(k);
            const f: LogFilter = { kind: "engine", engine: k };
            return (
              <Node
                key={k}
                label={name}
                sub={n ? plural(n, "step") : "not used yet"}
                state={stateOf(n, last?.engine === k)}
                role={ROLE[k]}
                filter={f}
                active={sameFilter(filter, f)}
                onFilter={onFilter}
                small
              />
            );
          })}
        </div>
        <Link flowing={live && nowAt === "model"} />
        <Node
          label="Meterless Nightshift"
          sub={mState === "off" ? "not used · sample mode" : calls.length ? plural(calls.length, "model call") : health?.meterless === "online" ? "online" : "no calls yet"}
          state={mState}
          role={ROLE.Nightshift}
          filter={calls.length ? { kind: "model" } : undefined}
          active={sameFilter(filter, { kind: "model" })}
          onFilter={onFilter}
        />
        <Link flowing={live && nowAt === "model"} />
        <Node
          label="NVIDIA Nemotron"
          sub={
            mState === "off"
              ? "not used · sample mode"
              : modelNow && last
                ? (routedModel(last) ?? "").replace(/^nvidia\//, "")
                : models.length
                  ? models.map((m) => m.replace(/^nvidia\//, "")).join(", ")
                  : "not called yet"
          }
          state={mState}
          role={ROLE.Nemotron}
          filter={calls.length ? { kind: "model" } : undefined}
          active={sameFilter(filter, { kind: "model" })}
          onFilter={onFilter}
        />
      </div>
    </section>
  );
}
