"""`triage.prioritise` -- ordering is a safety control, not presentation."""

from __future__ import annotations

from app.domain.packs.medtrace.triage import MUST_REVIEW_FLOOR, prioritise
from app.domain.packs.medtrace.types import DiscrepancyCandidate, DiscrepancyType

D = DiscrepancyType


def cand(kind=D.OMISSION, generic="famotidine", risk=None, severity="medium",
         sources=("gp", "pharmacy"), atc_class="A02B", intent="likely_unintentional"):
    return DiscrepancyCandidate(
        id=f"{kind.value}:{generic}", type=kind, generic=generic, high_risk_class=risk,
        severity=severity, sources_involved=list(sources), row_ids=["R-1"],
        detail={"atc_class": atc_class}, intent_status=intent)


def test_core_apinchs_always_outranks_everything_else() -> None:
    """However often warfarin findings have been dismissed, a warfarin finding
    is never ranked below a non-high-risk one."""
    warfarin = cand(D.DOSE_UNCONFIRMABLE, "warfarin", risk="A", severity="high",
                    atc_class="B01A")
    others = [cand(D.DOSE, "amlodipine", severity="high", sources=("gp", "pharmacy", "patient")),
              cand(D.OMISSION, "famotidine")]
    ranked = prioritise([*others, warfarin], {("dose_unconfirmable", "B01A"): 0.0})
    assert ranked[0].generic == "warfarin"
    assert ranked[0].priority >= MUST_REVIEW_FLOOR
    assert all(c.priority < MUST_REVIEW_FLOOR for c in ranked[1:])


def test_learned_acceptance_sinks_a_class_that_keeps_being_rejected() -> None:
    """Two otherwise identical findings tie and break alphabetically. Once
    omissions on ACE inhibitors (C09A) keep being rejected as clinically
    irrelevant, that one drops below the other."""
    def pair():
        return [cand(generic="aaa", atc_class="C09A"), cand(generic="zzz", atc_class="A02B")]
    assert [c.generic for c in prioritise(pair(), {})] == ["aaa", "zzz"]
    learned = {("omission", "C09A"): 0.1}
    assert [c.generic for c in prioritise(pair(), learned)] == ["zzz", "aaa"]


def test_acceptance_never_hides_a_finding() -> None:
    ranked = prioritise([cand()], {("omission", "A02B"): 0.0})
    assert len(ranked) == 1 and ranked[0].priority > 0


def test_a_documented_reason_halves_priority_but_keeps_the_item() -> None:
    plain = prioritise([cand()], {})[0].priority
    noted = prioritise([cand(intent="documented_intentional")], {})[0]
    assert noted.priority == plain / 2


def test_more_independent_sources_rank_higher() -> None:
    one = cand(generic="a", sources=("emr", "gp"))
    three = cand(generic="b", sources=("emr", "gp", "pharmacy", "patient"))
    assert [c.generic for c in prioritise([one, three], {})] == ["b", "a"]


def test_suppressed_kinds_are_dropped_even_if_a_detector_regresses() -> None:
    leaked = cand()
    leaked.detail["suppressed_as"] = "brand_only"
    assert prioritise([leaked, cand(generic="kept")], {})[0].generic == "kept"
    assert len(prioritise([leaked], {})) == 0


def test_order_is_deterministic_and_priority_is_set_in_place() -> None:
    items = [cand(generic="b"), cand(generic="a")]
    ranked = prioritise(items, {})
    assert [c.generic for c in ranked] == ["a", "b"]          # tie -> generic
    assert all(c.priority > 0 for c in items)
