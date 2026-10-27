"""Feedback to learning (PLAN 5.7), through the H-MEM engine.

A pharmacist's verdict on a finding becomes `HMEM.feedback()` on the `(source, attribute)`
trust records behind it -- the engine's exact deltas and clamps, a `review` tag on
`wrong`, and a ledger entry -- and the next run's `fuse()` reads that trust. The verdict
itself is also remembered, so the Planner can recall it:

  confirm                                    -> helpful      +0.05
  reject: source_outdated | wrong_patient    -> wrong        -0.20  on THAT (source, attribute)
  reject: anything else                      -> not_helpful  -0.03
  intentional_change | not_clinically_relevant also lower the acceptance rate per
  (type, ATC class) that `triage.prioritise` multiplies in.

The learning demo (TODO_ARNAV, `tests/unit/test_learning_demo.py`): reject P0003's GP
dose as `source_outdated` with `source="gp"`, `attribute="daily_dose"` -> GP
`daily_dose` 0.70 -> 0.50 -> P0007 then resolves rosuvastatin to the pharmacy's dose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.packs.medtrace.types import DiscrepancyType as DT
from app.schemas import AcceptanceUpdate, FeedbackRequest, FeedbackResponse, Finding, TrustUpdate

if TYPE_CHECKING:
    from app.orchestrator import Orchestrator

ACCEPTANCE_STEP = 0.10
ACCEPTANCE_FLOOR = 0.10
_DOSE_TYPES = {DT.DOSE, DT.DOSE_UNCONFIRMABLE, DT.FREQUENCY}


class FeedbackError(ValueError):
    pass


def _attribute_for(f: Finding) -> str:
    """Which attribute a verdict on this finding is about, when the request does not say."""
    if f.type in _DOSE_TYPES:
        return "daily_dose"
    if f.type == DT.FORMULATION:
        return "release"
    if f.type == DT.ROUTE:
        return "route"
    return "existence"


def apply_feedback(orch: Orchestrator, req: FeedbackRequest) -> FeedbackResponse:
    """Apply a verdict once. The same verdict again -- a double-click, a UI retry -- returns the
    first response and moves nothing (scan S31: four repeats used to take GP daily-dose trust
    from 0.70 to 0.0, and the learning demo's documented 0.70 -> 0.50 step was gone). A
    different verdict or reason on the same target is a new decision and does apply."""
    key = (req.run_id, req.target_id, req.verdict, req.reason, req.source, req.attribute)
    with orch.feedback_lock:
        if key in orch.feedback_applied:
            return orch.feedback_applied[key]
        result = _apply(orch, req)
        orch.feedback_applied[key] = result
        return result


def _apply(orch: Orchestrator, req: FeedbackRequest) -> FeedbackResponse:
    response = orch.get(req.run_id)
    if response is None:
        raise FeedbackError(f"unknown run {req.run_id}")
    if req.target_id.startswith("grid:"):
        return _grid_feedback(orch, req, response)
    finding = next((f for f in response.findings if f.id == req.target_id), None)
    if finding is None:
        raise FeedbackError(f"{req.target_id} is not a finding of {req.run_id}")

    kind = _kind(req)
    attribute = req.attribute or _attribute_for(finding)
    if req.source is not None:
        sources = [req.source]  # source_outdated names exactly one record (schema-enforced)
    else:
        sources = sorted({e.source for e in finding.evidence if e.source} - {"emr"})
    # A pair with no prior is skipped: nothing to learn into, and nothing is invented.
    updates = [u for s in sources if (u := _move(orch, s, attribute, kind))]
    _remember(orch, req, response, f"{finding.type.value} finding on {finding.generic}", attribute, sources)

    acceptance: list[AcceptanceUpdate] = []
    if req.reason in ("intentional_change", "not_clinically_relevant"):
        atc_class = str(finding.detail.get("atc_class") or "")
        key = (finding.type.value, atc_class)
        before = orch.acceptance.get(key, 1.0)
        after = round(max(ACCEPTANCE_FLOOR, before - ACCEPTANCE_STEP), 4)
        orch.acceptance[key] = after
        acceptance.append(AcceptanceUpdate(type=finding.type, atc_class=atc_class, before=before, after=after))

    return FeedbackResponse(run_id=req.run_id, target_id=req.target_id, verdict=req.verdict, reason=req.reason,
                            trust_updates=updates, acceptance_updates=acceptance)


def _kind(req: FeedbackRequest) -> str:
    if req.verdict == "confirm":
        return "helpful"
    return "wrong" if req.reason in ("source_outdated", "wrong_patient") else "not_helpful"


def _move(orch: Orchestrator, source: str, attribute: str, kind: str) -> TrustUpdate | None:
    moved = orch.memory.feedback(source, attribute, kind)
    if moved is None:
        return None
    record_id, before, after = moved
    return TrustUpdate(source=source, attribute=attribute, hmem_record_id=record_id,
                       kind=kind, before=before, after=after, delta=round(after - before, 4))


def _remember(orch: Orchestrator, req: FeedbackRequest, response, target: str, attribute: str,
              sources: list[str]) -> None:
    verdict = "confirmed" if req.verdict == "confirm" else f"rejected ({req.reason})"
    where = ", ".join(sources) or "no source"
    orch.memory.remember_verdict(
        f"Pharmacist {verdict} the {target} for patient {response.patient_id}; {where} {attribute.replace('_', ' ')}",
        source=sources[0] if len(sources) == 1 else None, reason=req.reason)


def _grid_feedback(orch: Orchestrator, req: FeedbackRequest, response) -> FeedbackResponse:
    """`grid:<generic>:<attribute>` -- a verdict on one BPMH cell, e.g. an abstained dose.

    This is the learning demo's step 1: P0003's candesartan dose abstains, so there is no
    finding to reject, and the pharmacist rejects the GP value in the grid instead.
    """
    try:
        _, generic, attribute = req.target_id.split(":", 2)
    except ValueError as exc:
        raise FeedbackError("a grid target is grid:<generic>:<attribute>") from exc
    med = next((m for m in response.grid if m.generic == generic), None)
    if med is None:
        raise FeedbackError(f"{generic} is not in the grid of {req.run_id}")
    attribute = req.attribute or attribute
    if req.source is not None:
        sources = [req.source]
    else:
        cell = med.attributes.get(attribute)
        sources = sorted(set(cell.supporting if cell else []) - {"emr"})
    kind = _kind(req)
    updates = [u for s in sources if (u := _move(orch, s, attribute, kind))]
    _remember(orch, req, response, f"{generic} {attribute.replace('_', ' ')} in the grid", attribute, sources)
    return FeedbackResponse(run_id=req.run_id, target_id=req.target_id, verdict=req.verdict, reason=req.reason,
                            trust_updates=updates)
