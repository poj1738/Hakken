"""`safety.py`: APINCHS classification and the human-review gate.

This is the module that decides what a pharmacist is allowed to act on without
a second look, so its failure modes are asymmetric. Classifying a safe medicine
as high-risk costs attention; missing a high-risk one costs the thing the tool
exists to prevent. **APINCHS recall has a target of 100%.**
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql
from app.domain.packs.medtrace.safety import (
    UNTRUSTED_RESOLUTIONS,
    forced_confirm,
    high_risk_class,
    safety_gate,
)
from app.domain.packs.medtrace.types import DiscrepancyCandidate, DiscrepancyType

FIXTURES = pathlib.Path("tests/fixtures/medtrace")

pytestmark = pytest.mark.skipif(
    not (FIXTURES / "Q_REF__apinchs.json").exists(), reason="run `make lexicon` first"
)


@pytest.fixture(scope="module")
def lex():
    load = lambda n: dicts_from_sql(json.loads((FIXTURES / f"Q_REF__{n}.json").read_text()))
    return build_lexicon(load("lexicon"), load("apinchs"), load("nicknames"))


def candidate(**kwargs) -> DiscrepancyCandidate:
    base = {"id": "D0001", "type": DiscrepancyType.OMISSION, "generic": "apixaban",
            "row_ids": ["GP-000001"]}
    return DiscrepancyCandidate(**(base | kwargs))


# --------------------------------------------------------------------------- #
# APINCHS classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("atc", "expected"), [
    ("B01AA03", "H"),    # warfarin -- vitamin K antagonist
    ("B01AF02", "H"),    # apixaban -- factor Xa inhibitor
    ("B01AE07", "H"),    # dabigatran
    ("A10AE04", "I"),    # insulin glargine -- long-acting
    ("A10AB05", "I"),    # insulin aspart -- fast-acting
    ("N02AA05", "N"),    # oxycodone
    ("N02AE01", "N"),    # buprenorphine
    ("N05CD07", "N"),    # temazepam
    ("L04AX03", "C"),    # oral methotrexate
    ("A10BB09", "Ext"),  # gliclazide -- sulfonylurea extension
    ("C01AA05", "Ext"),  # digoxin extension
    ("C10AA05", None),   # atorvastatin -- not high-risk
    ("H03AA01", None),   # levothyroxine -- not APINCHS
    # DATA_SPEC 10.1's documented exception: high-risk for dose_unconfirmable
    # only, so a distinct label rather than a core APINCHS class.
    ("H02AB06", "steroid_taper_ext"),
    (None, None),
    ("", None),
])
def test_high_risk_class(lex, atc, expected) -> None:
    assert high_risk_class(atc, lex) == expected


def test_the_most_specific_prefix_wins(lex) -> None:
    """`A10AB` (fast-acting insulin) must beat a broader `A10`, or every insulin
    collapses into one class and the specific rule never fires."""
    assert high_risk_class("A10AB05", lex) == "I"
    assert high_risk_class("A10AE04", lex) == "I"
    # A10BK is an SGLT2 inhibitor -- in neither the insulin nor the SU rule.
    assert high_risk_class("A10BK03", lex) is None


def test_case_and_whitespace_do_not_defeat_classification(lex) -> None:
    """A code arrives as a string from a view; a stray space must not silently
    turn a high-risk medicine into an unclassified one."""
    assert high_risk_class(" b01aa03 ", lex) == "H"


def test_none_means_unclassified_not_safe(lex) -> None:
    """Nothing downstream may read a `None` as permission to demote. This test
    exists to pin the docstring's claim, because the two readings differ only in
    consequence."""
    assert high_risk_class("Z99ZZ99", lex) is None


def test_every_high_risk_medicine_in_our_lexicon_classifies(lex) -> None:
    """Our own reference data marks medicines high-risk independently of ATC. If
    a marked medicine does not match any APINCHS prefix, APINCHS recall cannot
    reach 100% -- and it would fail silently."""
    import csv

    src = pathlib.Path("data/reference_src/medicines.csv")
    if not src.exists():
        pytest.skip("reference source not present")
    with src.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r["high_risk"] or "").strip() in ("Y", "ext")]
    assert rows
    unclassified = [(r["generic"], r["atc"]) for r in rows
                    if high_risk_class(r["atc"], lex) is None]
    assert not unclassified, f"marked high-risk but matches no APINCHS prefix: {unclassified}"


# --------------------------------------------------------------------------- #
# forced_confirm
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("generic,atc", [
    ("warfarin", "B01AA03"),
    ("insulin glargine", "A10AE04"),
    ("insulin aspart", "A10AB05"),
    ("prednisolone", "H02AB06"),
])
def test_dose_changes_without_a_script_always_force_a_task(generic, atc) -> None:
    """These change dose by phone call, so every source can be internally
    consistent and all of them stale. Agreement is not evidence here, which is
    why this is independent of discrepancy detection."""
    task = forced_confirm(generic, atc)
    assert task and "onfirm" in task


def test_an_unlisted_insulin_is_still_caught_by_atc() -> None:
    """A generic string we do not recognise must not slip through -- the ATC
    prefix is the backstop."""
    assert forced_confirm("insulin degludec", "A10AE06") is not None
    assert forced_confirm("acenocoumarol", "B01AA07") is not None


def test_an_ordinary_medicine_forces_nothing() -> None:
    assert forced_confirm("atorvastatin", "C10AA05") is None
    assert forced_confirm("pantoprazole", "A02BC02") is None
    assert forced_confirm("", None) is None


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def test_a_finding_with_no_row_ids_is_blocked() -> None:
    """An unciteable finding is indistinguishable from a hallucinated one, so it
    is not shown as a finding at all."""
    result = safety_gate(candidate(row_ids=[]))
    assert result.decision == "blocked"
    assert "row_ids" in result.reason


def test_a_high_risk_finding_needs_a_pharmacist() -> None:
    result = safety_gate(candidate(high_risk_class="H"))
    assert result.decision == "needs_pharmacist"
    assert "APINCHS H" in result.reason


@pytest.mark.parametrize("resolution", sorted(UNTRUSTED_RESOLUTIONS))
def test_a_finding_resting_on_an_unverified_name_needs_a_pharmacist(resolution) -> None:
    """`llm` and `unmapped` mean the medicine's identity is a guess. A finding
    built on a guess may be shown, but never actioned silently."""
    result = safety_gate(candidate(detail={"resolution": resolution}))
    assert result.decision == "needs_pharmacist"
    assert result.required_tasks


def test_a_finding_resting_on_a_review_band_link_needs_a_pharmacist() -> None:
    """If we are not sure it is the same person, we are not sure of the finding."""
    result = safety_gate(candidate(detail={"identity_band": "review"}))
    assert result.decision == "needs_pharmacist"
    assert any("same person" in t for t in result.required_tasks)


def test_an_auto_merge_band_does_not_force_review() -> None:
    assert safety_gate(candidate(detail={"identity_band": "auto-merge"})).decision == "allow"


def test_an_identity_uncertain_finding_always_needs_a_pharmacist() -> None:
    result = safety_gate(candidate(type=DiscrepancyType.IDENTITY_UNCERTAIN))
    assert result.decision == "needs_pharmacist"


def test_an_ordinary_cited_finding_is_allowed_but_still_a_draft() -> None:
    result = safety_gate(candidate())
    assert result.decision == "allow"
    assert "draft" in result.reason


def test_reasons_accumulate_rather_than_the_first_one_winning() -> None:
    """A finding can be high-risk *and* llm-resolved *and* identity-uncertain.
    Showing only the first reason would understate why it needs a human."""
    result = safety_gate(candidate(high_risk_class="H",
                                   detail={"resolution": "llm", "identity_band": "review"}))
    assert result.decision == "needs_pharmacist"
    assert result.reason.count(";") >= 2
    assert len(result.required_tasks) == 2


def test_an_unciteable_high_risk_finding_is_blocked_not_escalated() -> None:
    """Blocking takes precedence: we cannot ask a pharmacist to review evidence
    we cannot show them."""
    assert safety_gate(candidate(row_ids=[], high_risk_class="H")).decision == "blocked"
