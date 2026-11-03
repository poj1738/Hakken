// Presenter view of the same diagram, for a window beside the Zetaris SQL editor.
// It runs the same catalogue, in the same order, and shows a number only after
// that step's own response has arrived.

import { useEffect, useState } from "react";
import { API_MODE } from "../api";
import { DISCLAIMER } from "./Footer";
import { DataMapDiagram, formatCount, soleCell, useDataMapRun, type LogEntry } from "./DataMapDiagram";

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
    title: "Data quality",
    line: "medicine lines have a strength that isn't a real product",
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
  const { catalogue, byId } = useDataMapRun(true);
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
        <p className="dm-live" aria-live="polite">
          {current.title}. {spoken || "Waiting for its query."} {current.line}
          {dq && entry?.phase === "done" ? " Rule strength_is_a_real_product." : ""}
        </p>
        {dq && <DqHero entry={entry} />}
      </header>
      <div className="dm-diagram dm-diagram-present">
        {catalogue ? (
          <DataMapDiagram catalogue={catalogue} byId={byId} lit={current.lit} present />
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

function DqHero({ entry }: { entry?: LogEntry }) {
  if (!entry) return <p className="dm-wait">Waiting for its query.</p>;
  if (entry.phase === "running") return <p className="dm-wait">querying Zetaris…</p>;
  if (entry.phase === "error") return <p className="dm-err">{entry.error}</p>;
  const count = soleCell(entry.result);
  if (count == null) return null;
  return (
    <p className="dm-dq-hero">
      <span className="dm-dq-num dm-num">{formatCount(count)}</span>
      <span className="dm-rule">strength_is_a_real_product</span>
    </p>
  );
}
