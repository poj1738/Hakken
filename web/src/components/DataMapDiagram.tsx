// One diagram of sources → the Zetaris semantic layer → MedTrace.
// The data map and the presenter view both render this. Positions are layout,
// not counts: a number appears only after that node's query has answered.

import { useCallback, useEffect, useRef, useState, type HTMLAttributes } from "react";
import { api } from "../api";
import type { DataMapQueryResult, DataMapQuerySpec } from "../types";

export interface LogEntry {
  id: string;
  label: string;
  node: string;
  phase: "running" | "done" | "error";
  result?: DataMapQueryResult;
  error?: string;
}

export function soleCell(result: DataMapQueryResult | undefined): string | null {
  const value = result?.data[0]?.[0];
  if (value == null || value === "") return null;
  return String(value);
}

/** Rows column: a single count's cell, otherwise how many rows came back. */
export function rowsShown(result: DataMapQueryResult): string {
  if (result.data.length === 1 && result.headers.length === 1) {
    const cell = soleCell(result);
    if (cell != null) return cell;
  }
  return String(result.row_count);
}

export function useDataMapRun(enabled: boolean) {
  const [catalogue, setCatalogue] = useState<DataMapQuerySpec[] | null>(null);
  const [byId, setById] = useState<Record<string, LogEntry>>({});
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const gen = useRef(0);

  const rerun = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    const token = ++gen.current;
    const ctrl = new AbortController();
    const alive = () => token === gen.current && !ctrl.signal.aborted;
    setCatalogue(null);
    setById({});
    setEntries([]);
    setFatal(null);

    (async () => {
      try {
        const cat = await api.dataMapQueries(ctrl.signal);
        if (!alive()) return;
        setCatalogue(cat.queries);
        for (const query of cat.queries) {
          if (!alive()) return;
          const running: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "running" };
          setById((m) => ({ ...m, [query.id]: running }));
          setEntries((es) => [...es.filter((e) => e.id !== query.id), running]);
          try {
            const result = await api.dataMapQuery(query.id, ctrl.signal);
            if (!alive()) return;
            const done: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "done", result };
            setById((m) => ({ ...m, [query.id]: done }));
            setEntries((es) => es.map((e) => (e.id === query.id ? done : e)));
          } catch (err) {
            if (!alive() || (err instanceof DOMException && err.name === "AbortError")) return;
            const message = err instanceof Error ? err.message : String(err);
            const failed: LogEntry = { id: query.id, label: query.label, node: query.node, phase: "error", error: message };
            setById((m) => ({ ...m, [query.id]: failed }));
            setEntries((es) => es.map((e) => (e.id === query.id ? failed : e)));
          }
        }
      } catch (err) {
        if (!alive() || (err instanceof DOMException && err.name === "AbortError")) return;
        setFatal(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => ctrl.abort();
  }, [enabled, nonce]);

  return { catalogue, byId, entries, fatal, rerun };
}

const SRC_X = 12;
const SRC_W = 210;
const SRC_H = 72;
const SRC_GAP = 8;
const SRC_TOP = 8;
const VB_W = 960;

const USL = { x: 470, y: 168, w: 250, h: 156 };
const TRACE = { x: 768, y: 196, w: 176, h: 104 };
const BUS_X = SRC_X + SRC_W + 52;

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
}

const SKIP = new Set(["merge", "usl", "high_risk", "dq"]);
const XHTML = { xmlns: "http://www.w3.org/1999/xhtml" } as HTMLAttributes<HTMLDivElement>;

export function DataMapDiagram({ catalogue, byId, lit, present = false }: Props) {
  const reduced = useReducedMotion();
  const sources = catalogue.filter((q) => !SKIP.has(q.node));
  // Presenter type is larger, so the boxes grow with it. The data map keeps the compact size.
  const srcH = present ? 128 : SRC_H;
  const srcGap = present ? 6 : SRC_GAP;
  const srcW = present ? 228 : SRC_W;
  const yOf = (i: number) => SRC_TOP + i * (srcH + srcGap);
  const cyOf = (i: number) => yOf(i) + srcH / 2;
  const columnBottom = sources.length ? yOf(sources.length - 1) + srcH + 16 : 200;
  const columnMid = sources.length ? (cyOf(0) + cyOf(sources.length - 1)) / 2 : USL.y + USL.h / 2;
  const uslBox = present ? { x: 488, y: Math.max(12, columnMid - 96), w: 268, h: 192 } : USL;
  const traceBox = present
    ? { x: uslBox.x + uslBox.w + 24, y: uslBox.y + 44, w: 168, h: 104 }
    : TRACE;
  const vbH = Math.max(columnBottom, uslBox.y + uslBox.h + 24, traceBox.y + traceBox.h + 24);
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
  const mergeEntry = entry("merge");
  const mergeOn = mergeEntry?.phase === "error" ? false : dimming ? isLit("merge") : mergeEntry?.phase === "done";
  const trunk = curve(BUS_X, mergeY, uslBox.x, uslCy);
  const toTrace = curve(uslBox.x + uslBox.w, uslCy, traceBox.x, traceBox.y + traceBox.h / 2);
  const traceOn = entry("usl")?.phase === "done" && (!dimming || isLit("medtrace"));

  return (
    <svg
      className={`dm-svg${present ? " present" : ""}`}
      viewBox={`0 0 ${VB_W} ${vbH}`}
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
        />
      ))}
      <Edge d={trunk} on={mergeOn} faint={dimming && !isLit("merge")} reduced={reduced} />
      {sources.slice(lastSilo + 1).map((query) => {
        const i = sources.indexOf(query);
        const slot = i - lastSilo;
        const y2 = uslBox.y + uslBox.h - 36 - slot * 22;
        return (
          <Edge
            key={query.id}
            d={curve(SRC_X + srcW, cyOf(i), uslBox.x, Math.min(uslBox.y + uslBox.h - 18, Math.max(uslBox.y + 18, y2)))}
            on={edgeOn(query.node)}
            optional={query.node === "tga"}
            faint={dimming && !isLit(query.node)}
            reduced={reduced}
          />
        );
      })}
      <Edge d={toTrace} on={traceOn} faint={dimming && !isLit("medtrace")} reduced={reduced} />

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
        entry={entry("usl")}
        active={dimming && isLit("usl")}
        faint={dimming && !isLit("usl")}
      />
      <NodeBox
        x={traceBox.x}
        y={traceBox.y}
        w={traceBox.w}
        h={traceBox.h}
        label="MedTrace"
        caption="Reads the semantic layer by SQL"
        entry={entry("usl")?.phase === "done" ? { id: "medtrace", label: "MedTrace", node: "medtrace", phase: "done" } : undefined}
        active={dimming && isLit("medtrace")}
        faint={dimming && !isLit("medtrace")}
        noCount
      />
    </svg>
  );
}

function Edge({
  d,
  on,
  optional = false,
  faint,
  reduced,
}: {
  d: string;
  on: boolean;
  optional?: boolean;
  faint: boolean;
  reduced: boolean;
}) {
  const end = /([\d.]+)\s+([\d.]+)\s*$/.exec(d);
  const x2 = end ? Number(end[1]) : 0;
  const y2 = end ? Number(end[2]) : 0;
  return (
    <g className={faint ? "dm-faint" : undefined} aria-hidden>
      <path d={d} className={`dm-edge${on ? " dm-edge-on" : ""}${optional ? " dm-edge-opt" : ""}`} pathLength={optional ? undefined : 1} />
      {on && reduced && <circle cx={x2} cy={y2} r="4" className="dm-dot" />}
      {on && !reduced && (
        <circle r="4" className="dm-dot">
          <animateMotion dur="0.6s" fill="freeze" path={d} />
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
  active,
  faint,
  noCount = false,
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
  active: boolean;
  faint: boolean;
  noCount?: boolean;
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
        shown ? `${shown} rows in Zetaris` : "",
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
    <g className={cls} tabIndex={0} role="img" aria-label={aria}>
      <rect x={x} y={y} width={w} height={h} rx={12} className={`dm-box${optional ? " dm-box-opt" : ""}${usl ? " dm-box-usl" : ""}`} />
      <foreignObject x={x} y={y} width={w} height={h} aria-hidden="true">
        <div {...XHTML} className={`dm-node-body ${state}${usl ? " dm-usl-body" : ""}`}>
          <div className="dm-name">
            {phase === "running" && <span className="pn-dot" />}
            {label}
          </div>
          {optional && <div className="dm-cap">optional overlay</div>}
          {waiting && <div className="dm-wait">{waiting}</div>}
          {detail && (
            <div className="dm-err" title={detail}>
              {detail}
            </div>
          )}
          {shown && <div className="dm-count dm-num">{shown}</div>}
          {shown && <div className="dm-cap">{caption ?? "rows in Zetaris"}</div>}
          {noCount && caption && <div className="dm-cap">{caption}</div>}
        </div>
      </foreignObject>
    </g>
  );
}

function MergeLabel({ x, y, entry, faint }: { x: number; y: number; entry?: LogEntry; faint: boolean }) {
  const count = entry?.phase === "done" ? soleCell(entry.result) : null;
  const text =
    entry?.phase === "running" ? "querying Zetaris…" : count ? `4 systems combined: ${count} rows` : "";
  if (!text) return null;
  return (
    <foreignObject x={x} y={y} width={168} height={52} className={faint ? "dm-faint" : undefined}>
      <div {...XHTML} className="dm-merge" role="img" aria-label={text}>
        {text}
      </div>
    </foreignObject>
  );
}
