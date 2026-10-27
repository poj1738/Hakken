import type { HealthResponse } from "../types";
import { humanize } from "../format";

// GET /status values as words, with a dot colour. In SAMPLE_MODE the API replays
// recorded Zetaris responses and makes no model calls and says "sample_mode":
// neither up nor down.
const DOT: Record<string, string> = { connected: "ok", online: "ok", unauthorized: "warn", offline: "bad", sample_mode: "info" };
const LABEL: Record<string, string> = { sample_mode: "Sample mode", connected: "Connected", online: "Online" };
const said = (v: string) => LABEL[v] ?? humanize(v);

/** The sidebar's brand block. */
export function Brand() {
  return (
    <div className="brand">
      <div className="brand-logo" aria-hidden>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />
        </svg>
      </div>
      <div className="brand-name">MedTrace</div>
    </div>
  );
}

function Row({ name, value, dot, title, cls = "" }: { name: string; value: string; dot?: string; title: string; cls?: string }) {
  return (
    <div className={`st-row ${cls}`} title={title}>
      <span>{name}</span>
      <span className="st-value">
        {dot && <span className={`st-dot dot-${dot}`} aria-hidden />}
        {value}
      </span>
    </div>
  );
}

/** GET /status as returned, at the foot of the sidebar: "Model" is the server's answer, not ours. */
export function SideStatus({ health, error }: { health: HealthResponse | null; error: string | null }) {
  if (error) {
    return (
      <div className="side-status">
        <Row name="Service" value="Unreachable" dot="bad" title={error} />
      </div>
    );
  }
  const z = health?.zetaris ?? "unknown";
  const m = health?.meterless ?? "unknown";
  const model = health?.last_routed_model ?? null;
  return (
    <div className="side-status">
      <Row name="Data source" value={said(z)} dot={DOT[z] ?? "bad"} title={`Zetaris data layer: ${z}`} />
      <Row name="AI runtime" value={said(m)} dot={DOT[m] ?? "bad"} title={`Meterless Nightshift (GET /v1/models): ${m}`} />
      <Row name="Model" value={model ?? "Not yet called"} title="The model that actually answered most recently (meterless.routed_model)" cls="st-model" />
    </div>
  );
}
