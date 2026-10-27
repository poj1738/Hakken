import type { Notice } from "../types";
import { cleanText, medName } from "../format";
import { rowDate } from "../records";
import { InfoTip } from "./InfoTip";

/**
 * S42: known shortages (TGA, Q4) as one "Supply" section. The disclaimer is said
 * once, in the header. When the API ranks a notice against the patient's own
 * product (`relevance`, top-level or in an object `detail`), "Affects this
 * patient" comes first and other products of the same medicine collapse into one
 * line each. Without `relevance` the screen does not guess: shortages are listed
 * per medicine, marked as not matched to the patient's product.
 */
export const DISCLAIMER = "The TGA shortage database is incomplete: a listed shortage is not a statement that a medicine is unavailable.";

type Rel = "affects" | "other" | "drop" | "unranked";
interface Short {
  n: Notice;
  medicine: string;
  product: string;
  status: string | null;
  back: string | null;
  rel: Rel;
}

const obj = (n: Notice): Record<string, unknown> | null => {
  const d = (n as unknown as { detail: unknown }).detail;
  return d && typeof d === "object" ? (d as Record<string, unknown>) : null;
};
const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);

/** The notice's relevance as the API sent it, mapped to a group; anything unrecognised is "unranked", never guessed. */
function relevanceOf(n: Notice): Rel {
  const raw = str((n as unknown as Record<string, unknown>).relevance) ?? str(obj(n)?.relevance);
  if (!raw) return "unranked";
  if (/affect|this.?patient|same.?product|patient.?product/i.test(raw)) return "affects";
  if (/other|different|same.?medicine/i.test(raw)) return "other";
  if (/drop|route|form|irrelevant|none/i.test(raw)) return "drop";
  return "unranked";
}

// Today's API sentence: "Known shortage listed for <product> (<status>, expected to resolve <date>). The TGA … unavailable."
const SENTENCE = /Known shortage listed for (.+?) \(([^,)]+)(?:, expected to resolve ([^)]+))?\)/i;
const DISCLAIMERS = [/\s*The TGA shortage database is incomplete[^.]*\./gi, /\s*\(TGA database is incomplete\)/gi];

function parse(n: Notice): Short {
  const o = obj(n);
  const raw = typeof n.detail === "string" ? n.detail : str(o?.text) ?? str(o?.summary) ?? "";
  // The disclaimer is said once in the header, so take it out before reading the sentence.
  const text = DISCLAIMERS.reduce((t, r) => t.replace(r, ""), raw).trim();
  const m = SENTENCE.exec(text);
  const product = str(o?.product) ?? str(o?.medicine_name) ?? (m ? m[1] : null) ?? cleanText(text).replace(/^Known shortage listed for /i, "").replace(/\.$/, "");
  const back = str(o?.expected_resolution) ?? (m && m[3] ? m[3].trim() : null);
  return {
    n,
    medicine: n.generic ?? product,
    product,
    status: str(o?.status) ?? (m ? m[2].trim() : null),
    back: back ? rowDate(back) : null,
    rel: relevanceOf(n),
  };
}

function byMedicine(items: Short[]): [string, Short[]][] {
  const m = new Map<string, Short[]>();
  for (const s of items) m.set(s.medicine, [...(m.get(s.medicine) ?? []), s]);
  return [...m.entries()];
}

function Line({ s }: { s: Short }) {
  return (
    <div className="supply-line">
      <span className="supply-product">{s.product}</span>
      {s.status && <span className="tag t-medium">{s.status}</span>}
      {s.back && <span className="supply-back">Expected back {s.back}</span>}
    </div>
  );
}

export function Supply({ notices }: { notices: Notice[] }) {
  const all = notices.filter((n) => n.type === "known_shortage").map(parse);
  const affects = all.filter((s) => s.rel === "affects");
  const other = all.filter((s) => s.rel === "other");
  const unranked = all.filter((s) => s.rel === "unranked");
  const dropped = all.filter((s) => s.rel === "drop").length;
  return (
    <>
      <div className="sec-head">
        <h2 className="sec-title">Supply</h2>
        <span className="sec-meta">Known shortages (TGA)</span>
      </div>
      <p className="supply-caveat">{DISCLAIMER}</p>
      {!all.length && <p className="sec-empty">No known shortages</p>}

      {affects.length > 0 && (
        <div className="supply-group">
          <h3 className="fgroup-title">
            Affects this patient <span className="count">{affects.length}</span>
          </h3>
          {affects.map((s, i) => (
            <div key={i} className="supply-card">
              <div className="supply-med">{medName(s.medicine)}</div>
              <Line s={s} />
            </div>
          ))}
        </div>
      )}

      {other.length > 0 && (
        <div className="supply-group">
          <h3 className="fgroup-title">
            Other products short <span className="count">{other.length}</span>
            <InfoTip text="Other strength, brand or form; the patient's product isn't listed" />
          </h3>
          {byMedicine(other).map(([med, items]) => (
            <details key={med} className="supply-fold">
              <summary>
                <strong>{medName(med)}</strong>: {items.length} other {items.length === 1 ? "product" : "products"} short
              </summary>
              {items.map((s, i) => (
                <Line key={i} s={s} />
              ))}
            </details>
          ))}
        </div>
      )}

      {unranked.length > 0 && (
        <div className="supply-group">
          <h3 className="fgroup-title">
            Listed for these medicines <span className="count">{unranked.length}</span>
            <InfoTip text="Not yet matched to the patient's product" />
          </h3>
          {byMedicine(unranked).map(([med, items]) => (
            <details key={med} className="supply-fold" open={items.length === 1}>
              <summary>
                <strong>{medName(med)}</strong>: {items.length} {items.length === 1 ? "product" : "products"} listed
              </summary>
              {items.map((s, i) => (
                <Line key={i} s={s} />
              ))}
            </details>
          ))}
        </div>
      )}
      {dropped > 0 && <p className="supply-dropped">{dropped} listed for a different route or form, not shown.</p>}
    </>
  );
}
