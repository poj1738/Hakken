import type { PatientSummary } from "../types";
import { SOURCES } from "../types";
import { ICON } from "./Silos";
import { fullName } from "./Picker";

/**
 * Welcome to MedTrace: the default view before any patient is run, and always one
 * click away in the sidebar. Wording comes only from README.md, metadata.json's
 * one-liner and docs/PITCH_CLAIMS.md; the Limitations card is PLAN §8's text.
 * No numbers are invented here: the learning visual has no values on it.
 */
const SOURCE_NAME: Record<string, string> = { emr: "Hospital chart", gp: "GP", pharmacy: "Pharmacy", patient: "Patient interview" };

const CHECKS = [
  "Identity across systems",
  "Omissions",
  "Dose and formulation conflicts",
  "Duplications",
  "Possibly stopped medicines",
  "High-alert (APINCHS) first",
];

const POWERED: [string, string][] = [
  ["Zetaris", "The data layer: every source is queried through Zetaris."],
  ["Meterless Nightshift", "Every model call goes through Nightshift."],
  ["Meterless engines", "H-MEM holds pharmacist-taught trust; World Model holds identity memory."],
  ["NVIDIA Nemotron", "The model that answers the agents, through Nightshift."],
];

const DEMO: { ids: string[]; what: string }[] = [
  { ids: ["MRN0000089"], what: "Straight through" },
  { ids: ["MRN0000015"], what: "Identity review" },
  { ids: ["MRN0000003", "MRN0000007"], what: "Learning: mark a dose outdated, then see the next patient" },
];

export const LIMITATIONS =
  "Synthetic data only. Not medical advice; a pharmacist must confirm every item. Model output can vary between runs. Identity-matching statistics come mostly from US studies; there are no public Australian IHI match rates. Harm cases are illustrations.";

export function Welcome({ patients, onPick, onStart }: { patients: PatientSummary[]; onPick: (id: string) => void; onStart: () => void }) {
  const byId = new Map(patients.map((p) => [p.patient_id, p]));
  return (
    <div className="welcome">
      <section className="panel wl-hero">
        <h1 className="wl-title">Welcome to MedTrace</h1>
        <p className="wl-lead">
          MedTrace reconciles an admitted patient's pre-admission medicines across four systems that don't talk to each other:
          the hospital EMR, the GP, the community pharmacy and the bedside interview.
        </p>
        <p className="wl-problem">
          <span className="wl-k">The problem</span> In a landmark Canadian study, more than half of older inpatients had at
          least one unintended medication discrepancy at admission. <cite>Cornish et al. 2005, Arch Intern Med</cite>
        </p>
      </section>

      <section className="panel wl-card" aria-labelledby="wl-how">
        <h2 className="h2" id="wl-how">
          How it works
        </h2>
        <ol className="wl-steps">
          <li>
            <span className="wl-n">1</span> Select a patient
          </li>
          <li>
            <span className="wl-n">2</span> Run reconciliation
          </li>
          <li>
            <span className="wl-n">3</span> Review discrepancies, then confirm or reject
          </li>
        </ol>
        <button type="button" className="btn btn-primary" onClick={onStart}>
          Start with a patient
        </button>
      </section>

      <div className="wl-grid">
        <section className="panel wl-card" aria-labelledby="wl-sources">
          <h2 className="h2" id="wl-sources">
            Four sources, one view
          </h2>
          <ul className="wl-sources">
            {SOURCES.map((s) => (
              <li key={s}>
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  {ICON[s]}
                </svg>
                {SOURCE_NAME[s]}
              </li>
            ))}
          </ul>
          <p className="wl-note">A missing source is "unknown", never "not taking".</p>
        </section>

        <section className="panel wl-card" aria-labelledby="wl-checks">
          <h2 className="h2" id="wl-checks">
            What it checks
          </h2>
          <ul className="wl-checks">
            {CHECKS.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>

        <section className="panel wl-card" aria-labelledby="wl-learn">
          <h2 className="h2" id="wl-learn">
            It learns
          </h2>
          <p className="wl-text">It learns from the pharmacist which source to trust: feedback changes source confidence for future runs.</p>
          <div className="wl-bars" role="img" aria-label="Illustration: a source's confidence before and after pharmacist feedback">
            <span className="wl-bar-k">Before</span>
            <span className="bar">
              <span className="bar-before" style={{ width: "70%" }} />
            </span>
            <span className="wl-bar-k">After feedback</span>
            <span className="bar">
              <span className="bar-fill" style={{ width: "50%" }} />
            </span>
          </div>
        </section>

        <section className="panel wl-card wl-wide" aria-labelledby="wl-powered">
          <h2 className="h2" id="wl-powered">
            Powered by
          </h2>
          <dl className="wl-powered">
            {POWERED.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <section className="panel wl-card" aria-labelledby="wl-demo">
        <h2 className="h2" id="wl-demo">
          Suggested demo patients
        </h2>
        <ul className="wl-demo">
          {DEMO.map((d) => (
            <li key={d.ids.join()}>
              <span className="wl-demo-what">{d.what}</span>
              <span className="wl-demo-pts">
                {d.ids.map((id, i) => {
                  const p = byId.get(id);
                  return (
                    <span key={id}>
                      {i > 0 && <span aria-hidden> → </span>}
                      <button type="button" className="btn btn-line btn-sm" onClick={() => onPick(id)} disabled={!p} title={p ? undefined : "Not in this patient list"}>
                        {p ? `${fullName(p)} · ${id.replace(/^MRN/, "MRN ")}` : id}
                      </button>
                    </span>
                  );
                })}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel wl-card wl-limits" aria-labelledby="wl-lim">
        <h2 className="h2" id="wl-lim">
          Limitations
        </h2>
        <p className="wl-text">{LIMITATIONS}</p>
      </section>
    </div>
  );
}
