import type { HealthResponse } from "../types";
import { API_MODE } from "../api";

interface Props {
  health: HealthResponse | null;
  error: string | null;
}

const NIGHTSHIFT_TONE: Record<string, string> = { online: "ok", unauthorized: "warn", offline: "bad", sample_mode: "info" };
// In SAMPLE_MODE the API replays recorded Zetaris responses and makes no model
// calls, and says so as "sample_mode": neither up nor down.
const ZETARIS_TONE: Record<string, string> = { connected: "ok", sample_mode: "info" };
const said = (v: string) => (v === "sample_mode" ? "sample mode" : v);

export function Header({ health, error }: Props) {
  const zetaris = health?.zetaris ?? "unknown";
  const nightshift = health?.meterless ?? "unknown";
  const model = health?.last_routed_model ?? null;
  return (
    <header className="header">
      <div className="brand">
        <span className="logo" aria-hidden>
          ⚕
        </span>
        <div>
          <h1>MedTrace</h1>
          <p className="tagline">Medication reconciliation across four siloed systems</p>
        </div>
      </div>
      <div className="pills" aria-live="polite">
        <span className="pill tone-disclaimer" title="A pharmacist must confirm every item.">
          Synthetic data · Not medical advice
        </span>
        {API_MODE === "mock" && (
          <span className="pill tone-mock" title="Replaying tests/fixtures/api/*.json — hand-written examples, not real runs">
            Mock data
          </span>
        )}
        {health?.sample_mode && (
          <span className="pill tone-info" title="SAMPLE_MODE: recorded Zetaris responses, no network">
            SAMPLE_MODE
          </span>
        )}
        {error ? (
          <span className="pill tone-bad" title={error}>
            API unreachable
          </span>
        ) : (
          <>
            <span className={`pill tone-${ZETARIS_TONE[zetaris] ?? "bad"}`} title="Zetaris data layer">
              <i className="dot" /> Zetaris: {said(zetaris)}
            </span>
            <span className={`pill tone-${NIGHTSHIFT_TONE[nightshift] ?? "bad"}`} title="Meterless Nightshift (GET /v1/models)">
              <i className="dot" /> Nightshift: {said(nightshift)}
            </span>
            <span className="pill tone-model" title="The model that actually answered (meterless.routed_model)">
              Model: <code>{model ?? "none yet"}</code>
            </span>
          </>
        )}
      </div>
    </header>
  );
}
