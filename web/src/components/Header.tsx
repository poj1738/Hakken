import type { HealthResponse } from "../types";
import { API_MODE } from "../api";
import { humanize } from "../format";

interface Props {
  health: HealthResponse | null;
  error: string | null;
}

// GET /status values, as words and a tone. In SAMPLE_MODE the API replays
// recorded Zetaris responses and makes no model calls, and says "sample_mode":
// neither up nor down.
const TONE: Record<string, string> = {
  connected: "ok",
  online: "ok",
  unauthorized: "warn",
  offline: "bad",
  sample_mode: "info",
};
const LABEL: Record<string, string> = { sample_mode: "Sample mode", connected: "Connected", online: "Online" };
const said = (v: string) => LABEL[v] ?? humanize(v);

function Status({ name, value, title }: { name: string; value: string; title: string }) {
  return (
    <span className={`status-item tone-${TONE[value] ?? "bad"}`} title={title}>
      <i className="dot" aria-hidden />
      <span className="status-name">{name}</span>
      <span className="status-value">{said(value)}</span>
    </span>
  );
}

export function Header({ health, error }: Props) {
  const zetaris = health?.zetaris ?? "unknown";
  const nightshift = health?.meterless ?? "unknown";
  const model = health?.last_routed_model ?? null;
  return (
    <header className="header">
      <div className="brand">
        <span className="logo" aria-hidden>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12h4l2-5 4 10 2-5h6" />
          </svg>
        </span>
        <div>
          <h1>MedTrace</h1>
          <p className="tagline">Medication reconciliation</p>
        </div>
      </div>
      <div className="header-right">
        {error ? (
          <span className="status-group">
            <span className="status-item tone-bad" title={error}>
              <i className="dot" aria-hidden />
              <span className="status-value">Service unreachable</span>
            </span>
          </span>
        ) : (
          <span className="status-group" aria-live="polite">
            <Status name="Data" value={zetaris} title={`Zetaris data layer: ${zetaris}`} />
            <Status name="AI" value={nightshift} title={`Meterless Nightshift (GET /v1/models): ${nightshift}`} />
            <span className="status-item" title="The model that actually answered most recently (meterless.routed_model)">
              <span className="status-name">Model</span>
              <span className="status-value">{model ?? "None yet"}</span>
            </span>
          </span>
        )}
        {API_MODE === "mock" && (
          <span className="badge-mock" title="Replaying tests/fixtures/api/*.json: hand-written examples, not real runs">
            Example data
          </span>
        )}
        <span className="badge-disclaimer" title="A pharmacist must confirm every item.">
          Synthetic data · Not medical advice
        </span>
      </div>
    </header>
  );
}
