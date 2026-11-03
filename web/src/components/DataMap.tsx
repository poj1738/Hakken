// The Data map. Every count is a cell from GET /data-map/query/{id}.
// Mock mode does not invent a diagram.

import { useEffect, useRef, useState } from "react";
import { API_MODE } from "../api";
import type { DataMapQuerySpec } from "../types";
import { DataMapDiagram, RunStatus, formatCount, formatSeconds, soleCell, useDataMapRun, type LogEntry } from "./DataMapDiagram";

const SILOS = ["emr", "gp", "pharmacy", "patient"] as const;
const KNOWN_QUERIES = new Set(["emr", "gp", "pharmacy", "patient", "lexicon", "apinchs", "tga", "all_sources", "rows", "high_risk", "dq"]);
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
  const { catalogue, byId, entries, fatal, rerun, clock } = useDataMapRun(true);
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const find = (node: string) => {
    const query = catalogue?.find((q) => q.node === node);
    return query ? byId[query.id] : undefined;
  };
  const waysQuery = catalogue?.find((q) => !KNOWN_QUERIES.has(q.id) && q.id !== "dq_examples");
  const examplesQuery = catalogue?.find((q) => q.id === "dq_examples");

  return (
    <div className="dm-page">
      <header className="dm-head">
        <h1 className="dm-title">Data map</h1>
        <div className="dm-actions">
          <button type="button" className="btn btn-line" onClick={rerun}>
            Run live again
          </button>
          <button type="button" className="btn btn-primary" onClick={onPresent}>
            Presenter view
          </button>
        </div>
      </header>
      <RunStatus clock={clock} onRerun={rerun} />

      {fatal && (
        <div className="alert alert-note" role="alert">
          {fatal}
        </div>
      )}

      <div className="dm-top">
        <section className="panel dm-hero" aria-labelledby="dm-diagram-title">
          <h2 className="h2" id="dm-diagram-title">
            From six sources to one view
          </h2>
          <p className="dm-cap">Hover any box to see what it is and the query behind it.</p>
          <div className="dm-diagram">
            {catalogue ? (
              <DataMapDiagram catalogue={catalogue} byId={byId} flow={clock.phase === "done" || clock.phase === "cached"} />
            ) : (
              <p className="dm-wait">querying Zetaris…</p>
            )}
          </div>
        </section>

        <section className="panel panel-pad dm-log-card" aria-labelledby="dm-log-title">
          <h2 className="h2" id="dm-log-title">
            Live query log
          </h2>
          <p className="dm-cap">Every SQL statement sent to Zetaris, in order.</p>
          <div className="dm-log-scroll" ref={logRef}>
            <table className="dm-log">
              <caption className="dm-live">Query log</caption>
              <thead>
                <tr>
                  <th scope="col" className="dm-log-dot-col">
                    <span className="dm-live">Status</span>
                  </th>
                  <th scope="col">Time</th>
                  <th scope="col">Query</th>
                  <th scope="col" className="dm-log-num">
                    Result
                  </th>
                  <th scope="col" className="dm-log-num">
                    Took
                  </th>
                  <th scope="col">
                    <span className="dm-live">SQL</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <LogRow key={entry.id} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div className={`dm-bottom${waysQuery ? " dm-bottom-3" : ""}`}>
        <section className="panel panel-pad" aria-labelledby="dm-risk-title">
          <h2 className="h2" id="dm-risk-title">
            High-risk medicines by source
          </h2>
          <RiskChart entry={find("high_risk")} catalogue={catalogue} byId={byId} />
        </section>
        {waysQuery && (
          <section className="panel panel-pad" aria-labelledby="dm-ways-title">
            <h2 className="h2" id="dm-ways-title">
              Same medicine, written many ways
            </h2>
            <WaysCard entry={byId[waysQuery.id]} />
          </section>
        )}
        <section className="panel panel-pad" aria-labelledby="dm-dq-title">
          <QualityCard dq={find("dq")} rows={find("usl")} sql={catalogue?.find((q) => q.node === "dq")?.sql} examples={examplesQuery ? byId[examplesQuery.id] : undefined} />
        </section>
      </div>
    </div>
  );
}

const AU_PERCENT = new Intl.NumberFormat("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function RiskChart({
  entry,
  catalogue,
  byId,
}: {
  entry?: LogEntry;
  catalogue: DataMapQuerySpec[] | null;
  byId: Record<string, LogEntry>;
}) {
  if (!entry) return <p className="dm-wait">Waiting for its query.</p>;
  if (entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  const result = entry.result;
  if (!result) return <p className="dm-wait">querying Zetaris…</p>;
  const labelOf = new Map((catalogue ?? []).map((q) => [q.id, q.label]));
  const rows = riskRows(result, labelOf).map((row) => {
    const source = sourceCount(byId[row.key]);
    const pct = source != null && source > 0 ? (row.n / source) * 100 : 0;
    return { ...row, source, pct };
  });
  const maxPct = rows.reduce((m, row) => Math.max(m, row.pct), 0);
  return (
    <div className="dm-bars" role="list">
      {rows.map((row) => {
        const value = riskValue(row.text, row.n, row.source);
        const width = maxPct > 0 ? (row.pct / maxPct) * 100 : 0;
        return (
          <div key={row.key} role="listitem" aria-label={`${row.label}: ${value}`}>
            <div className="dm-bar">
              <span className="dm-bar-name">{row.label}</span>
              <span className="dm-bar-val dm-num">{value}</span>
            </div>
            <span className="dm-track">
              <span className="dm-fill" style={{ width: `${width}%` }} />
            </span>
            {row.note && <p className="dm-note">{PATIENT_NOTE}</p>}
          </div>
        );
      })}
    </div>
  );
}

function sourceCount(entry: LogEntry | undefined): number | null {
  if (!entry || entry.phase !== "done") return null;
  const cell = soleCell(entry.result);
  const n = cell == null ? Number.NaN : Number(cell);
  return Number.isFinite(n) ? n : null;
}

function riskValue(text: string, highRisk: number, source: number | null): string {
  const high = formatCount(text) ?? text;
  if (source == null) return high;
  const of = `${high} of ${formatCount(source)}`;
  if (!(source > 0) || !Number.isFinite(highRisk)) return of;
  return `${of} · ${AU_PERCENT.format((highRisk / source) * 100)}%`;
}

function riskRows(result: { data: (string | null)[][] }, labelOf: Map<string, string>) {
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

function WaysCard({ entry }: { entry?: LogEntry }) {
  if (!entry) return <p className="dm-wait">Waiting for its query.</p>;
  if (entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  const result = entry.result;
  if (!result) return <p className="dm-wait">querying Zetaris…</p>;
  return (
    <div className="dm-log-scroll">
      <table className="dm-log">
        <thead>
          <tr>
            {result.headers.map((header) => (
              <th key={header} scope="col">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.data.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QualityCard({ dq, rows, sql, examples }: { dq?: LogEntry; rows?: LogEntry; sql?: string; examples?: LogEntry }) {
  const [showSql, setShowSql] = useState(false);
  const violations = dq?.phase === "done" ? soleCell(dq.result) : null;
  const total = rows?.phase === "done" ? soleCell(rows.result) : null;
  const counted = violations == null ? null : formatCount(violations);
  const across = total == null ? null : formatCount(total);
  const exampleRows = examples?.phase === "done" ? examples.result?.data.slice(0, 3) ?? [] : [];
  return (
    <div>
      <h2 className="h2" id="dm-dq-title">
        Doses that don't exist
      </h2>
      {dq?.phase === "error" ? (
        <p className="dm-err">{dq.error}</p>
      ) : counted == null ? (
        <p className="dm-wait">querying Zetaris…</p>
      ) : (
        <div className="dm-dq-lead">
          <span className="dm-dq-num dm-num">{counted}</span>
          <div className="dm-list-copy">
            <p className="dm-dq-say">medicine lines list a strength no product comes in</p>
            {across != null && <p className="dm-cap">out of {across} lines across all four records</p>}
          </div>
        </div>
      )}
      {exampleRows.length > 0 && (
        <>
          <p className="dm-cap">For example:</p>
          <ul className="dm-examples">
            {exampleRows.map((row, i) => (
              <li key={i}>{row.filter((cell) => cell != null && cell !== "").join(" ")}</li>
            ))}
          </ul>
        </>
      )}
      <p className="dm-cap">
        Zetaris checks every line automatically with a rule stored in Zetaris: <span className="dm-mono">strength_is_a_real_product</span>
      </p>
      <p className="dm-cap">These are dose errors we planted to test MedTrace.</p>
      {sql && (
        <div>
          <button type="button" className="lnk" aria-expanded={showSql} onClick={() => setShowSql((open) => !open)}>
            {showSql ? "Hide the SQL" : "Show the SQL"}
          </button>
          {showSql && <pre className="dm-code">{formatSql(sql)}</pre>}
        </div>
      )}
    </div>
  );
}

function formatSql(sql: string): string {
  return sql.replace(/\s+\b(FROM|WHERE)\b\s+/g, "\n$1 ");
}

function resultWords(entry: LogEntry): string {
  if (entry.phase === "running") return "querying Zetaris…";
  if (entry.phase === "error") return entry.error ?? "The query failed";
  const result = entry.result;
  if (!result) return "";
  if (result.data.length === 1 && result.headers.length === 1) {
    const count = formatCount(soleCell(result));
    return count ? `${count} rows counted` : "";
  }
  const sources = formatCount(result.row_count ?? undefined);
  return sources ? `${sources} sources` : "";
}

function LogRow({ entry }: { entry: LogEntry }) {
  const result = entry.result;
  const time = result && entry.phase !== "running" ? clock(result.executed_at) : "";
  const took = result && entry.phase === "done" && result.latency_ms != null ? formatSeconds(result.latency_ms) : "";
  const dot = entry.phase === "error" ? "bad" : entry.phase === "running" ? "run" : entry.phase === "done" ? "done" : "";
  return (
    <tr>
      <td>
        <span className={`dm-dot-status ${dot}`} aria-hidden />
      </td>
      <td className="dm-log-time">{time}</td>
      <td>
        {entry.id === "dq" ? "Strengths no product comes in" : entry.label}
        {result?.replayed ? <span className="badge">replayed</span> : null}
      </td>
      <td className="dm-log-num">{resultWords(entry)}</td>
      <td className="dm-log-num">{took}</td>
      <td>
        {result?.sql ? (
          <details className="dm-fold">
            <summary>SQL</summary>
            <pre className="dm-code">{result.sql}</pre>
          </details>
        ) : null}
      </td>
    </tr>
  );
}

function clock(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
