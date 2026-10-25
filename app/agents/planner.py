"""Planner (Nemotron, fast route): decides what the investigation needs.

It reads the patient and the Zetaris catalogue and answers with steps, each a tool
plus the need in plain words ("get the dispensing history and GP list"). The
Executor turns each tool into one of Arpon's verified SQL templates (Option A,
25 Oct): the model decides WHAT is needed, never the SQL text.

    find_identities   -> Q1  find this patient's records in the other systems
    fetch_meds        -> Q2  read every medicine row for the linked records
    resolve_free_text -> (no SQL) lexicon candidates + one Nemotron choice
    check_shortages   -> Q4  known TGA shortages for the drafted medicines (optional)
    verify            -> Q3  re-read every cited row

The core steps (find_identities, fetch_meds, verify) are not the model's to skip:
a plan without them is completed in code and the trace says so. Optional steps
run only when the Planner chooses them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.domain.packs.medtrace.types import SourceRow

Tool = Literal["find_identities", "fetch_meds", "resolve_free_text", "check_shortages", "verify"]
CORE: tuple[Tool, ...] = ("find_identities", "fetch_meds", "verify")
ORDER: tuple[Tool, ...] = ("find_identities", "fetch_meds", "resolve_free_text", "check_shortages", "verify")
#: The SQL template each tool becomes. None: the step sends no SQL.
TEMPLATE_FOR: dict[str, str | None] = {"find_identities": "Q1", "fetch_meds": "Q2", "resolve_free_text": None,
                                       "check_shortages": "Q4", "verify": "Q3"}
DEFAULT_NEED: dict[str, str] = {
    "find_identities": "find this patient's records in the GP, pharmacy and interview systems",
    "fetch_meds": "get every medicine line, dispensing and interview answer for those records",
    "resolve_free_text": "work out what any free-text medicine lines refer to",
    "check_shortages": "check the drafted medicines against known supply shortages",
    "verify": "re-read every row the findings cite before anyone sees them",
}


class PlanStep(BaseModel):
    tool: Tool
    need: str = Field(min_length=1, max_length=200, description="what this step is for, in plain words")


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
    rationale: str = Field(min_length=1, max_length=600)

    @property
    def tools(self) -> list[str]:
        return [s.tool for s in self.steps]

    def need(self, tool: str) -> str:
        return next((s.need for s in self.steps if s.tool == tool), DEFAULT_NEED[tool])


def _offline_plan(anchor: SourceRow, budget_left: int) -> Plan:
    tools: list[Tool] = ["find_identities", "fetch_meds", "resolve_free_text", "verify"]
    return Plan(steps=[PlanStep(tool=t, need=DEFAULT_NEED[t]) for t in tools], rationale=(
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
            f"Patient: {anchor.source_patient_id}, {anchor.name_given} {anchor.name_family}, "
            f"DOB {anchor.dob_raw}, admitted {anchor.doc_date}.\n"
            f"Zetaris views you can draw on: {', '.join(catalogue)}.\n"
            f"Query budget left: {budget_left}.\n"
            "Tools: find_identities (find the patient in the other systems), fetch_meds (read their "
            "medicines and dispensings), resolve_free_text (only if lines may be free text), "
            "check_shortages (optional: known supply shortages), verify (re-read cited rows).\n"
            "Return the steps you need, each as a tool plus a short 'need' saying in plain words what you "
            "want from it, and a one-paragraph rationale."
        ),
    }]
    result, calls = ctx.llm.chat_json("Planner", messages, Plan, max_tokens=4096,
                                      offline=lambda: _offline_plan(anchor, budget_left))
    chosen = {s.tool: s for s in result.steps}
    missing = [t for t in CORE if t not in chosen]
    steps = [chosen.get(t) or PlanStep(tool=t, need=DEFAULT_NEED[t])
             for t in ORDER if t in chosen or t in CORE]
    final = Plan(steps=steps, rationale=result.rationale)
    ctx.record("Planner", "plan", "PLAN", calls,
               "Plan: " + "; ".join(f'{s.tool} ("{s.need}")' for s in steps) + f". {result.rationale}"
               + (f" (Core steps added by code: {', '.join(missing)}.)" if missing else ""))
    return final
