// One diagram of sources → the Zetaris semantic layer → MedTrace.
// The data map and the presenter view both render this. Positions are layout,
// not counts: a number appears only after that node's query has answered.

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type HTMLAttributes, type MouseEvent as ReactMouseEvent } from "react";
import { NodeDetail } from "./DataMapDetail";
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
const SRC_W = 420;
const SRC_H = 64;
const SRC_GAP = 8;
const LABEL_H = 16;
const USL_W = 440;
const USL_H = 248;
const TRACE_W = 340;
const TRACE_H = 200;
const COL_GAP = (VB_W - PAD * 2 - SRC_W - USL_W - TRACE_W) / 2;
const SRC_X = PAD;
const USL_X = SRC_X + SRC_W + COL_GAP;
const TRACE_X = USL_X + USL_W + COL_GAP;
const BUS_X = SRC_X + SRC_W + COL_GAP / 2;
const USL_TABLES = ["medicine", "high_risk_class", "medication_statement"] as const;
const PIPE = ["Planner", "Executor", "Evaluator", "Writer"] as const;

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
  /** Presenter: this node's card stays open beside the diagram. */
  forcedNode?: string;
  showQuality?: boolean;
}

const SKIP = new Set(["merge", "usl", "high_risk", "dq"]);
const XHTML = { xmlns: "http://www.w3.org/1999/xhtml" } as HTMLAttributes<HTMLDivElement>;
const XHTML_BTN = { xmlns: "http://www.w3.org/1999/xhtml" } as ButtonHTMLAttributes<HTMLButtonElement>;

const OpenCtx = createContext<{
  openId: string | null;
  enter: (id: string) => void;
  leave: (event: ReactMouseEvent) => void;
  focus: (id: string) => void;
  blur: () => void;
  toggle: (id: string) => void;
} | null>(null);

export function DataMapDiagram({ catalogue, byId, lit, present = false, flow = false, forcedNode, showQuality = false }: Props) {
  const reduced = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [suppressed, setSuppressed] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; width: number; maxH: number } | null>(null);
  const openId = present ? forcedNode ?? null : suppressed ? null : focusId ?? pinned ?? hover;
  const sources = catalogue.filter((q) => !SKIP.has(q.node));
  const srcH = SRC_H;
  const srcW = SRC_W;
  const siloIdxEarly = sources.findIndex((q) => q.node === "patient");
  const lastSiloEarly = siloIdxEarly >= 0 ? siloIdxEarly : Math.min(3, sources.length - 1);
  const tgaEarly = sources.findIndex((q) => q.node === "tga");
  const yOf = (i: number) => {
    let y = PAD + LABEL_H + i * (srcH + SRC_GAP);
    if (i > lastSiloEarly) y += LABEL_H;
    if (tgaEarly >= 0 && i >= tgaEarly) y += PAD;
    return y;
  };
  const cyOf = (i: number) => yOf(i) + srcH / 2;
  const columnTop = sources.length ? yOf(0) : PAD;
  const columnBottom = sources.length ? yOf(sources.length - 1) + srcH : 200;
  const columnMid = (columnTop + columnBottom) / 2;
  const uslBox = { x: USL_X, y: Math.max(PAD, columnMid - USL_H / 2), w: USL_W, h: USL_H };
  const traceBox = {
    x: TRACE_X,
    y: uslBox.y + (uslBox.h - TRACE_H) / 2,
    w: TRACE_W,
    h: TRACE_H,
  };
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

  const siloIdx = sources.findIndex((q) => q.node === "patient");
  const lastSilo = siloIdx >= 0 ? siloIdx : Math.min(3, sources.length - 1);
  const mergeY = sources.length ? (cyOf(0) + cyOf(Math.max(lastSilo, 0))) / 2 : uslBox.y + uslBox.h / 2;
  const uslCy = uslBox.y + uslBox.h / 2;
  const lexiconI = sources.findIndex((q) => q.node === "lexicon");
  const apinchsI = sources.findIndex((q) => q.node === "apinchs");
  const tgaI = sources.findIndex((q) => q.node === "tga");
  // Top to bottom on the semantic layer's left edge, matching source order, so the lines do not cross.
  const entryPad = 28;
  const entryY = (i: number) => uslBox.y + entryPad + ((uslBox.h - entryPad * 2) * i) / 2;
  const mergeEntryY = entryY(0);
  const lexiconEntryY = entryY(1);
  const apinchsEntryY = entryY(2);
  const mergeEntry = entry("merge");
  const mergeOn = mergeEntry?.phase === "error" ? false : dimming ? isLit("merge") : mergeEntry?.phase === "done";
  const trunk = curve(BUS_X, mergeY, uslBox.x, mergeEntryY);
  const toTrace = curve(uslBox.x + uslBox.w, uslCy, traceBox.x, traceBox.y + traceBox.h / 2);
  const traceOn = entry("usl")?.phase === "done" && (!dimming || isLit("medtrace"));
  const yUnder = Math.max(
    tgaI >= 0 ? cyOf(tgaI) + 36 : 0,
    uslBox.y + uslBox.h + 28,
    traceBox.y + traceBox.h + 24,
  );
  const tgaPath =
    tgaI >= 0
      ? `M ${SRC_X + srcW} ${cyOf(tgaI)} C ${SRC_X + srcW + 56} ${yUnder}, ${traceBox.x + traceBox.w / 2} ${yUnder}, ${traceBox.x + traceBox.w / 2} ${traceBox.y + traceBox.h}`
      : "";
  const vbH = Math.max(columnBottom, uslBox.y + uslBox.h + 24, traceBox.y + traceBox.h + 24, yUnder + 12);

  useEffect(() => {
    if (present) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setPinned(null);
      setSuppressed(true);
    };
    const onDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".dm-node-btn") || target.closest(".dm-detail")) return;
      setPinned(null);
      setSuppressed(true);
    };
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const btn = target.closest(".dm-node-btn");
      if (!btn || !stageRef.current?.contains(btn)) return;
      const id = btn.closest("[data-node]")?.getAttribute("data-node");
      if (!id) return;
      setSuppressed(false);
      setFocusId(id);
    };
    const onFocusOut = (event: FocusEvent) => {
      const next = event.relatedTarget;
      if (next instanceof Element && next.closest(".dm-node-btn")) return;
      setFocusId(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("focusout", onFocusOut, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("focusout", onFocusOut, true);
    };
  }, [present]);

  useLayoutEffect(() => {
    if (present || !openId || !stageRef.current || !cardRef.current) {
      setPos(null);
      return;
    }
    const node = stageRef.current.querySelector(`[data-node="${openId}"]`);
    if (!node) return;
    const box = stageRef.current.getBoundingClientRect();
    const nr = node.getBoundingClientRect();
    const gap = 8;
    const roomRight = box.width - (nr.right - box.left) - gap * 2;
    const roomLeft = nr.left - box.left - gap * 2;
    const right = roomRight >= roomLeft;
    const width = Math.max(160, Math.min(360, right ? roomRight : roomLeft));
    let left = right ? nr.right - box.left + gap : nr.left - box.left - width - gap;
    left = Math.max(gap, Math.min(left, box.width - width - gap));
    const cr = cardRef.current.getBoundingClientRect();
    let top = nr.top - box.top;
    if (top + cr.height > box.height - gap) top = box.height - cr.height - gap;
    top = Math.max(gap, top);
    const maxH = Math.max(120, Math.round(box.height - gap * 2));
    const next = { left: Math.round(left), top: Math.round(top), width: Math.round(width), maxH };
    setPos((prev) =>
      prev && prev.left === next.left && prev.top === next.top && prev.width === next.width && prev.maxH === next.maxH ? prev : next,
    );
  }, [present, openId, byId, pos?.width, pos?.maxH]);

  const ui = {
    openId,
    enter: (id: string) => {
      if (present) return;
      setSuppressed(false);
      setHover(id);
    },
    leave: (event: ReactMouseEvent) => {
      const next = event.relatedTarget;
      if (next instanceof Element && (next.closest(".dm-detail") || next.closest(".dm-node-btn"))) return;
      setHover(null);
      setSuppressed(false);
    },
    focus: (id: string) => {
      if (present) return;
      setSuppressed(false);
      setFocusId(id);
    },
    blur: () => setFocusId(null),
    toggle: (id: string) => {
      if (present) return;
      const closing = pinned === id;
      setSuppressed(closing);
      setPinned(closing ? null : id);
    },
  };

  const detail = openId ? (
    <div
      ref={cardRef}
      className={present ? "dm-detail-present-wrap" : "dm-detail-slot"}
      style={present ? undefined : { left: pos?.left ?? 8, top: pos?.top ?? 8, width: pos?.width ?? 360, maxHeight: pos?.maxH, visibility: pos ? "visible" : "hidden" }}
      onMouseEnter={() => openId && ui.enter(openId)}
    >
      <NodeDetail nodeId={openId} entry={entry(openId)} showQuality={showQuality} quality={showQuality ? byId.dq : undefined} present={present} />
    </div>
  ) : null;

  return (
    <OpenCtx.Provider value={ui}>
    <div ref={stageRef} className={present ? "dm-stage dm-stage-present" : "dm-stage"} onMouseLeave={ui.leave}>
    <svg
      className={`dm-svg${present ? " present" : ""}`}
      viewBox={`0 0 ${VB_W} ${vbH}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Sources flowing through the Zetaris semantic layer into MedTrace"
    >
      {sources.slice(0, lastSilo + 1).map((query, i) => (
        <Edge
          key={query.id}
          d={curve(SRC_X + srcW, cyOf(i), BUS_X, mergeY)}
          on={edgeOn(query.node)}
          faint={dimming && !isLit(query.node)}
          reduced={reduced}
          flow={flow}
        />
      ))}
      <Edge d={trunk} on={mergeOn} faint={dimming && !isLit("merge")} reduced={reduced} flow={flow} />
      {lexiconI >= 0 && (
        <Edge
          d={curve(SRC_X + srcW, cyOf(lexiconI), uslBox.x, lexiconEntryY)}
          on={edgeOn("lexicon")}
          faint={dimming && !isLit("lexicon")}
          reduced={reduced}
          flow={flow}
        />
      )}
      {apinchsI >= 0 && (
        <Edge
          d={curve(SRC_X + srcW, cyOf(apinchsI), uslBox.x, apinchsEntryY)}
          on={edgeOn("apinchs")}
          faint={dimming && !isLit("apinchs")}
          reduced={reduced}
          flow={flow}
        />
      )}
      {tgaPath && (
        <Edge d={tgaPath} on={edgeOn("tga")} optional faint={dimming && !isLit("tga")} reduced={reduced} flow={flow} />
      )}
      <Edge d={toTrace} on={traceOn} faint={dimming && !isLit("medtrace")} reduced={reduced} flow={flow} />

      <GroupLabel x={SRC_X} y={yOf(0) - 20} w={srcW} text="Clinical records · synthetic" />
      {lexiconI >= 0 && <GroupLabel x={SRC_X} y={yOf(lexiconI) - 20} w={srcW} text="Australian reference data · real" />}

      {sources.map((query, i) => (
        <NodeBox
          key={query.id}
          x={SRC_X}
          y={yOf(i)}
          w={srcW}
          h={srcH}
          label={query.label}
          optional={query.node === "tga"}
          entry={byId[query.id]}
          active={dimming && isLit(query.node)}
          faint={dimming && !isLit(query.node)}
          nodeId={query.node}
        />
      ))}

      <MergeLabel x={BUS_X + 8} y={mergeY - 36} entry={mergeEntry} faint={dimming && !isLit("merge")} />

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
      <NodeBox
        x={traceBox.x}
        y={traceBox.y}
        w={traceBox.w}
        h={traceBox.h}
        label="MedTrace"
        pipe
        entry={entry("usl")?.phase === "done" ? { id: "medtrace", label: "MedTrace", node: "medtrace", phase: "done" } : undefined}
        active={dimming && isLit("medtrace")}
        faint={dimming && !isLit("medtrace")}
        noCount
        nodeId="medtrace"
      />
    </svg>
    {detail}
    </div>
    </OpenCtx.Provider>
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
  pipe = false,
  active,
  faint,
  noCount = false,
  nodeId,
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
  pipe?: boolean;
  active: boolean;
  faint: boolean;
  noCount?: boolean;
  nodeId: string;
}) {
  const ui = useContext(OpenCtx);
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
        shown ? `${formatCount(shown) ?? shown} rows in Zetaris` : "",
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
        <button
          {...XHTML_BTN}
          type="button"
          className={`dm-node-btn dm-node-body ${state}${usl ? " dm-usl-body" : " panel dm-src"}${optional ? " dm-opt" : ""}${phase === "done" && !usl && !pipe ? " dm-arrived" : ""}`}
          aria-label={aria}
          aria-expanded={ui?.openId === nodeId}
          aria-controls={ui?.openId === nodeId ? `dm-detail-${nodeId}` : undefined}
          onMouseEnter={() => ui?.enter(nodeId)}
          onMouseLeave={ui?.leave}
          onFocus={() => ui?.focus(nodeId)}
          onBlur={() => ui?.blur()}
          onClick={() => ui?.toggle(nodeId)}
        >
          <div className={usl || pipe ? undefined : "dm-src-line"}>
            <div className="dm-name">
              {phase === "running" && <span className="pn-dot" />}
              {label}
            </div>
            {!usl && !pipe && shown && <div className="dm-count dm-num">{formatCount(shown)}</div>}
          </div>
          {!usl && !pipe && waiting && <div className="dm-wait">{waiting}</div>}
          {(usl || pipe) && waiting && <div className="dm-wait">{waiting}</div>}
          {detail && (
            <div className="dm-err" title={detail}>
              {detail}
            </div>
          )}
          {(usl || pipe) && shown && <div className="dm-count dm-num">{formatCount(shown)}</div>}
          {shown && <div className="dm-cap">{caption ?? "rows in Zetaris"}</div>}
          {shown && optional && <div className="dm-cap">optional overlay</div>}
          {shown && chips && (
            <div className="dm-chips">
              {chips.map((name) => (
                <span key={name} className="dm-chip">
                  {name}
                </span>
              ))}
            </div>
          )}
          {pipe && (
            <ol className="dm-pipe">
              {PIPE.map((name) => (
                <li key={name} className="pn pn-used dm-pipe-step">
                  <span className="pn-dot" aria-hidden />
                  <span className="pn-label">{name}</span>
                </li>
              ))}
            </ol>
          )}
        </button>
      </foreignObject>
    </g>
  );
}

function GroupLabel({ x, y, w, text }: { x: number; y: number; w: number; text: string }) {
  return (
    <foreignObject x={x} y={y} width={w} height={20} aria-hidden="true">
      <div {...XHTML} className="dm-group">
        {text}
      </div>
    </foreignObject>
  );
}

function MergeLabel({ x, y, entry, faint }: { x: number; y: number; entry?: LogEntry; faint: boolean }) {
  const count = entry?.phase === "done" ? soleCell(entry.result) : null;
  const text =
    entry?.phase === "running" ? "querying Zetaris…" : count ? `4 systems → ${formatCount(count)} medicine lines` : "";
  if (!text) return null;
  return (
    <foreignObject x={x} y={y} width={168} height={52} className={faint ? "dm-faint" : undefined}>
      <div {...XHTML} className="dm-merge" role="img" aria-label={text}>
        {text}
      </div>
    </foreignObject>
  );
}
