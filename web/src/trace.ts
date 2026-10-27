// Reading the API's trace (RunResponse.trace): which events were Zetaris
// queries, which engine or model handled a step, and the filter the "Powered by"
// pipeline sets on the processing log. Structured fields only; never the message text.
import type { TraceEvent } from "./types";
import { OFFLINE_MODEL } from "./format";

/** The model that answered: the Meterless receipt's routed_model, else `model`. */
export function routedModel(e: TraceEvent): string | null {
  const m = e.meterless?.["routed_model"];
  return typeof m === "string" ? m : e.model ?? null;
}

/** A model really answered (not the offline fallback). */
export const modelAnswered = (e: TraceEvent) => {
  const m = routedModel(e);
  return !!m && m !== OFFLINE_MODEL;
};

/** A Zetaris query event: it carries SQL or a row count. */
export const isQuery = (e: TraceEvent) => !!e.sql || (e.row_count !== null && e.row_count !== undefined);

/** What a click on a pipeline node filters the processing log to. */
export type LogFilter = { kind: "agent"; agent: string } | { kind: "zetaris" } | { kind: "engine"; engine: string } | { kind: "model" };

export function matches(e: TraceEvent, f: LogFilter): boolean {
  if (f.kind === "agent") return e.agent_name === f.agent;
  if (f.kind === "zetaris") return isQuery(e);
  if (f.kind === "engine") return e.engine === f.engine;
  return modelAnswered(e);
}

export const sameFilter = (a: LogFilter | null, b: LogFilter) => !!a && JSON.stringify(a) === JSON.stringify(b);
