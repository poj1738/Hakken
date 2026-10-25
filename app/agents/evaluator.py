"""Evaluator (code first): fuse, detect, gate, rank -- then verify and critique.

  FUSE / DETECT / PRIORITISE  Arpon's pack, in `scripts/eval.py:reconcile()` order,
      plus the three things the pack leaves to us (TODO_ARNAV 1): the grid's
      `high_risk_class` from `safety.high_risk_class`, the dose-confirmation task
      lane from `safety.forced_confirm` for EVERY current medicine, and
      `safety.safety_gate` per candidate (blocked candidates are never shown).
  VERIFY  ONE Q3 for every cited row (DECISIONS: batch, never one query per claim).
      A finding whose rows Zetaris no longer returns, or whose cited values differ,
      is blocked. Every number in an explanation must appear in that finding's own
      evidence or detail; every row id it cites must be its own.
  CRITIQUE  The same rules as code, plus a Nemotron read of every sentence in live
      mode. Problems go back to the Writer (at most MAX_AGENT_ITERATIONS rounds).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.domain.packs.medtrace import coverage as cov_mod
from app.domain.packs.medtrace import queries
from app.domain.packs.medtrace.detect import detect_discrepancies
from app.domain.packs.medtrace.fuse import fuse
from app.domain.packs.medtrace.safety import forced_confirm, high_risk_class, safety_gate
from app.domain.packs.medtrace.triage import prioritise
from app.domain.packs.medtrace.types import (
    SOURCES,
    Coverage,
    DiscrepancyCandidate,
    EvidenceState,
    FusedMed,
    IdentityLink,
    MedStatement,
    Notice,
    NoticeType,
    SourceRow,
)
from app.schemas import Evidence, Finding

_ROW_ID = re.compile(r"\b(?:EMR|GP|PHM|PAT)-[A-Za-z0-9]+\b")
_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
_NOT_TAKING = re.compile(r"\b(not taking|no longer tak|stopped taking|has stopped|discontinued by the patient)",
                         re.IGNORECASE)


@dataclass
class Analysis:
    cov: dict[str, Coverage]
    evidence: dict[str, dict[str, EvidenceState]]
    fused: list[FusedMed]
    findings: list[Finding]
    notices: list[Notice]
    tasks: list[str]
    bpmh_confirmable: bool
    banner: str | None
    blocked: list[str] = field(default_factory=list)


def _current(med: FusedMed) -> bool:
    existence = med.attributes.get("existence")
    if existence is not None and str(existence.value).casefold() == "absent":
        return False
    return any(state == EvidenceState.PRESENT for state in med.per_source.values())


def _notices(cov, fused, stmts, as_of, confirmable, banner) -> list[Notice]:
    out: list[Notice] = []
    for source in SOURCES:
        c = cov.get(source)
        if c is not None and c.state == "not_found":
            out.append(Notice(type=NoticeType.COVERAGE_GAP, source=source, detail=f"{source}: no record found.",
                              tasks=[{"gp": "Call GP practice", "pharmacy": "Ask the patient which pharmacy they use",
                                      "patient": "Interview the patient or carer"}.get(source, f"Find the {source} record")]))
    if not confirmable:
        out.append(Notice(type=NoticeType.BPMH_NOT_CONFIRMABLE, detail=banner or "BPMH not confirmable."))
    reasons = cov_mod.possible_second_pharmacy(stmts, cov, as_of)
    if reasons:
        out.append(Notice(type=NoticeType.POSSIBLE_SECOND_PHARMACY, source="pharmacy", detail=" ".join(reasons),
                          tasks=["Ask the patient about other pharmacies"]))
    for med in fused:
        if med.abstained:
            out.append(Notice(type=NoticeType.CONFLICT_ABSTAINED, generic=med.generic, row_ids=med.row_ids,
                              detail=f"{med.generic} {', '.join(med.abstained)}: sources disagree within the "
                                     "margin. Conflict: ask patient."))
        present = {s for s, st in med.per_source.items() if st == EvidenceState.PRESENT}
        if present == {"patient"}:
            out.append(Notice(type=NoticeType.PATIENT_ONLY_ITEM, source="patient", generic=med.generic,
                              row_ids=med.row_ids, detail=f"{med.generic} is reported only by the patient; kept, "
                                                          "verify the dose.", tasks=[f"Verify the {med.generic} dose"]))
    for source, c in cov.items():
        for note in c.scope_notes:
            if "updated" in note.casefold() and "month" in note.casefold():
                out.append(Notice(type=NoticeType.STALE_DOCUMENT, source=source, detail=note))
    return out


def analyse(ctx: AgentContext, links: list[IdentityLink], rows: list[SourceRow], stmts: list[MedStatement],
            raw: dict[str, dict[str, str | None]], q2_query_id: str, trust: dict[tuple[str, str], float],
            acceptance: dict[tuple[str, str], float]) -> Analysis:
    ctx.check_time()
    cov = cov_mod.coverage(links, rows)
    generics = sorted({s.generic for s in stmts if s.generic})
    evidence = {g: {src: cov_mod.evidence_state(g, src, cov[src], stmts) for src in SOURCES} for g in generics}
    fused = [m.model_copy(update={"high_risk_class": m.high_risk_class or high_risk_class(m.atc, ctx.lex)})
             for m in fuse(stmts, evidence, trust, ctx.as_of)]
    abstained = [m.generic for m in fused if m.abstained]
    ctx.tracer.emit("Evaluator", "fuse", step="FUSE",
                    message=f"Built the BPMH grid: {len(fused)} medicines"
                            + (f"; abstained on {', '.join(abstained)} (sources disagree: ask patient)" if abstained else "")
                            + ".")

    cands = detect_discrepancies(fused, stmts, cov, ctx.as_of, ctx.lex)
    gated: list[tuple[DiscrepancyCandidate, object]] = []
    blocked: list[str] = []
    for c in cands:
        gate = safety_gate(c)
        if gate.decision == "blocked":
            blocked.append(f"{c.type.value} {c.generic}: {gate.reason}")
            continue
        gated.append((c, gate))
    ranked = prioritise([c for c, _ in gated], acceptance)
    gates = {id(c): g for c, g in gated}
    ctx.tracer.emit("Evaluator", "detect", step="DETECT",
                    message=f"{len(cands)} candidate discrepancies; {len(blocked)} blocked by the safety gate "
                            f"(no citable rows).")

    findings: list[Finding] = []
    for c in ranked:
        gate = gates[id(c)]
        findings.append(Finding(
            id=c.id, type=c.type, generic=c.generic, high_risk_class=c.high_risk_class, severity=c.severity,
            intent_status=c.intent_status, intent_reason=c.detail.get("reason") if c.intent_status ==
            "documented_intentional" else None, priority=c.priority, detail=dict(c.detail),
            evidence=[Evidence(source=raw[r].get("source") or "", row_id=r, sql_template_id="Q2",
                               query_id=q2_query_id, fields=raw[r]) for r in c.row_ids if r in raw],
            evidence_states=evidence.get(c.generic, {}),
            tasks=list(dict.fromkeys([*c.tasks, *gate.required_tasks])),
            needs_pharmacist=gate.decision == "needs_pharmacist",
            trust_explanation=[f"{s} {a} trust {v:.2f}" for (s, a), v in sorted(trust.items())
                               if s in c.sources_involved and a in ("existence", "daily_dose")],
        ))
    must = sum(1 for f in findings if f.needs_pharmacist)
    ctx.tracer.emit("Evaluator", "prioritise", step="PRIORITISE",
                    message=f"Ranked {len(findings)} findings; {must} need a pharmacist's tick.")

    confirmable, banner = cov_mod.bpmh_confirmable(cov)
    notices = _notices(cov, fused, stmts, ctx.as_of, confirmable, banner or None)
    dose_lane = [t for m in fused if _current(m) and (t := forced_confirm(m.generic, m.atc))]
    tasks = list(dict.fromkeys([*dose_lane, *(t for f in findings for t in f.tasks),
                                *(t for n in notices for t in n.tasks)]))
    return Analysis(cov=cov, evidence=evidence, fused=fused, findings=findings, notices=notices, tasks=tasks,
                    bpmh_confirmable=confirmable, banner=banner or None, blocked=blocked)


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER.findall(_ROW_ID.sub(" ", text))}


def claim_problems(f: Finding) -> list[str]:
    """The code half of the critique: what is wrong with this explanation, if anything."""
    text = f.explanation or ""
    own = {e.row_id for e in f.evidence}
    problems: list[str] = []
    cited = set(_ROW_ID.findall(text))
    if not cited & own:
        problems.append("cites none of its own rows")
    if cited - own:
        problems.append(f"cites rows that are not its evidence: {sorted(cited - own)}")
    allowed = _numbers(json.dumps([e.fields for e in f.evidence]) + " " + json.dumps(f.detail, default=str)
                       + " " + f.generic)
    unsupported = sorted(n for n in _numbers(text) if n not in allowed)
    if unsupported:
        problems.append(f"numbers not in the evidence: {unsupported}")
    if any(s == EvidenceState.UNKNOWN for s in f.evidence_states.values()) and _NOT_TAKING.search(text):
        problems.append("says 'not taking' where a source is UNKNOWN")
    return problems


def verify(ctx: AgentContext, findings: list[Finding], anchor: SourceRow) -> tuple[list[Finding], list[str], str]:
    """ONE Q3 re-reads every cited row; findings Zetaris no longer supports are blocked.

    Returns (verified findings, blocked descriptions, the Q3 SQL).
    """
    ctx.check_time()
    cited = sorted({e.row_id for f in findings for e in f.evidence})
    if not cited:
        ctx.tracer.emit("Evaluator", "verify", step="VERIFY", message="Nothing to verify: no cited rows.")
        return findings, [], ""
    sql = queries.q_verify_rows(cited)
    result, record = ctx.zetaris.run(sql, template_id="Q3", replay_key=anchor.source_patient_id)
    headers = list(result["headers"])
    live = {}
    for row in result["data"]:
        rec = {h: (None if v is None else str(v)) for h, v in zip(headers, row)}
        if rec.get("row_id") in cited:
            live[rec["row_id"]] = rec
    kept: list[Finding] = []
    blocked: list[str] = []
    for f in findings:
        missing = [e.row_id for e in f.evidence if e.row_id not in live]
        changed = [e.row_id for e in f.evidence if e.row_id in live and
                   any(live[e.row_id].get(k) != v for k, v in e.fields.items() if k in live[e.row_id])]
        if missing or changed:
            blocked.append(f"{f.id} {f.generic}: rows {'missing ' + str(missing) if missing else ''}"
                           f"{' changed ' + str(changed) if changed else ''} on re-read")
        else:
            kept.append(f)
    ctx.tracer.emit("Evaluator", "verify", step="VERIFY",
                    message=f"Re-read {len(cited)} cited rows in one query; {len(kept)} findings verified"
                            + (f", {len(blocked)} blocked" if blocked else "") + ".",
                    **{**record.trace_fields(), "row_count": len(live)})
    for b in blocked:
        ctx.tracer.emit("Evaluator", "verify", step="VERIFY", status="blocked",
                        message=f"Verifier blocked an unsupported finding: {b}")
    return kept, blocked, sql


class Verdict(BaseModel):
    id: str
    faithful: bool
    issue: str = Field(default="", max_length=400)


class Critique(BaseModel):
    """A verdict for EVERY finding. Asking for "problems" alone made the model list the
    clinical findings themselves as problems (live, 25 Oct); a forced boolean does not."""

    verdicts: list[Verdict] = Field(default_factory=list)


def critique(ctx: AgentContext, findings: list[Finding]) -> dict[str, list[str]]:
    """Code rules always; a Nemotron read of every sentence in live mode. Returns id -> problems."""
    ctx.check_time()
    problems = {f.id: p for f in findings if (p := claim_problems(f))}
    if not findings:
        return problems
    brief = [{"id": f.id, "type": f.type.value, "generic": f.generic, "explanation": f.explanation,
              "cited_rows": {e.row_id: {k: v for k, v in e.fields.items() if v and k in
                                        ("source", "med_text", "strength_text", "dose_text", "freq_text",
                                         "status_text", "note_text", "doc_date", "qty", "days_supply")}
                             for e in f.evidence},
              "source_states": {k: v.value for k, v in f.evidence_states.items()}} for f in findings]
    messages = [{"role": "user", "content": (
        "You check TEXT against DATA. You are not assessing the patient, and a clinical concern is not a "
        "problem: every finding below is already a confirmed discrepancy. For EACH finding return a verdict: "
        "faithful=true if every statement in its 'explanation' is supported by its own 'cited_rows' or is a "
        "neutral request to confirm something; faithful=false only if the text states a fact, number, date or "
        "source that its rows do not show, says the patient is 'not taking' or has 'stopped' a medicine where a "
        "source state is 'unknown', or tells someone to stop a medicine. When false, 'issue' names the "
        "unsupported words.\n" + json.dumps(brief, default=str))}]
    # 4k ran out live: three `<model>_empty_response` 502s (trace, 25 Oct).
    result, calls = ctx.llm.chat_json(
        "Evaluator", messages, Critique, max_tokens=8192,
        offline=lambda: Critique(verdicts=[Verdict(id=f.id, faithful=True) for f in findings]))
    ids = {f.id for f in findings}
    for v in result.verdicts:
        if v.id in ids and not v.faithful:
            problems.setdefault(v.id, []).append(v.issue or "model verifier: unfaithful")
    ctx.record("Evaluator", "critique", "CRITIQUE", calls,
               f"Critique: {len(problems)} of {len(findings)} explanations need revision"
               if problems else "Critique: every sentence maps to a finding with evidence.")
    return problems
