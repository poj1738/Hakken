"""Executor (mostly code): fetches through Zetaris and runs the deterministic pack.

  FIND_IDENTITY  Q1 -> `rows_from_sql` -> `identity.link_identity`. A review-band
                 link stops the run (`needs_review`) until a human decides.
  FETCH_MEDS     Q2 on the anchor plus the confirmed links only, then rows are
                 filtered to those records -- in SAMPLE_MODE the recorded Q2 holds
                 every row the fixture was recorded with, so a rejected link must
                 not leak medicines in.
  NORMALISE      `normalise.normalise_med` per row.
  RESOLVE_FREE_TEXT  One batched Nemotron call for the `unmapped` lines, choosing
                 ONLY from `normalise.llm_candidates`. An answer outside that set is
                 discarded and the line stays unmapped. A class-level answer
                 ("my blood thinner" -> B01) is never auto-resolved; it becomes a
                 confirm task.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.adapters.zetaris import QueryBudgetExceeded, ReplayMiss, ZetarisError
from app.agents.base import AgentContext
from app.domain.packs.medtrace import identity, queries
from app.domain.packs.medtrace.normalise import llm_candidates, normalise_med, parse_strength_mg
from app.domain.packs.medtrace.parse import dicts_from_sql, rows_from_sql
from app.domain.packs.medtrace.types import IdentityLink, MedStatement, Notice, NoticeType, SourceRow, SqlResult


def raw_rows(result: SqlResult) -> dict[str, dict[str, str | None]]:
    """row_id -> the row exactly as Zetaris returned it (strings, and None for NULL)."""
    headers = list(result["headers"])
    out: dict[str, dict[str, str | None]] = {}
    for row in result["data"]:
        rec = {h: (None if v is None else str(v)) for h, v in zip(headers, row)}
        if rec.get("row_id"):
            out[str(rec["row_id"])] = rec
    return out


def find_identities(ctx: AgentContext, anchor: SourceRow) -> tuple[list[IdentityLink], dict[str, SourceRow]]:
    """Returns the links and one row per candidate record (for the side-by-side review)."""
    ctx.check_time()
    sql = queries.q_identity_candidates(anchor)
    result, record = ctx.zetaris.run(sql, template_id="Q1", replay_key=anchor.source_patient_id)
    rows = rows_from_sql(result)
    by_key: dict[str, SourceRow] = {}
    for r in rows:
        by_key.setdefault(r.record_key, r)
    links = identity.link_identity(anchor, [r for r in rows if r.record_key != anchor.record_key], ctx.lex)
    merged = [l for l in links if l.band == "auto-merge"]
    review = [l for l in links if l.band == "review"]
    name = f"{anchor.name_given} {anchor.name_family}"
    msg = f"Found {name} in {len(merged)} other record(s): {', '.join(l.candidate_id for l in merged) or 'none'}."
    if review:
        why = "; ".join(f"{l.candidate_id} {l.probability:.2f} ({l.field_evidence.get('guard') or ', '.join(l.field_evidence.values())[:120]})"
                        for l in review)
        msg += f" {len(review)} near-miss(es) need your confirmation: {why}."
    ctx.tracer.emit("Executor", "find_identities", step="FIND_IDENTITY", message=msg, **record.trace_fields())
    return links, by_key


def fetch_meds(ctx: AgentContext, anchor: SourceRow, links: list[IdentityLink]
               ) -> tuple[list[SourceRow], dict[str, dict[str, str | None]], str]:
    """Q2 on the confirmed set. Returns the rows, the raw rows by id, and the SQL (for evidence)."""
    ctx.check_time()
    confirmed = [l for l in links if l.band == "auto-merge"]
    if not confirmed:
        # q_meds_for reads both ends of each link; a self-link reads the anchor alone,
        # where an empty list would be refused (it reads as "no medicines").
        confirmed = [IdentityLink(anchor_id=anchor.record_key, candidate_id=anchor.record_key, match_weight=0.0,
                                  probability=1.0, band="auto-merge", tier="probabilistic")]
    keys = {anchor.record_key} | {l.candidate_id for l in confirmed}
    sql = queries.q_meds_for(confirmed)
    result, record = ctx.zetaris.run(sql, template_id="Q2", replay_key=anchor.source_patient_id)
    rows = [r for r in rows_from_sql(result) if r.record_key in keys]
    raw = {rid: rec for rid, rec in raw_rows(result).items()
           if f"{rec.get('source')}:{rec.get('source_patient_id')}" in keys}
    by_source: dict[str, int] = {}
    for r in rows:
        if r.has_med:
            by_source[r.source] = by_source.get(r.source, 0) + 1
    ctx.tracer.emit("Executor", "fetch_meds", step="FETCH_MEDS",
                    message=f"Fetched {sum(by_source.values())} medicine rows in one query: "
                            + ", ".join(f"{s} {n}" for s, n in sorted(by_source.items())) + ".",
                    **{**record.trace_fields(), "row_count": len(rows)})
    return rows, raw, sql


def normalise(ctx: AgentContext, rows: list[SourceRow]) -> list[MedStatement]:
    ctx.check_time()
    stmts = [normalise_med(r, ctx.lex) for r in rows if r.has_med]
    counts: dict[str, int] = {}
    for s in stmts:
        counts[s.resolution] = counts.get(s.resolution, 0) + 1
    ctx.tracer.emit("Executor", "normalise", step="NORMALISE",
                    message=f"Normalised {len(stmts)} lines: "
                            + ", ".join(f"{n} by {k}" for k, n in sorted(counts.items())) + ".")
    return stmts


class Resolution(BaseModel):
    row_id: str
    choice: str | None = Field(default=None, description="exactly one of this row's candidates, or null")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Resolutions(BaseModel):
    items: list[Resolution] = Field(default_factory=list)


#: A model answer below this stays unmapped (scan S15): a wrong medicine in the grid is worse
#: than a line the pharmacist is asked to identify.
MIN_RESOLVE_CONFIDENCE = 0.8
#: More ingredient candidates than this, with no class to choose, means the text names no
#: medicine ("a little white one" matched five unrelated ones) -- not something to pick from.
MAX_UNANCHORED_CANDIDATES = 2


def resolve_free_text(ctx: AgentContext, stmts: list[MedStatement]) -> tuple[list[MedStatement], list[str]]:
    """Returns the statements (some now `resolution="llm"`) and any confirm tasks for class-level answers.

    A line the model may not resolve stays `unmapped`; the Evaluator then shows it as an
    unidentified line with an "Identify ... with the patient" task (scan S6).
    """
    ctx.check_time()
    pending = {s.row_id: (s, llm_candidates(s.raw_text, ctx.lex)) for s in stmts if s.resolution == "unmapped"}
    pending = {rid: (s, c) for rid, (s, c) in pending.items() if c.get("ingredients") or c.get("atc_classes")}
    vague = {rid: (s, c) for rid, (s, c) in pending.items()
             if not c.get("atc_classes") and len(c.get("ingredients", [])) > MAX_UNANCHORED_CANDIDATES}
    for rid, (s, c) in vague.items():
        ctx.tracer.emit("Executor", "resolve_free_text", step="RESOLVE_FREE_TEXT", status="skipped",
                        message=f'"{s.raw_text}" ({s.source}, {rid}) names no medicine: it matched '
                                f'{len(c["ingredients"])} unrelated candidates ({", ".join(c["ingredients"])}). '
                                "Not sent to the model; left for the pharmacist to identify.")
    pending = {rid: v for rid, v in pending.items() if rid not in vague}
    if not pending:
        ctx.tracer.emit("Executor", "resolve_free_text", step="RESOLVE_FREE_TEXT",
                        message="No free-text lines needed the model.")
        return stmts, []

    lines = "\n".join(f'- row_id {rid}: "{s.raw_text}" -> candidates: '
                      f'ingredients {c.get("ingredients", [])}, ATC classes {c.get("atc_classes", [])}'
                      for rid, (s, c) in pending.items())
    messages = [{"role": "user", "content": (
        "Map each free-text medicine line to exactly ONE of its listed candidates, or null if none fits. "
        "Never answer with anything that is not in that line's list. Prefer an ingredient; choose an ATC "
        "class only when the text names a class (e.g. 'blood thinner'). Give a confidence from 0 to 1; "
        f"an ingredient answer below {MIN_RESOLVE_CONFIDENCE} is not used.\n" + lines)}]
    # Offline: no guessing -- every line stays unmapped and is shown as such.
    # 3,872 of 4,096 were used live for two lines; 8k leaves room for the hidden reasoning.
    result, calls = ctx.llm.chat_json("Executor", messages, Resolutions, max_tokens=8192,
                                      offline=lambda: Resolutions(items=[]))

    by_row = {r.row_id: r for r in result.items}
    out: list[MedStatement] = []
    resolved, rejected, unsure, tasks = 0, 0, [], []
    for s in stmts:
        res = by_row.get(s.row_id)
        cands = pending.get(s.row_id, (None, {}))[1]
        if res is None or res.choice is None or s.row_id not in pending:
            out.append(s)
            continue
        if res.choice in cands.get("ingredients", []) and res.confidence < MIN_RESOLVE_CONFIDENCE:
            unsure.append(f'"{s.raw_text}" -> {res.choice} ({res.confidence:.2f})')
            out.append(s)
        elif res.choice in cands.get("ingredients", []):
            entry = ctx.lex.by_generic.get(res.choice.casefold())
            out.append(s.model_copy(update={"generic": res.choice, "resolution": "llm",
                                            "ingredients": [(res.choice, None)],
                                            "atc": entry.atc_primary if entry else s.atc}))
            resolved += 1
        elif res.choice in cands.get("atc_classes", []):
            tasks.append(f'Confirm what "{s.raw_text}" ({s.source}, {s.row_id}) refers to: '
                         f'it matches class {res.choice}, not a single medicine')
            out.append(s)
        else:
            rejected += 1
            out.append(s)
    ctx.record("Executor", "resolve_free_text", "RESOLVE_FREE_TEXT", calls,
               f"Resolved {resolved} of {len(pending)} free-text lines from the lexicon candidates"
               + (f"; {len(tasks)} class-level answer(s) left for confirmation" if tasks else "")
               + (f"; {rejected} answer(s) outside the candidate list discarded" if rejected else "")
               + (f"; {len(unsure)} below confidence {MIN_RESOLVE_CONFIDENCE} left unmapped: {'; '.join(unsure)}"
                  if unsure else "") + ".")
    return out, tasks


#: The TGA disclaimer, said ONCE per run (a run caveat), not on every notice (scan S42).
SHORTAGE_DISCLAIMER = ("The TGA shortage database is incomplete: a listed shortage is not a statement that a "
                       "medicine is unavailable, and a medicine not listed may still be short.")
AFFECTS = "affects_this_patient"
OTHER_PRODUCT = "other_product"

_TGA_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|microgram|mcg|g|units?)\b", re.IGNORECASE)
#: Dose form -> route family, first match wins (injection before "solution", which is ambiguous).
_FORM_FAMILY = (("inject", "parenteral"), ("infusion", "parenteral"), ("ampoule", "parenteral"),
                ("vial", "parenteral"), ("inhal", "inhaled"), ("aerosol", "inhaled"), ("nebul", "inhaled"),
                ("patch", "transdermal"), ("transdermal", "transdermal"), ("suppositor", "rectal"),
                ("cream", "topical"), ("ointment", "topical"), ("gel", "topical"), ("eye", "eye"),
                ("tablet", "oral"), ("capsule", "oral"), ("oral", "oral"), ("granule", "oral"),
                ("lozenge", "oral"))
_ROUTE_FAMILY = {"PO": "oral", "SL": "oral", "IV": "parenteral", "SC": "parenteral", "IM": "parenteral",
                 "INH": "inhaled", "TD": "transdermal", "TOP": "topical", "PR": "rectal"}


@dataclass
class _Product:
    """What the patient's own records say they take: brands, strengths (mg), route families."""

    brands: set[str] = field(default_factory=set)
    strengths: set[float] = field(default_factory=set)
    families: set[str] = field(default_factory=set)
    label: str = ""


def _form_family(text: str | None) -> str | None:
    low = (text or "").casefold()
    return next((fam for word, fam in _FORM_FAMILY if word in low), None)


def _patient_products(generics: list[str], stmts: list[MedStatement], raw: dict[str, dict[str, str | None]],
                      lex) -> dict[str, _Product]:
    out: dict[str, _Product] = {}
    for g in generics:
        mine = [s for s in stmts if s.generic == g]
        rows = [raw[s.row_id] for s in mine if s.row_id in raw]
        text = " ".join((r.get("med_text") or "") for r in rows).casefold()
        brands = {b for b, e in lex.by_brand.items() if (e.generic or "").casefold() == g.casefold()
                  and re.search(rf"\b{re.escape(b.casefold())}\b", text)}
        strengths = {v for r in rows if (v := parse_strength_mg(r.get("strength_text"))) is not None}
        families = {f for s in mine if (f := _ROUTE_FAMILY.get(s.route or ""))}
        families |= {f for r in rows if (f := _form_family(r.get("route_text")))}
        # The label is the pharmacy's wording where there is one (it names the product dispensed).
        named = next((r for r in rows if r.get("source") == "pharmacy"), None) or (rows[0] if rows else {})
        label, strength = named.get("med_text") or g, named.get("strength_text") or ""
        if strength and strength.casefold() not in label.casefold():
            label = f"{label} {strength}"
        out[g] = _Product(brands, strengths, families, label)
    return out


def _relevance(rec: dict[str, str | None], product: _Product) -> str | None:
    """Rank one TGA row against the patient's own product (scan S42). None means drop it.

    Different route (an injection ampoule for a patient on tablets): dropped. Same brand --
    or, when the records name no brand, the same strength -- affects this patient. Anything
    else is another product of the same medicine. `salt_quantity` is never used: it is salt
    mass, not strength.
    """
    name = rec.get("medicine_name") or ""
    family = _form_family(f"{rec.get('dosage_form') or ''} {name}")
    if family and product.families and family not in product.families:
        return None
    first = name.split()[0] if name.split() else ""
    brand = first.casefold() if first.isupper() and len(first) >= 3 else None
    if product.brands:
        return AFFECTS if brand in product.brands else OTHER_PRODUCT
    m = _TGA_STRENGTH.search(name)
    if m:
        value, unit = float(m.group(1)), m.group(2).casefold()
        mg = value / 1000 if unit in ("microgram", "mcg") else value * 1000 if unit == "g" else value
        if any(abs(mg - s) < 1e-6 for s in product.strengths):
            return AFFECTS
    return OTHER_PRODUCT


def check_shortages(ctx: AgentContext, anchor: SourceRow, current_generics: list[str],
                    stmts: list[MedStatement] | None = None,
                    raw: dict[str, dict[str, str | None]] | None = None) -> list[Notice]:
    """Q4: known TGA shortages for the medicines the patient is on. Optional (the Planner's call).

    A row is a `known_shortage` notice -- never "unavailable": the TGA database is
    incomplete, and a medicine absent from it says nothing. If the data is not there
    (SAMPLE_MODE has no recording; the view may not be registered), the run says so
    and continues.

    Each row is ranked against the patient's own product (`_relevance`, scan S42): a
    different route is dropped, and every notice carries its `relevance`. The disclaimer
    is the caller's to state once (`SHORTAGE_DISCLAIMER`), not repeated on each notice.
    """
    ctx.check_time()
    if not current_generics:
        ctx.tracer.emit("Executor", "check_shortages", step="CHECK_SHORTAGES", message="No current medicines to check.")
        return []
    sql = queries.q_shortages(current_generics)
    try:
        result, record = ctx.zetaris.run(sql, template_id="Q4", replay_key=anchor.source_patient_id)
    except QueryBudgetExceeded:
        raise
    except ReplayMiss:
        ctx.tracer.emit("Executor", "check_shortages", step="CHECK_SHORTAGES", status="skipped",
                        message="SAMPLE_MODE has no recorded shortage data; shortage check skipped.")
        return []
    except ZetarisError as exc:
        ctx.tracer.emit("Executor", "check_shortages", step="CHECK_SHORTAGES", status="skipped", error=str(exc),
                        message="Shortage overlay unavailable on this Zetaris (the TGA view may not be "
                                "registered); continuing without it.")
        return []
    products = _patient_products(current_generics, stmts or [], raw or {}, ctx.lex)
    notices: list[Notice] = []
    dropped = 0
    for rec in dicts_from_sql(result):
        g = rec.get("generic") or ""
        product = products.get(g, _Product(label=g))
        relevance = _relevance(rec, product)
        if relevance is None:
            dropped += 1
            continue
        when = f", expected to resolve {rec['expected_resolution']}" if rec.get("expected_resolution") else ""
        whose = (f"It matches the patient's product ({product.label})." if relevance == AFFECTS else
                 f"The patient's product ({product.label}) is a different one.")
        notices.append(Notice(
            type=NoticeType.KNOWN_SHORTAGE, generic=g or None, relevance=relevance,
            detail=f"Known shortage listed for {rec.get('medicine_name') or g} ({rec.get('status')}{when}). {whose}",
            tasks=[f"Check supply of {g} before discharge"] if g and relevance == AFFECTS else []))
    affects = sum(n.relevance == AFFECTS for n in notices)
    ctx.tracer.emit("Executor", "check_shortages", step="CHECK_SHORTAGES",
                    message=f"Checked {len(current_generics)} medicines for known shortages: {affects} match the "
                            f"patient's product, {len(notices) - affects} other product(s) of the same medicine, "
                            f"{dropped} dropped (different route or form).",
                    **record.trace_fields())
    return notices


def catalogue() -> list[str]:
    """The views the templates read -- what the Planner is told it can query."""
    return [queries.ALL_SOURCES_VIEW, *queries.SOURCE_VIEWS.values(), *queries.REFERENCE_VIEWS.values(),
            queries.TGA_VIEW]


__all__: list[Any] = ["catalogue", "check_shortages", "fetch_meds", "find_identities", "normalise", "raw_rows",
                      "resolve_free_text"]
