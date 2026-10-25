import type { IdentityReview as Review, SourceRow } from "../types";
import { sourceLabel } from "../format";

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
  { label: "IHI (synthetic)", show: "ihi_syn", evidence: ["ihi"] },
];

// The colour follows the matcher's own sentence in `field_evidence`, never a
// comparison done here: "M" vs "Male" or a combined name field would read as
// "differs" to a string compare while the matcher (correctly) calls it a match.
const DIFFERS = /differ|mismatch|conflict|swap|typo|transpos|does not match|no match/i;
const AGREES = /match|same|equal|nickname/i;

function agreement(sentences: string[]): "agree" | "differ" | "missing" {
  if (!sentences.length) return "missing";
  if (sentences.some((t) => DIFFERS.test(t))) return "differ";
  return sentences.some((t) => AGREES.test(t)) ? "agree" : "missing";
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
      <h2>Identity review needed</h2>
      <p className="lead">
        {banner ??
          "These records could be this patient, but the match is not certain enough to merge automatically. A wrong merge mixes two people's medicines."}
      </p>
      <div className="table-scroll">
        <table className="id-table">
          <thead>
            <tr>
              <th />
              <th className="anchor-col">
                {sourceLabel(anchor.source)}
                <div className="muted small">
                  {anchor.source}:{anchor.source_patient_id} · this admission
                </div>
              </th>
              {candidates.map((c) => {
                const r = records[c.candidate_id];
                return (
                  <th key={c.candidate_id}>
                    {sourceLabel(r?.source ?? c.candidate_id.split(":")[0])}
                    <div className="muted small">{c.candidate_id}</div>
                    <div className="score">
                      p = {c.probability.toFixed(2)} · weight {c.match_weight.toFixed(1)} · {c.band}
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
                <td className="anchor-col">{anchor[f.show] ?? <span className="muted">—</span>}</td>
                {candidates.map((c) => {
                  const r = records[c.candidate_id];
                  const ev = f.evidence.map((k) => c.field_evidence[k]).filter(Boolean);
                  return (
                    <td key={c.candidate_id} className={`agree-${agreement(ev)}`}>
                      {r ? (r[f.show] ?? <span className="muted">—</span>) : <span className="muted">record not sent</span>}
                      {ev.map((t) => (
                        <div key={t} className="why">
                          {t}
                        </div>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
            {otherKeys.length > 0 && (
              <tr>
                <th scope="row">Other evidence</th>
                <td className="anchor-col" />
                {candidates.map((c) => (
                  <td key={c.candidate_id} className="small">
                    {otherKeys
                      .filter((k) => c.field_evidence[k])
                      .map((k) => (
                        <div key={k}>
                          <span className="muted">{k}:</span> {c.field_evidence[k]}
                        </div>
                      ))}
                  </td>
                ))}
              </tr>
            )}
            <tr>
              <th scope="row">Held back because</th>
              <td className="anchor-col" />
              {candidates.map((c) => (
                <td key={c.candidate_id} className="guard">
                  {c.field_evidence.guard ?? (c.guards.join(", ") || "—")}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Your decision</th>
              <td className="anchor-col" />
              {candidates.map((c) => {
                const d = decided[c.candidate_id];
                return (
                  <td key={c.candidate_id}>
                    {d ? (
                      <span className={`badge ${d === "same" ? "ok" : "neutral"}`}>
                        {d === "same" ? "Same person" : "Different people"}
                      </span>
                    ) : (
                      <div className="btn-row">
                        <button disabled={!!busy} onClick={() => onDecide(c.candidate_id, true)}>
                          Same person
                        </button>
                        <button disabled={!!busy} onClick={() => onDecide(c.candidate_id, false)}>
                          Different people
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
      <p className="legend small">
        <span className="swatch agree-agree" /> matcher says it agrees <span className="swatch agree-differ" /> matcher
        says it differs <span className="swatch agree-missing" /> not compared. The sentence under each value is the
        matcher's reason.
      </p>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
