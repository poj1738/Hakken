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

from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.domain.packs.medtrace import identity, queries
from app.domain.packs.medtrace.normalise import llm_candidates, normalise_med
from app.domain.packs.medtrace.parse import rows_from_sql
from app.domain.packs.medtrace.types import IdentityLink, MedStatement, SourceRow, SqlResult


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


def resolve_free_text(ctx: AgentContext, stmts: list[MedStatement]) -> tuple[list[MedStatement], list[str]]:
    """Returns the statements (some now `resolution="llm"`) and any confirm tasks for class-level answers."""
    ctx.check_time()
    pending = {s.row_id: (s, llm_candidates(s.raw_text, ctx.lex)) for s in stmts if s.resolution == "unmapped"}
    pending = {rid: (s, c) for rid, (s, c) in pending.items() if c.get("ingredients") or c.get("atc_classes")}
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
        "class only when the text names a class (e.g. 'blood thinner').\n" + lines)}]
    # Offline: no guessing -- every line stays unmapped and is shown as such.
    result, calls = ctx.llm.chat_json("Executor", messages, Resolutions, max_tokens=4096,
                                      offline=lambda: Resolutions(items=[]))

    by_row = {r.row_id: r for r in result.items}
    out: list[MedStatement] = []
    resolved, rejected, tasks = 0, 0, []
    for s in stmts:
        res = by_row.get(s.row_id)
        cands = pending.get(s.row_id, (None, {}))[1]
        if res is None or res.choice is None or s.row_id not in pending:
            out.append(s)
            continue
        if res.choice in cands.get("ingredients", []):
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
               + (f"; {rejected} answer(s) outside the candidate list discarded" if rejected else "") + ".")
    return out, tasks


def catalogue() -> list[str]:
    """The views the templates read -- what the Planner is told it can query."""
    return [queries.ALL_SOURCES_VIEW, *queries.SOURCE_VIEWS.values(), *queries.REFERENCE_VIEWS.values()]


__all__: list[Any] = ["catalogue", "fetch_meds", "find_identities", "normalise", "raw_rows", "resolve_free_text"]
