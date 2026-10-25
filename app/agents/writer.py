"""Writer (Nemotron, deep route): explains each finding and writes the summary.

One call for every finding: 1-2 sentences each, citing row ids, using only
numbers that appear in that finding's own rows or detail. It never says "not
taking" for an UNKNOWN source and never tells anyone to stop a medicine -- these
are drafts for a pharmacist. On a critique it rewrites only the flagged ones.

`template()` is the grounded fallback: built from the finding's own rows and
detail, so it cannot cite anything else. It is what SAMPLE_MODE uses
(`offline-heuristic`), and what replaces a model explanation that still fails
verification after the last revision round.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.domain.packs.medtrace.types import DiscrepancyType as DT
from app.domain.packs.medtrace.types import SourceRow
from app.schemas import Finding

_WHAT = {
    DT.OMISSION: "is supported before admission but is not on the admission chart",
    DT.COMMISSION: "is on the admission chart but no pre-admission source supports it",
    DT.DOSE: "has a different total daily dose on the chart than before admission",
    DT.FREQUENCY: "is charted at a different frequency than before admission",
    DT.FORMULATION: "is charted with a different release form than before admission",
    DT.ROUTE: "is charted by a different route than before admission",
    DT.DUPLICATION: "appears more than once once combination products are decomposed",
    DT.STALE_LISTING: "is listed as current but its supply ran out long ago",
    DT.DOSE_UNCONFIRMABLE: "has a dose the sources disagree on, and it changes without a new script",
    DT.UNPROPAGATED_DISCHARGE_CHANGE: "was changed at a previous discharge, but another source still shows the old state",
    DT.IDENTITY_UNCERTAIN: "rests on a record whose link to this patient is uncertain",
}


def template(f: Finding) -> str:
    rows = ", ".join(e.row_id for e in f.evidence)
    statement = f.detail.get("statement")
    body = f"{f.generic.capitalize()} {_WHAT.get(f.type, 'needs review')}"
    if isinstance(statement, str) and statement:
        body += f": {statement}"
    if f.detail.get("conflict") == "confirm":
        body += ". Ask first; do not stop it on this evidence alone"
    return f"{body} ({rows})."


class Explanation(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=600)


class Draft(BaseModel):
    explanations: list[Explanation] = Field(default_factory=list)
    summary: str = Field(default="", max_length=1200)


def _brief(f: Finding) -> dict:
    return {"id": f.id, "type": f.type.value, "generic": f.generic, "severity": f.severity,
            "high_risk_class": f.high_risk_class, "detail": f.detail,
            "source_states": {k: v.value for k, v in f.evidence_states.items()},
            "rows": {e.row_id: {k: v for k, v in e.fields.items() if v and k in
                                ("source", "med_text", "strength_text", "dose_text", "freq_text", "route_text",
                                 "status_text", "note_text", "doc_date", "qty", "days_supply")}
                     for e in f.evidence}}


def _offline_summary(findings: list[Finding], anchor: SourceRow, banner: str | None) -> str:
    must = [f for f in findings if f.needs_pharmacist]
    head = (f"{len(findings)} finding(s) for {anchor.name_given} {anchor.name_family} "
            f"({anchor.source_patient_id})")
    if must:
        head += f"; {len(must)} need a pharmacist first: " + ", ".join(f"{f.generic} ({f.type.value})" for f in must[:4])
    return head + "." + (f" {banner}" if banner else "")


def draft(ctx: AgentContext, findings: list[Finding], anchor: SourceRow, banner: str | None, *,
          problems: dict[str, list[str]] | None = None) -> tuple[dict[str, str], str | None]:
    """Returns (id -> explanation, summary). On a revision round only the flagged ids are rewritten
    and the summary is None (kept from the first round)."""
    ctx.check_time()
    targets = [f for f in findings if problems is None or f.id in problems]
    if not targets:
        return {}, None
    revising = problems is not None
    instructions = (
        "Write the explanation a hospital pharmacist sees for each finding below. Synthetic data; these are "
        "drafts a pharmacist must confirm.\nRules: 1-2 sentences each. Cite the supporting row ids in "
        "parentheses, e.g. (GP-000003). Use ONLY numbers that appear in that finding's own rows or detail. "
        "Never say the patient is 'not taking' or has 'stopped' a medicine when a source state is 'unknown'. "
        "Never instruct anyone to stop or start a medicine; say what to confirm."
    )
    if revising:
        instructions += "\nYour previous explanations had these problems; fix them:\n" + json.dumps(problems)
    else:
        instructions += ("\nAlso write a 2-3 sentence summary for the whole patient, leading with what needs a "
                         "pharmacist first." + (f" Mention this coverage caveat: {banner}" if banner else ""))
    messages = [{"role": "user", "content": instructions + "\n" + json.dumps([_brief(f) for f in targets],
                                                                             default=str)}]
    result, calls = ctx.llm.chat_json(
        # 16k: a 5-finding draft used 6,391 completion tokens live, and attempts that
        # exhausted 8k came back as `<model>_empty_response` (trace, 25 Oct).
        "Writer", messages, Draft, max_tokens=16384,
        offline=lambda: Draft(explanations=[Explanation(id=f.id, text=template(f)) for f in targets],
                              summary="" if revising else _offline_summary(findings, anchor, banner)))
    ids = {f.id for f in targets}
    texts = {e.id: e.text for e in result.explanations if e.id in ids}
    ctx.record("Writer", "revise" if revising else "draft", "DRAFT", calls,
               f"{'Revised' if revising else 'Drafted'} explanations for {len(texts)} of {len(targets)} findings.")
    return texts, (None if revising else (result.summary or _offline_summary(findings, anchor, banner)))
