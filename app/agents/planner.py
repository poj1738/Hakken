"""Planner (Nemotron, fast route): plans the investigation for one patient.

It chooses which optional tool steps to run and says why. The core steps --
find identities, fetch medicines, verify -- are not the model's to skip: a plan
without them is completed in code and the trace says so. On a critique it
re-plans only the failed part (PLAN 5.5).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.domain.packs.medtrace.types import SourceRow

Tool = Literal["find_identities", "fetch_meds", "resolve_free_text", "check_shortages", "verify", "free_sql"]
CORE: tuple[Tool, ...] = ("find_identities", "fetch_meds", "verify")
ORDER: tuple[Tool, ...] = ("find_identities", "fetch_meds", "resolve_free_text", "check_shortages",
                           "free_sql", "verify")


class Plan(BaseModel):
    steps: list[Tool] = Field(min_length=1, max_length=8)
    rationale: str = Field(min_length=1, max_length=600)


def _offline_plan(anchor: SourceRow, budget_left: int) -> Plan:
    steps: list[Tool] = ["find_identities", "fetch_meds", "resolve_free_text", "verify"]
    return Plan(steps=steps, rationale=(
        f"Standard reconciliation for {anchor.name_given} {anchor.name_family}: link the patient across "
        f"GP, pharmacy and interview records, read their medicines in one query, resolve any free-text "
        f"lines from the lexicon, then verify every cited row. {budget_left} queries available."))


def plan(ctx: AgentContext, anchor: SourceRow, catalogue: list[str], budget_left: int) -> Plan:
    """One call. Returns the plan with the core steps guaranteed, in a safe order."""
    ctx.check_time()
    messages = [{
        "role": "user",
        "content": (
            "You plan a medication reconciliation for one admitted patient. Synthetic data; a pharmacist "
            "confirms everything.\n"
            f"Patient: {anchor.name_given} {anchor.name_family}, DOB {anchor.dob_raw}, admitted {anchor.doc_date}.\n"
            f"Zetaris views available: {', '.join(catalogue)}.\n"
            f"Query budget left: {budget_left}.\n"
            "Tools: find_identities, fetch_meds, resolve_free_text (only if some medicine lines may be free "
            "text), check_shortages (optional, known-shortage overlay), verify, free_sql (avoid; budgeted).\n"
            "Return the steps to run and a one-paragraph rationale."
        ),
    }]
    result, calls = ctx.llm.chat_json("Planner", messages, Plan, max_tokens=4096,
                                      offline=lambda: _offline_plan(anchor, budget_left))
    missing = [s for s in CORE if s not in result.steps]
    steps = [s for s in ORDER if s in set(result.steps) | set(CORE)]
    ctx.record("Planner", "plan", "PLAN", calls,
               f"Plan: {', '.join(steps)}. {result.rationale}"
               + (f" (Core steps added by code: {', '.join(missing)}.)" if missing else ""))
    return Plan(steps=steps, rationale=result.rationale)
