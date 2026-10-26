import type { HealthResponse } from "../types";
import { API_MODE } from "../api";
import { humanize } from "../format";

interface Props {
  health: HealthResponse | null;
  error: string | null;
}

// GET /status values as words, with a dot colour. In SAMPLE_MODE the API replays
// recorded Zetaris responses and makes no model calls and says "sample_mode":
// neither up nor down.
const DOT: Record<string, string> = { connected: "ok", online: "ok", unauthorized: "warn", offline: "bad", sample_mode: "info" };
const LABEL: Record<string, string> = { sample_mode: "Sample mode", connected: "Connected", online: "Online" };
const said = (v: string) => LABEL[v] ?? humanize(v);

function Status({ name, value, title }: { name: string; value: string; title: string }) {
  return (
    <div className="hd-status" title={title}>
      <span className={`hd-dot dot-${DOT[value] ?? "bad"}`} aria-hidden />
      <span className="hd-name">{name}</span>
      <span className="hd-value">{said(value)}</span>
    </div>
  );
}

export function Header({ health, error }: Props) {
  const model = health?.last_routed_model ?? null;
  return (
    <header className="hd">
      <div className="hd-inner">
        <div className="hd-brand">
          <div className="hd-logo" aria-hidden>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12h4l3-7 4 14 3-7h4" />
            </svg>
          </div>
          <div>
            <div className="hd-title">MedTrace</div>
            <div className="hd-sub">Medication Reconciliation</div>
          </div>
        </div>
        <div className="hd-right">
          {error ? (
            <div className="hd-status" title={error}>
              <span className="hd-dot dot-bad" aria-hidden />
              <span className="hd-value">Service unreachable</span>
            </div>
          ) : (
            <>
              <Status name="Data source" value={health?.zetaris ?? "unknown"} title={`Zetaris data layer: ${health?.zetaris ?? "unknown"}`} />
              <Status name="AI runtime" value={health?.meterless ?? "unknown"} title={`Meterless Nightshift (GET /v1/models): ${health?.meterless ?? "unknown"}`} />
              <div className="hd-status" title="The model that actually answered most recently (meterless.routed_model)">
                <span className="hd-name">Model</span>
                <span className="hd-value">{model ?? "Not yet called"}</span>
              </div>
            </>
          )}
          {API_MODE === "mock" && (
            <span className="hd-badge hd-badge-mock" title="Replaying tests/fixtures/api/*.json: hand-written examples, not real runs">
              Example data
            </span>
          )}
          <span className="hd-badge" title="A pharmacist must confirm every item.">
            Synthetic data · Not for clinical use
          </span>
        </div>
      </div>
    </header>
  );
}
