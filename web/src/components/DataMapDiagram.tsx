// One diagram of sources → the Zetaris semantic layer → MedTrace.
// The data map and the presenter view both render this. Positions are layout,
// not counts: a number appears only after that node's query has answered.

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type HTMLAttributes } from "react";
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
  /** When this request was sent. Set on the running entry; a finished row uses executed_at. */
  startedAt?: string;
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
          const runningEntry: LogEntry = {
            id: query.id,
            label: query.label,
            node: query.node,
            phase: "running",
            startedAt: new Date().toISOString(),
          };
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

export function RunStatus({ clock }: { clock: RunClock; onRerun: () => void }) {
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
    const origin = clock.replayed ? "replayed" : "live Zetaris";
    return (
      <p className="dm-status">
        Showing the {origin} run from {clockTime(clock.startedAt)} ({formatCount(mins)} min ago)
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

// Screen pixels. The viewBox matches the card, so one unit is one pixel.
// Floors: names 13, descriptions 11, connector labels 10, counts 14,
// semantic-layer count 30. These sit above those floors.
const NAME_PX = 14;
const DESC_PX = 12;
const USL_COUNT_PX = 32;
const LABEL_PX = 11;
const ROW_H = 56;
const HEAD_H = 30;
const LIST_GAP = 16;
const AGENT_H = 52;
const AGENT_GAP = 12;
const GROUP_PAD = 12;
const TRACE_HEAD = 36;
const USL_TABLES = ["medicine", "high_risk_class", "medication_statement"] as const;
const AGENTS = [
  { id: "planner", name: "Planner", job: "Splits the job" },
  { id: "executor", name: "Executor", job: "Runs SQL in Zetaris" },
  { id: "evaluator", name: "Evaluator", job: "Re-checks each cited row" },
  { id: "writer", name: "Writer", job: "Explains each finding" },
] as const;
const TGA_LINES = ["Supply check for each patient's medicines", "Not part of the semantic layer"] as const;

function textWidth(text: string, size: number, weight: number): number {
  if (typeof document === "undefined") return text.length * size * 0.56;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return text.length * size * 0.56;
  ctx.font = `${weight} ${size}px "Public Sans", system-ui, sans-serif`;
  return ctx.measureText(text).width;
}

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

const SKIP = new Set(["merge", "usl", "high_risk", "dq", "spellings", "dq_examples"]);
const XHTML = { xmlns: "http://www.w3.org/1999/xhtml" } as HTMLAttributes<HTMLDivElement>;

/** The short line from each source's description, shown on the card itself. */
const BLURB: Record<string, string> = {
  emr: "Charted in hospital",
  gp: "Prescribed by the GP",
  pharmacy: "Supplied, and when",
  patient: "In the patient's own words",
  lexicon: "Subsidised medicines list",
  apinchs: "Must be reviewed first",
};

export function DataMapDiagram({ catalogue, byId, lit, present = false, flow = false }: Props) {
  const reduced = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [fontTick, setFontTick] = useState(0);
  useLayoutEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const apply = () => setWidth(Math.round(el.clientWidth));
    apply();
    const watch = new ResizeObserver(apply);
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  useEffect(() => {
    let live = true;
    document.fonts.ready.then(() => {
      if (live) setFontTick((n) => n + 1);
    });
    return () => {
      live = false;
    };
  }, []);

  const sources = catalogue.filter((q) => !SKIP.has(q.node) && q.node !== "tga");
  const tgaQuery = catalogue.find((q) => q.node === "tga");
  const clinical = sources.filter((q) => q.node === "emr" || q.node === "gp" || q.node === "pharmacy" || q.node === "patient");
  const reference = sources.filter((q) => q.node === "lexicon" || q.node === "apinchs");
  const geom = width > 0 ? layoutDiagram(width, clinical.length, reference.length, fontTick) : null;

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
  const linkOn = entry("usl")?.phase === "done" && (!dimming || isLit("usl") || isLit("medtrace"));

  const ordered = [...clinical, ...reference];

  return (
    <div ref={stageRef} className={present ? "dm-stage dm-stage-present" : "dm-stage"}>
      {geom && (
        <svg
          className={`dm-svg${present ? " present" : ""}`}
          viewBox={`0 0 ${geom.width} ${geom.height}`}
          style={present ? undefined : { width: "100%", height: geom.height }}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Sources flowing through the Zetaris semantic layer into MedTrace"
        >
          <defs>
            <marker id="dm-into" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="9" markerHeight="9" orient="auto">
              <path d="M1 1.2 L11 6 L1 10.8 Z" fill="context-stroke" />
            </marker>
            <marker id="dm-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
              <path d="M0 0 L10 5 L0 10 Z" className="dm-arr" />
            </marker>
          </defs>
          {ordered.map((query, i) => {
            const inClinical = i < clinical.length;
            const listY = inClinical ? geom.clinicalY : geom.referenceY;
            const row = inClinical ? i : i - clinical.length;
            const y1 = listY + HEAD_H + row * ROW_H + ROW_H / 2;
            const y2 = geom.usl.y + 22 + ((geom.usl.h - 44) * i) / Math.max(1, ordered.length - 1);
            return (
              <Edge
                key={query.id}
                d={curve(geom.src.x + geom.src.w, y1, geom.usl.x, y2)}
                on={edgeOn(query.node)}
                faint={dimming && !isLit(query.node)}
                reduced={reduced}
                flow={flow}
              />
            );
          })}
          <rect x={geom.group.x} y={geom.group.y} width={geom.group.w} height={geom.group.h} rx={14} className="dm-trace-frame" />
          <Edge
            d={`M ${geom.agent.x} ${geom.execCy} L ${geom.usl.x + geom.usl.w} ${geom.execCy}`}
            on={linkOn}
            into
            faint={dimming && !isLit("usl") && !isLit("medtrace")}
            reduced={reduced}
            flow={flow}
          />
          <Edge
            d={`M ${geom.agent.x} ${geom.evalCy} L ${geom.usl.x + geom.usl.w} ${geom.evalCy}`}
            on={linkOn}
            into
            faint={dimming && !isLit("usl") && !isLit("medtrace")}
            reduced={reduced}
            flow={flow}
          />
          {tgaQuery && (
            <Edge
              d={`M ${geom.group.x + geom.group.w / 2} ${geom.group.y + geom.group.h} L ${geom.group.x + geom.group.w / 2} ${geom.tgaY}`}
              on={edgeOn("tga")}
              optional
              faint={dimming && !isLit("tga")}
              reduced={reduced}
              flow={flow}
            />
          )}

          <SourceList
            x={geom.src.x}
            y={geom.clinicalY}
            w={geom.src.w}
            h={geom.clinicalH}
            title="Patient records · synthetic"
            queries={clinical}
            byId={byId}
            dimming={dimming}
            isLit={isLit}
          />
          <SourceList
            x={geom.src.x}
            y={geom.referenceY}
            w={geom.src.w}
            h={geom.referenceH}
            title="Reference data · real"
            queries={reference}
            byId={byId}
            dimming={dimming}
            isLit={isLit}
          />
          <NodeBox
            x={geom.usl.x}
            y={geom.usl.y}
            w={geom.usl.w}
            h={geom.usl.h}
            label={spec("usl")?.label ?? "Zetaris · semantic layer (medtrace_usl)"}
            usl
            chips={USL_TABLES}
            caption="medicine lines · every source, one shape"
            entry={entry("usl")}
            active={dimming && isLit("usl")}
            faint={dimming && !isLit("usl")}
            nodeId="usl"
          />
          <foreignObject x={geom.group.x} y={geom.headY} width={geom.group.w} height={TRACE_HEAD} aria-hidden="true">
            <div {...XHTML} className="dm-trace-head">
              <div className="dm-trace-kicker">MedTrace</div>
              <div className="dm-trace-sub">Asks Zetaris in SQL</div>
            </div>
          </foreignObject>
          {AGENTS.slice(0, -1).map((agent, i) => (
            <line
              key={agent.id}
              x1={geom.agent.x + geom.agent.w / 2}
              y1={geom.boxY(i) + AGENT_H}
              x2={geom.agent.x + geom.agent.w / 2}
              y2={geom.boxY(i + 1)}
              className="dm-join"
              markerEnd="url(#dm-arr)"
            />
          ))}
          <path
            d={`M ${geom.agent.x + geom.agent.w} ${geom.evalCy} C ${geom.agent.x + geom.agent.w + 18} ${geom.evalCy}, ${geom.agent.x + geom.agent.w + 18} ${geom.execCy}, ${geom.agent.x + geom.agent.w} ${geom.execCy}`}
            className="dm-join"
            markerEnd="url(#dm-arr)"
          />
          <LinkLabel x1={geom.usl.x + geom.usl.w} x2={geom.agent.x} y={geom.execCy} text="SQL" />
          <LinkLabel x1={geom.usl.x + geom.usl.w} x2={geom.agent.x} y={geom.evalCy} text="re-check" />
          <RetryLabel
            x={geom.agent.x + geom.agent.w + 24}
            y={(geom.execCy + geom.evalCy) / 2}
            maxX={geom.group.x + geom.group.w - 8}
          />
          {AGENTS.map((agent, i) => (
            <AgentBox
              key={agent.id}
              x={geom.agent.x}
              y={geom.boxY(i)}
              w={geom.agent.w}
              h={AGENT_H}
              id={agent.id}
              name={agent.name}
              job={agent.job}
              faint={dimming && !isLit("medtrace")}
            />
          ))}
          {tgaQuery && (
            <NodeBox
              x={geom.group.x}
              y={geom.tgaY}
              w={geom.group.w}
              h={geom.tgaH}
              label={tgaQuery.label}
              optional
              lines={TGA_LINES}
              entry={byId[tgaQuery.id]}
              active={dimming && isLit("tga")}
              faint={dimming && !isLit("tga")}
              nodeId="tga"
            />
          )}
        </svg>
      )}
    </div>
  );
}

function layoutDiagram(width: number, clinicalCount: number, referenceCount: number, _fontTick: number) {
  void _fontTick;
  const longestJob = AGENTS.map((agent) => agent.job).reduce((a, b) => (textWidth(b, DESC_PX, 400) > textWidth(a, DESC_PX, 400) ? b : a));
  const agentInner = Math.ceil(textWidth(longestJob, DESC_PX, 400)) + 28;
  const retryLabel = Math.ceil(textWidth("retry", LABEL_PX, 400));
  const retryReserve = 18 + 6 + retryLabel + 10;
  const groupMin = GROUP_PAD + agentInner + retryReserve;
  const uslCaption = textWidth("medicine lines · every source, one shape", DESC_PX, 400);
  const uslTitle = textWidth("Zetaris · semantic layer (medtrace_usl)", NAME_PX, 600);
  const tgaLine = textWidth(TGA_LINES[0], DESC_PX, 400);
  const sourceLine = Math.max(
    ...Object.values(BLURB).map((line) => textWidth(line, DESC_PX, 400)),
    textWidth("High-risk classes (ACSQHC)", NAME_PX, 600),
    textWidth("Patient interview", NAME_PX, 600),
  );
  const countW = textWidth("00,000", 15, 600);
  const srcNeed = 32 + 14 + 8 + Math.ceil(sourceLine) + 8 + Math.ceil(countW);
  const grpNeed = Math.max(groupMin, Math.ceil(tgaLine) + 36);
  const uslNeed = Math.ceil(Math.max(uslCaption, uslTitle)) + 68;
  const gap2Floor = Math.max(56, Math.ceil(textWidth("re-check", LABEL_PX, 400)) + 16);

  const col = {
    src: Math.max(width * 0.32, srcNeed),
    gap1: 48,
    usl: Math.max(width * 0.26, uslNeed),
    gap2: 72,
    grp: Math.max(width * 0.26, grpNeed),
  };
  const textFloor = { src: srcNeed, gap1: 12, usl: uslNeed, gap2: gap2Floor, grp: grpNeed };
  const share = { src: width * 0.32, usl: width * 0.26, grp: width * 0.26 };
  const overflow = () => col.src + col.gap1 + col.usl + col.gap2 + col.grp + 32 - width;
  // Columns may sit above their share so a line fits. Give that extra back
  // before touching the 48px and 72px gaps.
  for (const key of ["src", "grp", "usl"] as const) {
    const over = overflow();
    if (over <= 0) break;
    const spare = col[key] - textFloor[key];
    if (spare > 0) col[key] -= Math.min(spare, over);
  }
  for (const key of ["gap1", "gap2"] as const) {
    const over = overflow();
    if (over <= 0) break;
    const spare = col[key] - textFloor[key];
    if (spare > 0) col[key] -= Math.min(spare, over);
  }
  let extra = -overflow();
  if (extra > 0) {
    for (const key of ["src", "usl", "grp"] as const) {
      const room = Math.max(0, share[key] - col[key]);
      const add = Math.min(extra, room);
      col[key] += add;
      extra -= add;
    }
  }

  const srcX = 0;
  const uslX = col.src + col.gap1;
  const groupX = uslX + col.usl + col.gap2;
  const clinicalH = HEAD_H + clinicalCount * ROW_H;
  const referenceH = HEAD_H + referenceCount * ROW_H;
  const clinicalY = 0;
  const referenceY = clinicalH + LIST_GAP;
  const leftH = referenceY + referenceH;
  const contentH = 48 + 20 + USL_COUNT_PX + 18 + 18 + 3 * 22;
  const groupH = GROUP_PAD * 2 + 4 * AGENT_H + 3 * AGENT_GAP;
  const execTop = GROUP_PAD + AGENT_H + AGENT_GAP;
  const evalBottom = GROUP_PAD + 2 * (AGENT_H + AGENT_GAP) + AGENT_H;
  const span = evalBottom - execTop;
  let uslH = Math.max(contentH, span + 16);
  let uslY = Math.max(0, (leftH - uslH) / 2);
  const spanMid = (execTop + evalBottom) / 2;
  let groupY = uslY + uslH / 2 - spanMid;
  if (groupY < TRACE_HEAD + 4) {
    const shift = TRACE_HEAD + 4 - groupY;
    groupY += shift;
    uslY += shift;
  }
  if (groupY + execTop < uslY) {
    uslH += uslY - (groupY + execTop);
    uslY = groupY + execTop;
  }
  if (groupY + evalBottom > uslY + uslH) uslH = groupY + evalBottom - uslY;

  const tgaH = 84;
  const tgaY = groupY + groupH + 28;
  const agentX = groupX + GROUP_PAD;
  const agentW = Math.max(40, groupX + col.grp - retryReserveOf(retryLabel) - agentX);

  return {
    width,
    height: Math.max(leftH, tgaY + tgaH) + 4,
    src: { x: srcX, w: col.src },
    usl: { x: uslX, y: uslY, w: col.usl, h: uslH },
    group: { x: groupX, y: groupY, w: col.grp, h: groupH },
    agent: { x: agentX, w: agentW },
    clinicalY,
    clinicalH,
    referenceY,
    referenceH,
    boxY: (i: number) => groupY + GROUP_PAD + i * (AGENT_H + AGENT_GAP),
    execCy: groupY + execTop + AGENT_H / 2,
    evalCy: groupY + GROUP_PAD + 2 * (AGENT_H + AGENT_GAP) + AGENT_H / 2,
    tgaY,
    tgaH,
    headY: groupY - TRACE_HEAD,
  };
}

function retryReserveOf(labelWidth: number): number {
  return 18 + 6 + labelWidth + 10;
}

function LinkLabel({ x1, x2, y, text }: { x1: number; x2: number; y: number; text: string }) {
  const width = Math.ceil(textWidth(text, LABEL_PX, 400)) + 2;
  const mid = (x1 + x2) / 2;
  const left = Math.min(x2 - 2, Math.max(x1 + 2, mid - width / 2));
  const height = 14;
  return (
    <foreignObject x={left} y={y - 5 - height} width={Math.min(width, Math.abs(x2 - x1) - 4)} height={height}>
      <div {...XHTML} className="dm-link-label">
        {text}
      </div>
    </foreignObject>
  );
}

function RetryLabel({ x, y, maxX }: { x: number; y: number; maxX: number }) {
  const width = Math.min(Math.ceil(textWidth("retry", LABEL_PX, 400)) + 2, Math.max(20, maxX - x));
  return (
    <foreignObject x={x} y={y - 8} width={width} height={16}>
      <div {...XHTML} className="dm-link-label">
        retry
      </div>
    </foreignObject>
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
}) {
  return (
    <foreignObject x={x} y={y} width={w} height={h}>
      <div {...XHTML} className="dm-list" style={{ width: w, height: h }}>
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
              className={`dm-list-row${dimming && !isLit(query.node) ? " dm-faint" : ""}`}
              data-node={query.node}
              role="group"
              aria-label={`${query.label}. ${BLURB[query.node] ?? ""}`}
            >
              <span className={`dm-dot-status${phase === "done" ? " done" : ""}${waiting ? " run" : ""}${failed ? " bad" : ""}`} />
              <div className="dm-name">{query.label}</div>
              <div className="dm-count dm-num">{count != null ? formatCount(count) : ""}</div>
              <div className="dm-blurb">{failed ? entry?.error ?? "The query failed" : waiting ? "querying Zetaris…" : BLURB[query.node]}</div>
            </div>
          );
        })}
      </div>
    </foreignObject>
  );
}

function Edge({
  d,
  on,
  optional = false,
  into = false,
  faint,
  reduced,
  flow,
}: {
  d: string;
  on: boolean;
  optional?: boolean;
  into?: boolean;
  faint: boolean;
  reduced: boolean;
  flow: boolean;
}) {
  return (
    <g className={faint ? "dm-faint" : undefined} aria-hidden>
      <path
        d={d}
        className={`dm-edge${into ? " dm-edge-into" : ""}${on ? " dm-edge-on" : ""}${optional ? " dm-edge-opt" : ""}`}
        markerEnd={into ? "url(#dm-into)" : undefined}
        pathLength={optional || into ? undefined : 1}
      />
      {on && flow && !reduced && !into && (
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
  lines,
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
  lines?: readonly string[];
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
          style={{ width: w, height: h }}
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
          {lines && !detail && lines.map((line) => (
            <div key={line} className="dm-blurb">{line}</div>
          ))}
          {usl && caption && <div className="dm-cap">{caption}</div>}
          {chips && (
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
        <div {...XHTML} className="dm-node-body panel dm-src dm-agent" style={{ width: w, height: h }} aria-label={`${name}. ${job}`}>
          <div className="dm-agent-name">{name}</div>
          <div className="dm-agent-job">{job}</div>
        </div>
      </foreignObject>
    </g>
  );
}
