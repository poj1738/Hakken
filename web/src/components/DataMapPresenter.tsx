// Presenter view of the same diagram, for a window beside the Zetaris SQL editor.
// It runs the same catalogue, in the same order, and shows a number only after
// that step's own response has arrived.

import { useEffect, useState, type ReactNode } from "react";
import { API_MODE } from "../api";
import { DISCLAIMER } from "./Footer";
import { DataMapDiagram, RunStatus, formatCount, soleCell, useDataMapRun, type LogEntry } from "./DataMapDiagram";

const STEPS: { queryId: string; title: string; line: string; lit: readonly string[] }[] = [
  { queryId: "emr", title: "Hospital EMR", line: "What was charted in hospital. Synthetic.", lit: ["emr"] },
  { queryId: "gp", title: "GP", line: "What the GP prescribed. Synthetic.", lit: ["gp"] },
  { queryId: "pharmacy", title: "Pharmacy", line: "What was actually dispensed. Synthetic.", lit: ["pharmacy"] },
  {
    queryId: "patient",
    title: "Patient interview",
    line: "What the patient says they take, in their own words. Synthetic.",
    lit: ["patient"],
  },
  {
    queryId: "lexicon",
    title: "PBS medicines",
    line: "Real Australian medicine codes, strengths and pack sizes.",
    lit: ["lexicon"],
  },
  {
    queryId: "apinchs",
    title: "High-risk classes (ACSQHC)",
    line: "The national list of high-risk medicine classes.",
    lit: ["apinchs"],
  },
  {
    queryId: "tga",
    title: "TGA shortages",
    line: "Optional overlay: real current and anticipated shortages.",
    lit: ["tga"],
  },
  {
    queryId: "rows",
    title: "Zetaris · semantic layer",
    line: "Six sources, one view of every medicine line. (TGA stays a separate overlay.)",
    lit: ["emr", "gp", "pharmacy", "patient", "lexicon", "apinchs", "usl", "merge"],
  },
  {
    queryId: "dq",
    title: "What Zetaris found",
    line: "Three checks over the semantic layer, each one its own live query.",
    lit: [],
  },
];

export function DataMapPresenter({ onExit }: { onExit: () => void }) {
  if (API_MODE !== "live") {
    return (
      <div className="dm-present">
        <p>The Data map needs the API (live or SAMPLE_MODE).</p>
        <button type="button" className="lnk" onClick={onExit}>
          Exit presenter view
        </button>
      </div>
    );
  }
  return <PresenterLive onExit={onExit} />;
}

function PresenterLive({ onExit }: { onExit: () => void }) {
  const { catalogue, byId, rerun, clock } = useDataMapRun(true);
  const [step, setStep] = useState(0);
  const current = STEPS[step] ?? STEPS[0];
  const last = STEPS.length - 1;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setStep((n) => Math.min(last, n + 1));
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setStep((n) => Math.max(0, n - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [last]);

  const entry = byId[current.queryId];
  const spoken = speak(entry, current.queryId === "tga");
  const dq = current.queryId === "dq";

  return (
    <div className="dm-present">
      <header className="dm-present-head">
        <p className="dm-kicker">
          Step {step + 1} of {STEPS.length}
        </p>
        <h1 className="dm-title">{current.title}</h1>
        <p className="dm-sub">{current.line}</p>
        <RunStatus clock={clock} onRerun={rerun} />
        {dq && <Findings byId={byId} />}
        <p className="dm-live" aria-live="polite">
          {current.title}. {dq ? findingsSpoken(byId) : spoken || "Waiting for its query."} {dq ? "" : current.line}
        </p>
      </header>
      <div className="dm-diagram dm-diagram-present">
        {catalogue ? (
          <DataMapDiagram
            catalogue={catalogue}
            byId={byId}
            lit={current.lit}
            present
            flow={clock.phase === "done" || clock.phase === "cached"}
          />
        ) : (
          <p className="dm-wait">querying Zetaris…</p>
        )}
      </div>
      <footer className="dm-present-foot">
        <button type="button" className="btn btn-line" aria-label="Previous step" onClick={() => setStep((n) => Math.max(0, n - 1))} disabled={step === 0}>
          Previous
        </button>
        <button type="button" className="btn btn-line" aria-label="Next step" onClick={() => setStep((n) => Math.min(last, n + 1))} disabled={step === last}>
          Next
        </button>
        <button type="button" className="lnk" onClick={onExit}>
          Exit presenter view
        </button>
        <p className="dm-cap dm-disclaimer">{DISCLAIMER}</p>
      </footer>
    </div>
  );
}

function speak(entry: LogEntry | undefined, tga: boolean): string {
  if (!entry) return "";
  if (entry.phase === "running") return "Querying Zetaris.";
  if (entry.phase === "error") return tga ? "Not registered." : "The query failed.";
  const count = formatCount(soleCell(entry.result));
  return count ? `${count} rows.` : "";
}

const SHORT: Record<string, string> = { emr: "EMR", gp: "GP", pharmacy: "Pharmacy", patient: "Patient" };

/** A finished query's rows, or why there are none yet. */
function pending(entry: LogEntry | undefined): ReactNode | null {
  if (!entry || entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  if (!entry.result) return <p className="dm-wait">querying Zetaris…</p>;
  return null;
}

function riskTotal(entry: LogEntry | undefined): number | null {
  if (entry?.phase !== "done" || !entry.result) return null;
  return entry.result.data.reduce((sum, row) => sum + (Number(row[1]) || 0), 0);
}

/** "EMR 205 · GP 207 · Pharmacy 1,439", in the diagram's order rather than Zetaris's. */
function bySource(entry: LogEntry | undefined): string {
  const rows = [...(entry?.result?.data ?? [])];
  const rank = (id: unknown) => {
    const i = Object.keys(SHORT).indexOf(String(id));
    return i < 0 ? Object.keys(SHORT).length : i;
  };
  rows.sort((a, b) => rank(a[0]) - rank(b[0]));
  return rows.map((row) => `${SHORT[String(row[0])] ?? row[0]} ${formatCount(row[1]) ?? row[1]}`).join(" · ");
}

function Stat({ tone, num, say, cap }: { tone: "high" | "accent"; num: string; say: string; cap?: ReactNode }) {
  return (
    <>
      <span className={`dm-stat-num dm-num dm-stat-${tone}`}>{num}</span>
      <p className="dm-stat-say">{say}</p>
      {cap && <p className="dm-stat-cap">{cap}</p>}
    </>
  );
}

function Findings({ byId }: { byId: Record<string, LogEntry> }) {
  const dq = byId.dq;
  const risk = byId.high_risk;
  const ways = byId.spellings;
  const total = byId.rows?.phase === "done" ? formatCount(soleCell(byId.rows.result)) : null;
  const top = ways?.phase === "done" ? ways.result?.data[0] : undefined;
  const sum = riskTotal(risk);
  return (
    <div className="dm-stats" role="list">
      <section className="dm-stat" role="listitem" aria-label="Doses that don't exist">
        <h2 className="dm-stat-title">Doses that don't exist</h2>
        {pending(dq) ?? (
          <Stat
            tone="high"
            num={formatCount(soleCell(dq?.result)) ?? "0"}
            say="lines list a strength no product comes in"
            cap={
              <>
                {total ? `of ${total} lines · ` : ""}rule <span className="dm-mono">strength_is_a_real_product</span>
              </>
            }
          />
        )}
      </section>
      <section className="dm-stat" role="listitem" aria-label="High-risk medicine lines">
        <h2 className="dm-stat-title">High-risk medicines</h2>
        {pending(risk) ?? (
          <Stat
            tone="accent"
            num={formatCount(sum) ?? "0"}
            say="lines carry an ACSQHC high-risk class"
            cap={bySource(risk)}
          />
        )}
      </section>
      <section className="dm-stat" role="listitem" aria-label="Same medicine, written many ways">
        <h2 className="dm-stat-title">Written many ways</h2>
        {pending(ways) ??
          (top ? (
            <Stat
              tone="accent"
              num={formatCount(top[1]) ?? String(top[1])}
              say={`ways to write ${top[0]}, matched to one medicine`}
              cap={`across ${formatCount(top[2]) ?? top[2]} systems`}
            />
          ) : (
            <p className="dm-wait">No rows came back.</p>
          ))}
      </section>
    </div>
  );
}

function findingsSpoken(byId: Record<string, LogEntry>): string {
  const dq = byId.dq?.phase === "done" ? formatCount(soleCell(byId.dq.result)) : null;
  const sum = riskTotal(byId.high_risk);
  const top = byId.spellings?.phase === "done" ? byId.spellings.result?.data[0] : undefined;
  const parts = [
    dq && `${dq} doses that don't exist.`,
    sum != null && `${formatCount(sum)} high-risk lines.`,
    top && `${top[0]} written ${top[1]} ways.`,
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : "Waiting for its queries.";
}
