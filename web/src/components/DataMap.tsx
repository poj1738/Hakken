// The Data map. Every count is a cell from GET /data-map/query/{id}.
// Mock mode does not invent a diagram.

import { useEffect, useRef } from "react";
import { API_MODE } from "../api";
import type { DataMapQueryResult, DataMapQuerySpec } from "../types";
import { DataMapDiagram, rowsShown, soleCell, useDataMapRun, type LogEntry } from "./DataMapDiagram";

const SILOS = ["emr", "gp", "pharmacy", "patient"] as const;
const PATIENT_NOTE = "Patients describe medicines in their own words, so no code or risk class is attached.";

export function DataMap({ onPresent }: { onPresent: () => void }) {
  if (API_MODE !== "live") {
    return (
      <div className="dm-page">
        <header className="dm-head">
          <h1 className="dm-title">Data map</h1>
        </header>
        <section className="panel panel-pad">
          <p>The Data map needs the API (live or SAMPLE_MODE).</p>
        </section>
      </div>
    );
  }
  return <DataMapLive onPresent={onPresent} />;
}

function DataMapLive({ onPresent }: { onPresent: () => void }) {
  const { catalogue, byId, entries, fatal, rerun } = useDataMapRun(true);
  const logRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const find = (node: string) => {
    const query = catalogue?.find((q) => q.node === node);
    return query ? byId[query.id] : undefined;
  };

  return (
    <div className="dm-page">
      <header className="dm-head">
        <h1 className="dm-title">Data map</h1>
        <div className="dm-actions">
          <button type="button" className="btn btn-line" onClick={rerun}>
            Run again
          </button>
          <button type="button" className="btn btn-primary" onClick={onPresent}>
            Presenter view
          </button>
        </div>
      </header>

      {fatal && (
        <div className="alert alert-note" role="alert">
          {fatal}
        </div>
      )}

      <section className="panel dm-hero" aria-labelledby="dm-diagram-title">
        <h2 className="h2" id="dm-diagram-title">
          Sources
        </h2>
        <div className="dm-diagram">
          {catalogue ? (
            <DataMapDiagram catalogue={catalogue} byId={byId} />
          ) : (
            <p className="dm-wait">querying Zetaris…</p>
          )}
        </div>
      </section>

      <div className="dm-split">
        <section className="panel panel-pad" aria-labelledby="dm-risk-title">
          <h2 className="h2" id="dm-risk-title">
            High-risk medicine lines by source
          </h2>
          <RiskChart entry={find("high_risk")} catalogue={catalogue} />
        </section>
        <section className="panel panel-pad" aria-labelledby="dm-dq-title">
          <h2 className="h2" id="dm-dq-title">
            Data quality
          </h2>
          <QualityCard dq={find("dq")} rows={find("usl")} />
        </section>
      </div>

      <section className="panel panel-pad" aria-labelledby="dm-log-title">
        <h2 className="h2" id="dm-log-title">
          Query log
        </h2>
        <ol className="dm-log" ref={logRef} aria-live="polite">
          <li className="dm-log-row dm-log-head" aria-hidden>
            <span>Time</span>
            <span>Query</span>
            <span>Rows</span>
            <span>ms</span>
            <span />
          </li>
          {entries.map((entry) => (
            <LogRow key={entry.id} entry={entry} />
          ))}
        </ol>
      </section>
    </div>
  );
}

function RiskChart({ entry, catalogue }: { entry?: LogEntry; catalogue: DataMapQuerySpec[] | null }) {
  if (!entry) return <p className="dm-wait">Waiting for its query.</p>;
  if (entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  const result = entry.result;
  if (!result) return <p className="dm-wait">querying Zetaris…</p>;
  const labelOf = new Map((catalogue ?? []).map((q) => [q.id, q.label]));
  const rows = riskRows(result, labelOf);
  const max = rows.reduce((m, row) => Math.max(m, row.n), 0);
  return (
    <div className="dm-bars" role="list">
      {rows.map((row) => (
        <div key={row.key} role="listitem" aria-label={`${row.label}: ${row.text} high-risk medicine lines`}>
          <div className="dm-bar">
            <span className="dm-bar-name">{row.label}</span>
            <span className="dm-track">
              <span className="dm-fill" style={{ width: max > 0 ? `${(row.n / max) * 100}%` : "0%" }} />
            </span>
            <span className="dm-bar-val dm-num">{row.text}</span>
          </div>
          {row.note && <p className="dm-note">{PATIENT_NOTE}</p>}
        </div>
      ))}
    </div>
  );
}

function riskRows(result: DataMapQueryResult, labelOf: Map<string, string>) {
  const seen = new Set<string>();
  const rows: { key: string; label: string; text: string; n: number; note: boolean }[] = [];
  for (const id of SILOS) {
    seen.add(id);
    const found = result.data.find((row) => row[0] === id);
    const text = found && found[1] != null ? String(found[1]) : "0";
    const n = Number(text);
    rows.push({
      key: id,
      label: labelOf.get(id) ?? id,
      text,
      n: Number.isFinite(n) ? n : 0,
      note: id === "patient" && (!found || text === "0"),
    });
  }
  for (const row of result.data) {
    const key = row[0] == null ? "" : String(row[0]);
    if (seen.has(key)) continue;
    const text = row[1] == null ? "" : String(row[1]);
    const n = Number(text);
    rows.push({ key, label: key, text, n: Number.isFinite(n) ? n : 0, note: false });
  }
  return rows;
}

function QualityCard({ dq, rows }: { dq?: LogEntry; rows?: LogEntry }) {
  if (!dq) return <p className="dm-wait">Waiting for its query.</p>;
  if (dq.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (dq.phase === "error") return <p className="dm-err">{dq.error}</p>;
  const violations = soleCell(dq.result);
  const total = soleCell(rows?.result);
  if (violations == null) return <p className="dm-err">The data-quality query returned no count.</p>;
  return (
    <div>
      <p className="dm-dq-num dm-num" aria-label={`${violations} medicine lines failed the strength check`}>
        {violations}
      </p>
      <p className="dm-cap dm-dq-line">
        {total != null
          ? `of ${total} medicine lines have a strength that isn't a real product`
          : "medicine lines have a strength that isn't a real product"}
      </p>
      <p className="dm-rule">strength_is_a_real_product</p>
      <p className="dm-cap">Same predicate as the Zetaris data-quality rule</p>
      {dq.result?.sql && <pre className="dm-code">{dq.result.sql}</pre>}
    </div>
  );
}

function LogRow({ entry }: { entry: LogEntry }) {
  const result = entry.result;
  const time = result ? clock(result.executed_at) : "";
  const rows = result ? rowsShown(result) : "";
  const ms = result ? String(result.latency_ms) : "";
  return (
    <li className="dm-log-item">
      <div className="dm-log-row">
        <span className="dm-num">{time}</span>
        <span>{entry.label}</span>
        <span className="dm-num">{entry.phase === "running" ? "querying Zetaris…" : rows}</span>
        <span className="dm-num">{ms}</span>
        <span>{result?.replayed ? <span className="badge">replayed</span> : null}</span>
      </div>
      {entry.phase === "error" && <p className="dm-err">{entry.error}</p>}
      {result?.sql && (
        <details className="dm-fold">
          <summary>SQL</summary>
          <pre className="dm-code">{result.sql}</pre>
        </details>
      )}
    </li>
  );
}

function clock(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
