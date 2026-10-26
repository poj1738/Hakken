import type { IdentityReview as Review, SourceRow } from "../types";
import { cleanText, fmtDate, humanize, sourceLabel } from "../format";
import { TechDetails } from "./TechDetails";

// Rows of the side-by-side table. `show` is the text displayed (the raw DOB,
// because a day/month swap is only visible in the raw text); `evidence` names
// the `field_evidence` keys that explain it.
const FIELDS: { label: string; show: keyof SourceRow; evidence: string[] }[] = [
  { label: "Given name", show: "name_given", evidence: ["given"] },
  { label: "Family name", show: "name_family", evidence: ["surname"] },
  { label: "Previous name", show: "name_previous", evidence: [] },
  { label: "Date of birth", show: "dob_raw", evidence: ["dob"] },
  { label: "Sex", show: "sex", evidence: ["sex"] },
  { label: "Postcode", show: "postcode", evidence: ["postcode"] },
  { label: "IHI (synthetic)", show: "ihi_syn", evidence: ["ihi_syn", "ihi"] },
];

// The colour follows the matcher's own verdict, never a comparison done here:
// "M" vs "Male" or a combined name field would read as "differs" to a string
// compare while the matcher (correctly) calls it a match.
//
// Since 25 Oct, identity.py starts every field_evidence sentence with a verdict
// (identity.EVIDENCE_VERDICTS: agrees / partial / differs / held), set from the
// score itself. The keyword fallback is only for sentences without one (the
// hand-written examples, until they are regenerated from real runs).
type Agreement = "agree" | "partial" | "differ" | "missing";
const PREFIX = /^(agrees|partial|differs|held):\s*/;
const PREFIX_TO_AGREEMENT: Record<string, Agreement> = { agrees: "agree", partial: "partial", differs: "differ", held: "partial" };
const DIFFERS = /differ|mismatch|conflict|swap|typo|transpos|does not match|no match/i;
const AGREES = /match|same|equal|nickname/i;

/** The sentence without its verdict prefix, for display. */
const stripVerdict = (t: string) => t.replace(PREFIX, "");

function agreementOf(t: string): Agreement {
  const m = PREFIX.exec(t);
  if (m) return PREFIX_TO_AGREEMENT[m[1]];
  if (DIFFERS.test(t)) return "differ";
  return AGREES.test(t) ? "agree" : "missing";
}

function agreement(sentences: string[]): Agreement {
  const a = sentences.map(agreementOf);
  for (const v of ["differ", "partial", "agree"] as const) if (a.includes(v)) return v;
  return "missing";
}

/** A record field for display: dates as dates; the raw DOB text is kept as written (a day/month swap is the point). */
function show(r: SourceRow, k: keyof SourceRow) {
  const v = r[k];
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (k === "dob_raw" && /^\d{4}-\d{2}-\d{2}$/.test(String(v))) return <span title={String(v)}>{fmtDate(String(v))}</span>;
  return String(v);
}

interface Props {
  review: Review;
  banner?: string | null;
  decided: Record<string, "same" | "different">;
  busy: string | null;
  error: string | null;
  onDecide: (candidateId: string, samePerson: boolean) => void;
}

export function IdentityReview({ review, banner, decided, busy, error, onDecide }: Props) {
  const { anchor, candidates, records } = review;
  // Evidence keys the table has no row for are still shown, never dropped.
  const shownKeys = new Set(["guard", ...FIELDS.flatMap((f) => f.evidence)]);
  const otherKeys = [...new Set(candidates.flatMap((c) => Object.keys(c.field_evidence)))].filter((k) => !shownKeys.has(k));
  return (
    <section className="card identity">
      <div className="id-head">
        <div className="eyebrow">Identity review required</div>
        <h2>Confirm Patient Records</h2>
        <p className="id-lead">
          {cleanText(banner) ||
            "These records may belong to this patient, but the match is not certain enough to link automatically. An incorrect link would combine two people's medicines."}
        </p>
      </div>
      <div className="id-scroll">
        <table className="id-table">
          <thead>
            <tr>
              <th />
              <th className="anchor-col" title={`${anchor.source}:${anchor.source_patient_id}`}>
                {sourceLabel(anchor.source)}
                <div className="score">This admission</div>
              </th>
              {candidates.map((c) => {
                const r = records[c.candidate_id];
                return (
                  <th key={c.candidate_id} title={c.candidate_id}>
                    {sourceLabel(r?.source ?? c.candidate_id.split(":")[0])}
                    <div className="score">
                      <span className="match">{Math.round(c.probability * 100)}% match</span> · {humanize(c.band)}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {FIELDS.map((f) => (
              <tr key={f.label}>
                <th scope="row">{f.label}</th>
                <td className="anchor-col">{show(anchor, f.show)}</td>
                {candidates.map((c) => {
                  const r = records[c.candidate_id];
                  const ev = f.evidence.map((k) => c.field_evidence[k]).filter(Boolean);
                  return (
                    <td key={c.candidate_id} className={`agree-${agreement(ev)}`}>
                      {r ? show(r, f.show) : <span className="muted">Record not sent</span>}
                      {ev.map((t) => (
                        <div key={t} className="why">
                          {stripVerdict(t)}
                        </div>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
            {otherKeys.length > 0 && (
              <tr>
                <th scope="row">Other matching evidence</th>
                <td className="anchor-col" />
                {candidates.map((c) => (
                  <td key={c.candidate_id} className="small">
                    {otherKeys
                      .filter((k) => c.field_evidence[k])
                      .map((k) => (
                        <div key={k}>
                          <span className="muted">{humanize(k)}:</span> {stripVerdict(c.field_evidence[k])}
                        </div>
                      ))}
                  </td>
                ))}
              </tr>
            )}
            <tr>
              <th scope="row">Withheld from automatic linkage</th>
              <td className="anchor-col" />
              {candidates.map((c) => (
                <td key={c.candidate_id} className="guard">
                  {c.field_evidence.guard ? cleanText(stripVerdict(c.field_evidence.guard)) : c.guards.map(humanize).join(", ") || "—"}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Pharmacist decision</th>
              <td className="anchor-col" />
              {candidates.map((c) => {
                const d = decided[c.candidate_id];
                return (
                  <td key={c.candidate_id}>
                    {d ? (
                      <span className={`pill ${d === "same" ? "pill-ok" : "sev-low"}`}>
                        {d === "same" ? "Confirmed: same patient" : "Recorded: different patients"}
                      </span>
                    ) : (
                      <div className="btn-row">
                        <button type="button" className="btn btn-primary" disabled={!!busy} onClick={() => onDecide(c.candidate_id, true)}>
                          Same patient
                        </button>
                        <button type="button" className="btn btn-quiet" disabled={!!busy} onClick={() => onDecide(c.candidate_id, false)}>
                          Different patients
                        </button>
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="id-legend">
        <span className="swatch agree-agree" /> Agrees <span className="swatch agree-partial" /> Partial match{" "}
        <span className="swatch agree-differ" /> Differs <span className="swatch agree-missing" /> Not compared. Colours show
        the matching engine's own verdict; the text under each value is its reason.
      </p>
      <TechDetails
        items={[
          ["This admission", `${anchor.source}:${anchor.source_patient_id} (row ${anchor.row_id})`],
          ...candidates.map(
            (c): [string, string] => [
              sourceLabel(records[c.candidate_id]?.source ?? c.candidate_id.split(":")[0]),
              `${c.candidate_id} · probability ${c.probability.toFixed(2)} · match weight ${c.match_weight.toFixed(1)} · band ${c.band} · tier ${c.tier}${c.guards.length ? ` · guards ${c.guards.join(", ")}` : ""}`,
            ],
          ),
        ]}
      />
      {error && <p className="error">{error}</p>}
    </section>
  );
}
