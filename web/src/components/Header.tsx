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

interface StatusRow {
  name: string;
  value: string;
  dot?: string;
  title: string;
  cls?: string;
}

/** The same three lines the expanded footer shows. A failed status call has no live values. */
function statusRows(health: HealthResponse | null, error: string | null): StatusRow[] {
  if (error) {
    return [{ name: "Service", value: "Unreachable", dot: "bad", title: error }];
  }
  const z = health?.zetaris ?? "unknown";
  const m = health?.meterless ?? "unknown";
  const model = health?.last_routed_model ?? null;
  return [
    { name: "Data source", value: said(z), dot: DOT[z] ?? "bad", title: `Zetaris data layer: ${z}` },
    { name: "AI runtime", value: said(m), dot: DOT[m] ?? "bad", title: `Meterless Nightshift (GET /v1/models): ${m}` },
    { name: "Model", value: model ?? "Not yet called", dot: model ? "model" : "idle", title: "Model that last answered (meterless.routed_model)", cls: "st-model" },
  ];
}

function Row({ name, value, dot, title, cls = "" }: StatusRow) {
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
  return (
    <div className="side-status">
      {statusRows(health, error).map((row) => (
        <Row key={row.name} {...row} dot={row.name === "Model" ? undefined : row.dot} />
      ))}
    </div>
  );
}

/** The collapsed rail: one dot per footer line, with the same label and value. */
export function StatusDots({ health, error }: { health: HealthResponse | null; error: string | null }) {
  const rows = statusRows(health, error);
  const shown = rows.length === 1 ? ["Data source", "AI runtime", "Model"].map((name) => ({ ...rows[0], name })) : rows;
  return (
    <div className="rail-status">
      {shown.map((row) => {
        const tip = `${row.name}: ${row.value}`;
        return (
          <span key={row.name} className="rail-dot rail-tip" tabIndex={0} role="img" aria-label={tip} data-tip={tip} title={tip}>
            <span className={`st-dot dot-${row.dot ?? "idle"}`} aria-hidden />
          </span>
        );
      })}
    </div>
  );
}
