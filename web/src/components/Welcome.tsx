import type { ReactNode } from "react";
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

const CHECKS = ["Identity across systems", "Omissions", "Dose and formulation conflicts", "Duplications", "Possibly stopped medicines", "High-alert (APINCHS) first"];

/**
 * Official logos, if someone places them in web/public/sponsors/ (zetaris.svg,
 * meterless.svg, nvidia.svg), are picked up at build time and shown inside the
 * icon tile; until then each card uses a generic line icon. Logos are never drawn
 * or recreated here.
 */
const LOGOS = new Set(Object.keys(import.meta.glob("/public/sponsors/*.svg")).map((k) => k.replace(/^\/public\/sponsors\//, "").replace(/\.svg$/, "")));

const LINE: Record<string, ReactNode> = {
  // database
  data: (
    <>
      <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
      <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
    </>
  ),
  // server
  runtime: (
    <>
      <rect x="4" y="4" width="16" height="6.5" rx="1.5" />
      <rect x="4" y="13.5" width="16" height="6.5" rx="1.5" />
      <path d="M8 7.25h.01M8 16.75h.01M12 7.25h5M12 16.75h5" />
    </>
  ),
  // memory chip
  engines: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="1.5" />
      <rect x="9.5" y="9.5" width="5" height="5" rx="0.5" />
      <path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21" />
    </>
  ),
  // network / model
  models: (
    <>
      <circle cx="12" cy="5" r="2" />
      <circle cx="5" cy="18" r="2" />
      <circle cx="19" cy="18" r="2" />
      <circle cx="12" cy="13" r="2" />
      <path d="M12 7v4M10.4 14.2 6.6 16.8M13.6 14.2l3.8 2.6M7 18h10" />
    </>
  ),
};

const SPONSORS: { name: string; role: string; tag: string; icon: string; logo: string }[] = [
  { name: "Zetaris", role: "Every source queried by SQL", tag: "Data", icon: "data", logo: "zetaris" },
  { name: "Meterless Nightshift", role: "Routes every model call", tag: "AI runtime", icon: "runtime", logo: "meterless" },
  { name: "Meterless engines", role: "H-MEM trust · World Model identity", tag: "Engines", icon: "engines", logo: "meterless" },
  { name: "NVIDIA Nemotron", role: "Answers the agents' model calls", tag: "Models", icon: "models", logo: "nvidia" },
];

const DEMO: { ids: string[]; what: string }[] = [
  { ids: ["MRN0000089"], what: "Straight through" },
  { ids: ["MRN0000015"], what: "Identity review" },
  { ids: ["MRN0000003", "MRN0000007"], what: "Learning" },
];

export const LIMITATIONS =
  "Synthetic data only. Not medical advice; a pharmacist must confirm every item. Model output can vary between runs. Identity-matching statistics come mostly from US studies; there are no public Australian IHI match rates. Harm cases are illustrations.";

const Line = ({ children, size = 22 }: { children: ReactNode; size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {children}
  </svg>
);

export function Welcome({ patients, onPick, onStart }: { patients: PatientSummary[]; onPick: (id: string) => void; onStart: () => void }) {
  const byId = new Map(patients.map((p) => [p.patient_id, p]));
  return (
    <div className="welcome">
      <section className="panel wl-hero">
        <div className="wl-hero-text">
          <h1 className="wl-title">Welcome to MedTrace</h1>
          <p className="wl-lead">
            MedTrace reconciles an admitted patient's pre-admission medicines across four systems that don't talk to each
            other: the hospital EMR, the GP, the community pharmacy and the bedside interview.
          </p>
          <div className="wl-problem">
            <span className="wl-k">The problem</span>
            <p>In a Canadian study, more than half of older inpatients had at least one unintended medication discrepancy at admission.</p>
            <cite>Cornish et al. 2005, Arch Intern Med</cite>
          </div>
        </div>
        <div className="wl-hero-side">
          <div className="wl-flow" aria-label="Four sources reconciled into one view">
            <ul className="wl-flow-src">
              {SOURCES.map((s) => (
                <li key={s}>
                  <Line size={18}>{ICON[s]}</Line>
                  {SOURCE_NAME[s]}
                </li>
              ))}
            </ul>
            <span className="wl-flow-arrow" aria-hidden>
              →
            </span>
            <div className="wl-flow-hub">MedTrace</div>
          </div>
          <p className="wl-caption">No record in a source means unknown, not stopped</p>
          <button type="button" className="btn btn-primary" onClick={onStart}>
            Start with a patient
          </button>
        </div>
      </section>

      <div className="wl-row3">
        <section className="panel wl-card" aria-labelledby="wl-how">
          <h2 className="wl-h" id="wl-how">
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
              <span className="wl-n">3</span> Review, then confirm or reject
            </li>
          </ol>
        </section>
        <section className="panel wl-card" aria-labelledby="wl-checks">
          <h2 className="wl-h" id="wl-checks">
            What it checks
          </h2>
          <ul className="wl-checks">
            {CHECKS.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
        <section className="panel wl-card" aria-labelledby="wl-learn">
          <h2 className="wl-h" id="wl-learn">
            It learns
          </h2>
          <p className="wl-text">Pharmacist feedback adjusts source trust for later runs.</p>
          <div className="wl-bars" role="img" aria-label="Illustration: a source's trust before and after pharmacist feedback">
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
      </div>

      <section aria-labelledby="wl-powered">
        <h2 className="wl-h wl-h-out" id="wl-powered">
          Powered by
        </h2>
        <ul className="sponsors">
          {SPONSORS.map((s) => (
            <li key={s.name} className="sponsor" tabIndex={0} aria-label={`${s.name}: ${s.role}. ${s.tag}.`}>
              <span className="sponsor-tile">
                {LOGOS.has(s.logo) ? <img src={`/sponsors/${s.logo}.svg`} alt="" /> : <Line size={28}>{LINE[s.icon]}</Line>}
              </span>
              <span className="sponsor-name">{s.name}</span>
              <span className="sponsor-role">{s.role}</span>
              <span className="sponsor-tag">{s.tag}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="wl-demo">
        <h2 className="wl-h wl-h-out" id="wl-demo">
          Demo patients
        </h2>
        <ul className="wl-demo">
          {DEMO.map((d) => (
            <li key={d.ids.join()} className="panel wl-demo-card">
              <span className="wl-demo-what">{d.what}</span>
              <span className="wl-demo-pts">
                {d.ids.map((id, i) => {
                  const p = byId.get(id);
                  return (
                    <span key={id} className="wl-demo-pt">
                      {i > 0 && (
                        <span className="wl-demo-then" aria-hidden>
                          then
                        </span>
                      )}
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
        <h2 className="wl-h" id="wl-lim">
          Limitations
        </h2>
        <p className="wl-text">{LIMITATIONS}</p>
      </section>
    </div>
  );
}
