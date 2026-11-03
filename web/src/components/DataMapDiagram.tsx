// One diagram of sources → the Zetaris semantic layer → MedTrace.
// The data map and the presenter view both render this. Positions are layout,
// not counts: a number appears only after that node's query has answered.

import { useCallback, useEffect, useRef, useState, type HTMLAttributes } from "react";
import { api } from "../api";
import type { DataMapQueryResult, DataMapQuerySpec } from "../types";

export type StoredResult = Omit<DataMapQueryResult, "latency_ms" | "row_count"> & {
  latency_ms: number | null;
  row_count: number | null;
};

export interface LogEntry {
  id: string;
  label: string;
  node: string;
  phase: "running" | "done" | "error";
  result?: StoredResult;
  error?: string;
}

const AU_COUNT = new Intl.NumberFormat("en-AU");
const AU_SECONDS = new Intl.NumberFormat("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function soleCell(result: { data: (string | null)[][] } | undefined): string | null {
  const value = result?.data[0]?.[0];
  if (value == null || value === "") return null;
  return String(value);
}

/** Australian grouping for a count that came back from Zetaris. A non-number stays as returned. */
export function formatCount(raw: string | number | null | undefined): string | null {
  if (raw == null || raw === "") return null;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return String(raw);
  return AU_COUNT.format(n);
}

/** Latency as seconds with one decimal, from the adapter's latency_ms. */
export function formatSeconds(ms: number): string {
  return `${AU_SECONDS.format(ms / 1000)} s`;
}

/** Rows column: a single count's cell, otherwise how many rows came back. */
export function rowsShown(result: StoredResult): string {
  if (result.data.length === 1 && result.headers.length === 1) {
    const cell = soleCell(result);
    if (cell != null) return cell;
  }
  return String(result.row_count);
}

const STORAGE_KEY = "medtrace.datamap.lastRun";

export interface SavedRun {
  startedAt: string;
  durationMs: number;
  results: StoredResult[];
}

export type RunPhase = "idle" | "cached" | "running" | "done";

export interface RunClock {
  phase: RunPhase;
  startedAt: string | null;
  durationMs: number | null;
  replayed: boolean;
}

function readCache(): SavedRun | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedRun;
    if (!parsed || typeof parsed.startedAt !== "string" || !Array.isArray(parsed.results) || parsed.results.length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(run: SavedRun) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(run));
  } catch {
    // Storage can be blocked. The run still shows; it just will not be there next time.
  }
}

function entryFrom(result: StoredResult, node: string): LogEntry {
  const failed = result.error != null && result.error !== "";
  return {
    id: result.id,
    label: result.label,
    node,
    phase: failed ? "error" : "done",
    result,
    error: failed ? (result.error ?? undefined) : undefined,
  };
}

const initialSaved = readCache();

export function useDataMapRun(enabled: boolean) {
  const [catalogue, setCatalogue] = useState<DataMapQuerySpec[] | null>(null);
  const [byId, setById] = useState<Record<string, LogEntry>>({});
  const [entries, setEntries] = useState<LogEntry[]>(() => (initialSaved ? initialSaved.results.map((r) => entryFrom(r, r.id)) : []));
  const [fatal, setFatal] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [clock, setClock] = useState<RunClock>(() =>
    initialSaved
      ? {
          phase: "cached",
          startedAt: initialSaved.startedAt,
          durationMs: initialSaved.durationMs,
          replayed: initialSaved.results.some((r) => r.replayed),
        }
      : { phase: "idle", startedAt: null, durationMs: null, replayed: false },
  );
  const gen = useRef(0);
  const forceLive = useRef(false);
  const running = useRef(false);
  const catalogueRef = useRef<DataMapQuerySpec[] | null>(null);

  const paint = useCallback((queries: DataMapQuerySpec[], saved: SavedRun, phase: RunPhase) => {
    const nodeOf = new Map(queries.map((q) => [q.id, q.node]));
    const list = saved.results.map((r) => entryFrom(r, nodeOf.get(r.id) ?? r.id));
    const map: Record<string, LogEntry> = {};
    for (const item of list) map[item.id] = item;
    catalogueRef.current = queries;
    setCatalogue(queries);
    setEntries(list);
    setById(map);
    setClock({
      phase,
      startedAt: saved.startedAt,
      durationMs: saved.durationMs,
      replayed: saved.results.some((r) => r.replayed),
    });
  }, []);

  const rerun = useCallback(() => {
    forceLive.current = true;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY || running.current) return;
      const saved = readCache();
      const queries = catalogueRef.current;
      if (!saved || !queries || saved.results.length !== queries.length) return;
      paint(queries, saved, "cached");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [enabled, paint]);

  useEffect(() => {
    if (!enabled) return;
    const token = ++gen.current;
    const ctrl = new AbortController();
    const alive = () => token === gen.current && !ctrl.signal.aborted;
    const live = forceLive.current;
    forceLive.current = false;
    setFatal(null);

    (async () => {
      let queries = catalogueRef.current;
      try {
        if (!queries) {
          const cat = await api.dataMapQueries(ctrl.signal);
          if (!alive()) return;
          queries = cat.queries;
          catalogueRef.current = queries;
          setCatalogue(queries);
        }
      } catch (err) {
        if (!alive() || (err instanceof DOMException && err.name === "AbortError")) return;
        setFatal(err instanceof Error ? err.message : String(err));
        return;
      }

      const saved = live ? null : readCache();
      if (saved && saved.results.length === queries.length) {
        paint(queries, saved, "cached");
        return;
      }

      running.current = true;
      const startedMs = Date.now();
      const startedAt = new Date(startedMs).toISOString();
      setClock({ phase: "running", startedAt, durationMs: null, replayed: false });
      setById({});
      setEntries([]);
      const collected: StoredResult[] = [];
      let sawReplay = false;
      try {
        for (const query of queries) {
          if (!alive()) return;
          const runningEntry: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "running" };
          setById((m) => ({ ...m, [query.id]: runningEntry }));
          setEntries((es) => [...es.filter((e) => e.id !== query.id), runningEntry]);
          try {
            const result = await api.dataMapQuery(query.id, ctrl.signal);
            if (!alive()) return;
            collected.push(result);
            if (result.replayed) sawReplay = true;
            const done: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "done", result };
            setById((m) => ({ ...m, [query.id]: done }));
            setEntries((es) => es.map((e) => (e.id === query.id ? done : e)));
          } catch (err) {
            if (!alive() || (err instanceof DOMException && err.name === "AbortError")) return;
            const message = err instanceof Error ? err.message : String(err);
            collected.push({
              id: query.id,
              label: query.label,
              sql: query.sql,
              headers: [],
              data: [],
              row_count: null,
              latency_ms: null,
              executed_at: "",
              replayed: false,
              error: message,
            });
            const failed: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "error", error: message };
            setById((m) => ({ ...m, [query.id]: failed }));
            setEntries((es) => es.map((e) => (e.id === query.id ? failed : e)));
          }
        }
        if (!alive() || collected.length !== queries.length) return;
        const durationMs = Date.now() - startedMs;
        writeCache({ startedAt, durationMs, results: collected });
        setClock({ phase: "done", startedAt, durationMs, replayed: sawReplay });
      } finally {
        if (token === gen.current) running.current = false;
      }
    })();

    return () => ctrl.abort();
  }, [enabled, nonce, paint]);

  return { catalogue, byId, entries, fatal, rerun, clock };
}

export function RunStatus({ clock, onRerun }: { clock: RunClock; onRerun: () => void }) {
  const ticking = clock.phase === "running" || clock.phase === "cached";
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!ticking) return;
    const id = window.setInterval(() => setNow(Date.now()), clock.phase === "running" ? 1000 : 30000);
    return () => window.clearInterval(id);
  }, [ticking, clock.phase]);

  if (clock.phase === "idle" || !clock.startedAt) return null;
  const source = clock.replayed ? "Replayed" : "Live from Zetaris";
  if (clock.phase === "running") {
    const elapsed = Math.max(0, now - Date.parse(clock.startedAt));
    return <p className="dm-status">● {source} · running {formatElapsed(elapsed)}</p>;
  }
  if (clock.phase === "cached") {
    const started = Date.parse(clock.startedAt);
    const mins = Number.isFinite(started) ? Math.max(0, Math.floor((now - started) / 60000)) : 0;
    const origin = clock.replayed ? "Replayed" : "live Zetaris";
    return (
      <p className="dm-status">
        Results from the {origin} run at {clockTime(clock.startedAt)} ({formatCount(mins)} min ago) ·{" "}
        <button type="button" className="lnk" onClick={onRerun}>
          Run live again
        </button>
      </p>
    );
  }
  const duration = clock.durationMs ?? 0;
  const minutes = Math.floor(duration / 60000);
  const seconds = Math.floor((duration % 60000) / 1000);
  const finishedAt = new Date(Date.parse(clock.startedAt) + duration).toISOString();
  return (
    <p className="dm-status">
      ● {source} · Last run {clockTime(finishedAt)} · took {formatCount(minutes)} min {formatCount(seconds)} s
    </p>
  );
}

function formatElapsed(ms: number): string {
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  if (minutes <= 0) return `${formatCount(seconds)} s`;
  return `${formatCount(minutes)} min ${formatCount(seconds)} s`;
}

function clockTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const VB_W = 1440;
const PAD = 16;
const SRC_W = 400;
const ROW_H = 50;
const LIST_HEAD = 28;
const LIST_PAD = 8;
const LIST_GAP = 16;
const USL_W = 280;
const USL_H = 168;
const AGENT_W = 188;
const AGENT_H = 52;
const AGENT_GAP = 12;
const GROUP_PAD = 8;
const RETRY_GUTTER = 42;
const GROUP_W = GROUP_PAD + AGENT_W + RETRY_GUTTER + GROUP_PAD;
const GROUP_H = GROUP_PAD + 4 * AGENT_H + 3 * AGENT_GAP + GROUP_PAD;
const TRACE_HEAD = 40;
const TRACE_W = GROUP_W;
const COL_GAP = (VB_W - PAD * 2 - SRC_W - USL_W - TRACE_W) / 2;
const SRC_X = PAD;
const USL_X = SRC_X + SRC_W + COL_GAP;
const TRACE_X = USL_X + USL_W + COL_GAP;
const BUS_X = SRC_X + SRC_W + COL_GAP / 2;
const USL_TABLES = ["medicine", "high_risk_class", "medication_statement"] as const;
const AGENTS = [
  { id: "planner", name: "Planner", job: "Splits the job into steps" },
  { id: "executor", name: "Executor", job: "Runs the SQL in Zetaris" },
  { id: "evaluator", name: "Evaluator", job: "Re-checks every cited row in Zetaris" },
  { id: "writer", name: "Writer", job: "Explains each finding for a pharmacist" },
] as const;

function curve(x1: number, y1: number, x2: number, y2: number) {
  const c = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${c} ${y1}, ${c} ${y2}, ${x2} ${y2}`;
}

function useReducedMotion() {
  const [on, setOn] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setOn(mq.matches);
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return on;
}

interface Props {
  catalogue: DataMapQuerySpec[];
  byId: Record<string, LogEntry>;
  /** Presenter focus. Omit it on the data map so nothing is dimmed. */
  lit?: readonly string[];
  present?: boolean;
  /** Slow dots along lit edges, only once every query has finished. */
  flow?: boolean;
}

const SKIP = new Set(["merge", "usl", "high_risk", "dq"]);
const XHTML = { xmlns: "http://www.w3.org/1999/xhtml" } as HTMLAttributes<HTMLDivElement>;

/** The short line from each source's description, shown on the card itself. */
const BLURB: Record<string, string> = {
  emr: "What was charted in hospital.",
  gp: "What the GP prescribed.",
  pharmacy: "What was actually supplied, and when.",
  patient: "What the patient says they take, in their own words.",
  lexicon: "Australia's list of subsidised medicines.",
  apinchs: "Medicines a pharmacist must review first.",
  tga: "Supply check: MedTrace looks up each patient's medicines here for shortage notices. Not part of the semantic layer.",
};

export function DataMapDiagram({ catalogue, byId, lit, present = false, flow = false }: Props) {
  const reduced = useReducedMotion();
  const [hoverId, setHoverId] = useState<string | null>(null);
  const sources = catalogue.filter((q) => !SKIP.has(q.node) && q.node !== "tga");
  const tgaQuery = catalogue.find((q) => q.node === "tga");
  const srcW = SRC_W;
  const clinical = sources.filter((q) => q.node === "emr" || q.node === "gp" || q.node === "pharmacy" || q.node === "patient");
  const reference = sources.filter((q) => q.node === "lexicon" || q.node === "apinchs");
  const listH = (n: number) => LIST_PAD + LIST_HEAD + n * ROW_H + LIST_PAD;
  const clinicalY = PAD;
  const clinicalH = listH(clinical.length);
  const referenceY = clinicalY + clinicalH + LIST_GAP;
  const referenceH = listH(reference.length);
  const rowCy = (listY: number, i: number) => listY + LIST_PAD + LIST_HEAD + i * ROW_H + ROW_H / 2;
  const columnTop = clinicalY;
  const columnBottom = reference.length ? referenceY + referenceH : clinicalY + clinicalH;
  const columnMid = (columnTop + columnBottom) / 2;
  const uslBox = { x: USL_X, y: Math.max(PAD, columnMid - USL_H / 2), w: USL_W, h: USL_H };
  const spec = (node: string) => catalogue.find((q) => q.node === node);
  const entry = (node: string) => {
    const query = spec(node);
    return query ? byId[query.id] : undefined;
  };
  const dimming = lit != null;
  const isLit = (node: string) => !dimming || (lit ?? []).includes(node);
  const edgeOn = (node: string) => {
    const phase = entry(node)?.phase;
    if (phase === "error") return false;
    if (dimming) return isLit(node);
    return phase === "done";
  };

  const mergeY = clinical.length ? (rowCy(clinicalY, 0) + rowCy(clinicalY, clinical.length - 1)) / 2 : uslBox.y + uslBox.h / 2;
  const uslCy = uslBox.y + uslBox.h / 2;
  // Top to bottom on the semantic layer's left edge, matching source order, so the lines do not cross.
  const entryPad = 28;
  const entryY = (i: number) => uslBox.y + entryPad + ((uslBox.h - entryPad * 2) * i) / 2;
  const mergeEntryY = entryY(0);
  const lexiconEntryY = entryY(1);
  const apinchsEntryY = entryY(2);
  const mergeEntry = entry("merge");
  const mergeOn = mergeEntry?.phase === "error" ? false : dimming ? isLit("merge") : mergeEntry?.phase === "done";
  const trunk = curve(BUS_X, mergeY, uslBox.x, mergeEntryY);
  // Sit the four agents so the Executor and Evaluator lines stay horizontal and inside the semantic layer's right edge.
  const execOffset = GROUP_PAD + (AGENT_H + AGENT_GAP) + AGENT_H / 2;
  const evalOffset = GROUP_PAD + 2 * (AGENT_H + AGENT_GAP) + AGENT_H / 2;
  let groupTop = uslCy - (execOffset + evalOffset) / 2;
  let headTop = groupTop - 8 - TRACE_HEAD;
  if (headTop < 8) {
    groupTop += 8 - headTop;
    headTop = 8;
  }
  const groupX = TRACE_X;
  const agentX = groupX + GROUP_PAD;
  const agentRight = agentX + AGENT_W;
  const boxY = (i: number) => groupTop + GROUP_PAD + i * (AGENT_H + AGENT_GAP);
  const execCy = boxY(1) + AGENT_H / 2;
  const evalCy = boxY(2) + AGENT_H / 2;
  const tgaY = groupTop + GROUP_H + 28;
  const tgaH = 108;
  const uslRight = uslBox.x + uslBox.w;
  const sqlLine = `M ${uslRight} ${execCy} L ${agentX} ${execCy}`;
  const recheckLine = `M ${agentX} ${evalCy} L ${uslRight} ${evalCy}`;
  const linkOn = entry("usl")?.phase === "done" && (!dimming || isLit("usl") || isLit("medtrace"));
  const dropX = Math.min(agentRight + 16, groupX + GROUP_W - 12);
  const shortage = tgaQuery != null ? `M ${dropX} ${execCy} L ${dropX} ${tgaY - 14}` : "";
  const retry = `M ${agentRight} ${evalCy} C ${agentRight + 22} ${evalCy}, ${agentRight + 22} ${execCy}, ${agentRight} ${execCy}`;
  const vbH = Math.max(columnBottom, uslBox.y + uslBox.h + 24, tgaY + tgaH + 16);

  return (
    <div className={present ? "dm-stage dm-stage-present" : "dm-stage"}>
    <svg
      className={`dm-svg${present ? " present" : ""}`}
      viewBox={`0 0 ${VB_W} ${vbH}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Sources flowing through the Zetaris semantic layer into MedTrace"
    >
      <defs>
        <marker id="dm-arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L8 4 L0 8 Z" className="dm-arr" />
        </marker>
      </defs>
      {clinical.map((query, i) => (
        <Edge
          key={query.id}
          d={curve(SRC_X + srcW, rowCy(clinicalY, i), BUS_X, mergeY)}
          on={edgeOn(query.node)}
          faint={dimming && !isLit(query.node)}
          reduced={reduced}
          flow={flow}
        />
      ))}
      <Edge d={trunk} on={mergeOn} faint={dimming && !isLit("merge")} reduced={reduced} flow={flow} />
      {reference.map((query, i) => (
        <Edge
          key={query.id}
          d={curve(SRC_X + srcW, rowCy(referenceY, i), uslBox.x, i === 0 ? lexiconEntryY : apinchsEntryY)}
          on={edgeOn(query.node)}
          faint={dimming && !isLit(query.node)}
          reduced={reduced}
          flow={flow}
        />
      ))}
      <rect x={groupX} y={groupTop} width={GROUP_W} height={GROUP_H} rx={14} className="dm-trace-frame" />
      <Edge d={sqlLine} on={linkOn} faint={dimming && !isLit("usl") && !isLit("medtrace")} reduced={reduced} flow={flow} />
      <Edge d={recheckLine} on={linkOn} faint={dimming && !isLit("usl") && !isLit("medtrace")} reduced={reduced} flow={flow} />
      {shortage && (
        <Edge d={shortage} on={edgeOn("tga")} optional faint={dimming && !isLit("tga")} reduced={reduced} flow={flow} />
      )}

      <SourceList
        x={SRC_X}
        y={clinicalY}
        w={srcW}
        h={clinicalH}
        title="Patient records · synthetic"
        queries={clinical}
        byId={byId}
        dimming={dimming}
        isLit={isLit}
        hoverId={hoverId}
        onHover={setHoverId}
      />
      <SourceList
        x={SRC_X}
        y={referenceY}
        w={srcW}
        h={referenceH}
        title="Australian reference data · real"
        queries={reference}
        byId={byId}
        dimming={dimming}
        isLit={isLit}
        hoverId={hoverId}
        onHover={setHoverId}
      />

      <MergeLabel x={BUS_X - 100} y={mergeY - 28} w={Math.max(120, COL_GAP - 12)} entry={mergeEntry} faint={dimming && !isLit("merge")} />

      <NodeBox
        x={uslBox.x}
        y={uslBox.y}
        w={uslBox.w}
        h={uslBox.h}
        label={spec("usl")?.label ?? "Zetaris · semantic layer (medtrace_usl)"}
        usl
        chips={USL_TABLES}
        caption="medicine lines, every source in one shape"
        entry={entry("usl")}
        active={dimming && isLit("usl")}
        faint={dimming && !isLit("usl")}
        nodeId="usl"
      />
      <foreignObject x={groupX} y={headTop} width={GROUP_W} height={TRACE_HEAD} aria-hidden="true">
        <div {...XHTML} className="dm-trace-head">
          <div className="dm-trace-kicker">MedTrace</div>
          <div className="dm-trace-sub">Asks Zetaris in SQL</div>
        </div>
      </foreignObject>
      {AGENTS.slice(0, -1).map((agent, i) => (
        <line
          key={agent.id}
          x1={agentX + AGENT_W / 2}
          y1={boxY(i) + AGENT_H}
          x2={agentX + AGENT_W / 2}
          y2={boxY(i + 1)}
          className="dm-join"
          markerEnd="url(#dm-arr)"
        />
      ))}
      <path d={retry} className="dm-join" markerEnd="url(#dm-arr)" />
      <text className="dm-mini" x={(uslRight + agentX) / 2} y={execCy - 8} textAnchor="middle">
        SQL
      </text>
      <text className="dm-mini" x={(uslRight + agentX) / 2} y={evalCy - 8} textAnchor="middle">
        re-check
      </text>
      <text className="dm-mini" x={agentRight + 22} y={(execCy + evalCy) / 2 + 4} textAnchor="middle">
        retry
      </text>
      <text className="dm-mini" x={groupX + GROUP_W / 2} y={tgaY - 4} textAnchor="middle">
        shortage lookup
      </text>
      {AGENTS.map((agent, i) => (
        <AgentBox
          key={agent.id}
          x={agentX}
          y={boxY(i)}
          w={AGENT_W}
          h={AGENT_H}
          id={agent.id}
          name={agent.name}
          job={agent.job}
          faint={dimming && !isLit("medtrace")}
        />
      ))}
      {tgaQuery && (
        <NodeBox
          x={groupX}
          y={tgaY}
          w={GROUP_W}
          h={tgaH}
          label={tgaQuery.label}
          optional
          entry={byId[tgaQuery.id]}
          active={dimming && isLit("tga")}
          faint={dimming && !isLit("tga")}
          nodeId="tga"
          blurb={BLURB.tga}
        />
      )}
    </svg>
    {hoverId && <QueryHover id={hoverId} catalogue={catalogue} byId={byId} onLeave={() => setHoverId(null)} />}
    </div>
  );
}

function SourceList({
  x,
  y,
  w,
  h,
  title,
  queries,
  byId,
  dimming,
  isLit,
  hoverId,
  onHover,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  queries: DataMapQuerySpec[];
  byId: Record<string, LogEntry>;
  dimming: boolean;
  isLit: (node: string) => boolean;
  hoverId: string | null;
  onHover: (id: string | null) => void;
}) {
  return (
    <foreignObject x={x} y={y} width={w} height={h}>
      <div {...XHTML} className="dm-list">
        <div className="dm-list-head dm-group">
          <span>{title}</span>
          <span>Rows</span>
        </div>
        {queries.map((query) => {
          const entry = byId[query.id];
          const phase = entry?.phase;
          const count = phase === "done" ? soleCell(entry?.result) : null;
          const waiting = phase === "running";
          const failed = phase === "error";
          return (
            <div
              {...XHTML}
              key={query.id}
              className={`dm-list-row${dimming && !isLit(query.node) ? " dm-faint" : ""}${hoverId === query.id ? " on" : ""}`}
              data-node={query.node}
              onMouseEnter={() => onHover(query.id)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(query.id)}
              onBlur={() => onHover(null)}
              tabIndex={0}
              role="group"
              aria-label={`${query.label}. ${BLURB[query.node] ?? ""}`}
            >
              <span className={`dm-dot-status${phase === "done" ? " done" : ""}${waiting ? " run" : ""}${failed ? " bad" : ""}`} />
              <div className="dm-list-copy">
                <div className="dm-name">{query.label}</div>
                <div className="dm-blurb">{failed ? entry?.error ?? "The query failed" : waiting ? "querying Zetaris…" : BLURB[query.node]}</div>
              </div>
              <div className="dm-count dm-num">{count != null ? formatCount(count) : ""}</div>
            </div>
          );
        })}
      </div>
    </foreignObject>
  );
}

function QueryHover({
  id,
  catalogue,
  byId,
  onLeave,
}: {
  id: string;
  catalogue: DataMapQuerySpec[];
  byId: Record<string, LogEntry>;
  onLeave: () => void;
}) {
  const query = catalogue.find((q) => q.id === id || q.node === id);
  const entry = query ? byId[query.id] : undefined;
  const blurb = BLURB[id] ?? (id === "usl" ? "Every question after this is one SELECT." : AGENTS.find((agent) => agent.id === id)?.job ?? "");
  const sql = entry?.result?.sql ?? query?.sql ?? "";
  return (
    <div className="dm-hover" onMouseLeave={onLeave} role="note">
      <p className="dm-name">{query?.label ?? id}</p>
      {blurb && <p className="dm-blurb">{blurb}</p>}
      {sql && <pre className="dm-code">{sql}</pre>}
    </div>
  );
}

function Edge({
  d,
  on,
  optional = false,
  faint,
  reduced,
  flow,
}: {
  d: string;
  on: boolean;
  optional?: boolean;
  faint: boolean;
  reduced: boolean;
  flow: boolean;
}) {
  return (
    <g className={faint ? "dm-faint" : undefined} aria-hidden>
      <path d={d} className={`dm-edge${on ? " dm-edge-on" : ""}${optional ? " dm-edge-opt" : ""}`} pathLength={optional ? undefined : 1} />
      {on && flow && !reduced && (
        <circle r="3.5" className="dm-dot">
          <animateMotion dur="4s" repeatCount="indefinite" path={d} />
        </circle>
      )}
    </g>
  );
}

function NodeBox({
  x,
  y,
  w,
  h,
  label,
  entry,
  optional = false,
  usl = false,
  caption,
  chips,
  active,
  faint,
  noCount = false,
  nodeId,
  blurb,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  entry?: LogEntry;
  optional?: boolean;
  usl?: boolean;
  caption?: string;
  chips?: readonly string[];
  active: boolean;
  faint: boolean;
  noCount?: boolean;
  nodeId: string;
  blurb?: string;
}) {
  const phase = entry?.phase;
  const count = phase === "done" ? soleCell(entry?.result) : null;
  const tgaMiss = optional && phase === "error";
  const detail = tgaMiss ? "not registered" : phase === "error" ? entry?.error ?? "The query failed" : null;
  const waiting = phase === "running" ? "querying Zetaris…" : null;
  const shown = noCount ? null : count;
  const aria = noCount
    ? `${label}. ${caption ?? ""}`
    : [
        label,
        optional ? "optional overlay" : "",
        blurb ?? "",
        shown ? `${formatCount(shown) ?? shown} rows` : "",
        waiting ?? "",
        detail ?? "",
        !shown && !waiting && !detail ? "waiting for its query" : "",
      ]
        .filter(Boolean)
        .join(". ");
  const state =
    phase === "error" ? "dm-bad" : phase === "running" ? "pn pn-now" : phase === "done" || active ? "pn pn-used" : "pn pn-idle";
  const cls = ["dm-g", faint ? "dm-faint" : "", state, usl ? "dm-usl" : ""].filter(Boolean).join(" ");

  return (
    <g className={cls} data-node={nodeId}>
      <rect x={x} y={y} width={w} height={h} rx={usl ? 24 : 12} className={`dm-box${optional ? " dm-box-opt" : ""}${usl ? " dm-box-usl" : " dm-box-ghost"}`} />
      <foreignObject x={x} y={y} width={w} height={h}>
        <div
          {...XHTML}
          className={`dm-node-body ${state}${usl ? " dm-usl-body" : " panel dm-src"}${optional ? " dm-opt" : ""}${phase === "done" && !usl ? " dm-arrived" : ""}`}
          aria-label={aria}
        >
          <div className={usl ? undefined : "dm-src-line"}>
            <div className="dm-name">
              {phase === "running" && <span className="pn-dot" />}
              {label}
            </div>
            {!usl && shown && <div className="dm-count dm-num">{formatCount(shown)}</div>}
          </div>
          {!usl && waiting && !blurb && <div className="dm-wait">{waiting}</div>}
          {usl && waiting && <div className="dm-wait">{waiting}</div>}
          {detail && (
            <div className="dm-err" title={detail}>
              {detail}
            </div>
          )}
          {usl && shown && <div className="dm-count dm-num">{formatCount(shown)}</div>}
          {blurb && !detail && <div className="dm-blurb">{blurb}</div>}
          {usl && shown && caption && <div className="dm-cap">{caption}</div>}
          {shown && chips && (
            <div className="dm-chips">
              {chips.map((name) => (
                <span key={name} className="dm-chip">
                  {name}
                </span>
              ))}
            </div>
          )}
        </div>
      </foreignObject>
    </g>
  );
}

function AgentBox({
  x,
  y,
  w,
  h,
  id,
  name,
  job,
  faint,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  id: string;
  name: string;
  job: string;
  faint: boolean;
}) {
  return (
    <g className={faint ? "dm-faint" : undefined} data-node={id}>
      <rect x={x} y={y} width={w} height={h} rx={12} className="dm-box dm-box-ghost" />
      <foreignObject x={x} y={y} width={w} height={h}>
        <div {...XHTML} className="dm-node-body panel dm-src dm-agent" aria-label={`${name}. ${job}`}>
          <div className="dm-agent-name">{name}</div>
          <div className="dm-agent-job">{job}</div>
        </div>
      </foreignObject>
    </g>
  );
}

function MergeLabel({ x, y, w, entry, faint }: { x: number; y: number; w: number; entry?: LogEntry; faint: boolean }) {
  const count = entry?.phase === "done" ? soleCell(entry.result) : null;
  const text =
    entry?.phase === "running" ? "querying Zetaris…" : count ? `4 systems → ${formatCount(count)} medicine lines` : "";
  if (!text) return null;
  return (
    <foreignObject x={x} y={y} width={w} height={22} className={faint ? "dm-faint" : undefined}>
      <div {...XHTML} className="dm-merge" role="img" aria-label={text}>
        {text}
      </div>
    </foreignObject>
  );
}
