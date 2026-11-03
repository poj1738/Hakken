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
          <div className="dm-diagram">
            {catalogue ? (
              <DataMapDiagram catalogue={catalogue} byId={byId} flow={clock.phase === "done" || clock.phase === "cached"} />
            ) : (
              <p className="dm-wait">querying Zetaris…</p>
            )}
          </div>
        </section>

        <QueryLog entries={entries} catalogue={catalogue} clock={clock} />
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
  return sql.replace(/\s+\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|LIMIT)\b/gi, (_match, keyword: string, offset: number) =>
    offset === 0 ? keyword : `\n${keyword}`,
  );
}

function QueryLog({
  entries,
  catalogue,
  clock,
}: {
  entries: LogEntry[];
  catalogue: DataMapQuerySpec[] | null;
  clock: { phase: string; startedAt: string | null; durationMs: number | null; replayed: boolean };
}) {
  const latest = entries.length ? entries[entries.length - 1] : undefined;
  const earlier = entries.slice(0, -1).slice().reverse();
  const [openId, setOpenId] = useState<string | null>(null);
  const [demoted, setDemoted] = useState<string | null>(null);
  const prevLatest = useRef<string | null>(null);
  useEffect(() => {
    const id = latest?.id ?? null;
    if (prevLatest.current && id && prevLatest.current !== id) setDemoted(prevLatest.current);
    prevLatest.current = id;
  }, [latest?.id]);
  const sqlOf = (entry: LogEntry) => entry.result?.sql ?? catalogue?.find((q) => q.id === entry.id)?.sql ?? "";
  const finished = clock.phase === "done" && clock.durationMs != null;
  const cached = clock.phase === "cached";
  return (
    <section className="panel panel-pad dm-log-card" aria-labelledby="dm-log-title">
      <h2 className="h2" id="dm-log-title">
        Live query log
      </h2>
      <p className="dm-desc">Every SQL statement sent to Zetaris, newest first.</p>
      {finished && <p className="dm-cap">All {formatCount(entries.length)} queries done · {formatSeconds(clock.durationMs ?? 0)}</p>}
      {cached && clock.startedAt && (
        <p className="dm-cap">From the {clock.replayed ? "replayed" : "live"} run at {sentAt(clock.startedAt)}</p>
      )}
      {latest ? (
        <LatestBlock entry={latest} sql={sqlOf(latest)} />
      ) : (
        <p className="dm-wait">querying Zetaris…</p>
      )}
      {earlier.length > 0 && (
        <>
          <h3 className="dm-earlier-h">Earlier queries ({formatCount(earlier.length)})</h3>
          <div className="dm-log-scroll">
            {earlier.map((entry) => (
              <EarlierRow
                key={entry.id}
                entry={entry}
                sql={sqlOf(entry)}
                open={openId === entry.id}
                fresh={demoted === entry.id}
                onToggle={() => setOpenId((current) => (current === entry.id ? null : entry.id))}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function LatestBlock({ entry, sql }: { entry: LogEntry; sql: string }) {
  const result = entry.phase === "error" ? entry.error ?? "The query failed" : entry.phase === "running" ? "querying Zetaris…" : doneLine(entry);
  const spoken = `${entry.label}: ${result}`;
  return (
    <div className="dm-latest" aria-live="polite" aria-atomic="true">
      <div className="dm-latest-top">
        <span className={`dm-dot-status${dotClass(entry)}`} aria-hidden />
        <span className="dm-latest-name">{entry.label}</span>
        <span className={entry.phase === "error" ? "dm-latest-result dm-err" : "dm-latest-result dm-num"}>{result}</span>
      </div>
      <p className="dm-sent">Sent {sentAt(entry.result?.executed_at || entry.startedAt)}</p>
      <span className="dm-live">{spoken}</span>
      {entry.phase !== "error" && sql && <pre className="dm-sql">{formatSql(sql)}</pre>}
    </div>
  );
}

function EarlierRow({
  entry,
  sql,
  open,
  fresh,
  onToggle,
}: {
  entry: LogEntry;
  sql: string;
  open: boolean;
  fresh: boolean;
  onToggle: () => void;
}) {
  const failed = entry.phase === "error";
  return (
    <div className={fresh ? "dm-earlier-wrap is-new" : "dm-earlier-wrap"}>
      <button type="button" className="dm-earlier" aria-expanded={open} onClick={onToggle}>
        <span className={`dm-dot-status${dotClass(entry)}`} aria-hidden />
        <span className="dm-earlier-time">{sentAt(entry.result?.executed_at || entry.startedAt)}</span>
        <span className="dm-earlier-name">{entry.label}</span>
        <span className={failed ? "dm-earlier-result dm-err" : "dm-earlier-result"}>{failed ? entry.error ?? "The query failed" : shortResult(entry)}</span>
        <span className="dm-earlier-took">{entry.result?.latency_ms != null ? formatSeconds(entry.result.latency_ms) : ""}</span>
      </button>
      {open && sql && <pre className="dm-sql">{formatSql(sql)}</pre>}
    </div>
  );
}

function dotClass(entry: LogEntry): string {
  if (entry.phase === "error") return " bad";
  if (entry.phase === "running") return " run";
  if (entry.phase === "done") return " done";
  return "";
}

function shortResult(entry: LogEntry): string {
  const result = entry.result;
  if (!result || entry.phase !== "done") return "";
  if (result.data.length === 1 && result.headers.length === 1) {
    const count = formatCount(soleCell(result));
    if (!count) return "";
    return entry.node === "dq" ? `${count} lines` : `${count} rows`;
  }
  const count = formatCount(result.data.length);
  if (!count) return "";
  return entry.node === "high_risk" ? `${count} sources` : `${count} rows`;
}

function doneLine(entry: LogEntry): string {
  const summary = shortResult(entry);
  const took = entry.result?.latency_ms != null ? formatSeconds(entry.result.latency_ms) : "";
  if (summary && took) return `${summary} · ${took}`;
  return summary || took;
}

function sentAt(iso: string | undefined): string {
  if (!iso) return "…";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
