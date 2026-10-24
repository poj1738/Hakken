"""`fuse` -- trust-weighted resolution into the BPMH grid."""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.packs.medtrace.fuse import fuse
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.domain.packs.medtrace.types import EvidenceState, MedStatement

ADMITTED = date(2026, 10, 24)
P, A, U = EvidenceState.PRESENT, EvidenceState.ABSENT_IN_SCOPE, EvidenceState.UNKNOWN
TRUST = dict(SOURCE_TRUST_PRIORS)


def stmt(source, dose=None, freq=None, status="active", doc_date=ADMITTED, row_id=None,
         generic="amlodipine", release="IR", days_supply=None) -> MedStatement:
    return MedStatement(source=source, row_id=row_id or f"{source.upper()}-1",
                        raw_text=generic, generic=generic, ingredients=[(generic, None)],
                        daily_dose_mg=dose, frequency=freq, status=status,
                        doc_date=doc_date, release=release, days_supply=days_supply)


def chart(dose, **kw):
    return stmt("emr", dose=dose, row_id="EMR-CHART", **kw)


def gp(dose, **kw):
    return stmt("gp", dose=dose, doc_date=ADMITTED - timedelta(days=60), row_id="GP-1", **kw)


def fill(dose, days_ago=20, row_id="PHM-1", **kw):
    return stmt("pharmacy", dose=dose, doc_date=ADMITTED - timedelta(days=days_ago),
                row_id=row_id, days_supply=30, **kw)


def one(stmts, evidence, trust=TRUST, margin=0.2):
    fused = fuse(stmts, {"amlodipine": evidence}, trust, ADMITTED, margin)
    assert len(fused) == 1
    return fused[0]


def test_an_uncontested_attribute_resolves_with_full_margin() -> None:
    med = one([gp(5.0)], {"gp": P})
    assert med.attributes["daily_dose"].value == 5.0
    assert med.attributes["daily_dose"].margin == 1.0
    assert not med.attributes["daily_dose"].abstained


def test_the_admission_chart_does_not_vote_on_its_own_audit() -> None:
    """The BPMH is pre-admission history; the chart is what gets reconciled
    against it. A chart error of 2.5 mg against a pharmacy supply of 5 mg used to
    resolve to 2.5 mg, because the chart outweighed a six-week-old fill."""
    med = one([chart(2.5), fill(5.0, days_ago=43)], {"emr": P, "pharmacy": P})
    assert med.attributes["daily_dose"].value == 5.0
    assert med.attributes["daily_dose"].supporting == ["pharmacy"]
    # ...but the grid still records that the chart has it.
    assert med.per_source["emr"] is P


def test_a_close_call_abstains_and_keeps_both_sides() -> None:
    """GP and patient asserting different doses with similar weight is a
    conflict to resolve, not a winner to announce."""
    trust = TRUST | {("gp", "daily_dose"): 0.5, ("patient", "daily_dose"): 0.5}
    med = one([stmt("gp", dose=5.0, row_id="GP-1"), stmt("patient", dose=10.0, row_id="PAT-1")],
              {"gp": P, "patient": P}, trust)
    value = med.attributes["daily_dose"]
    assert value.abstained
    assert value.value is None
    assert set(value.dissenting) == {"gp", "patient"}
    assert "daily_dose" in med.abstained


def test_an_unknown_source_contributes_nothing() -> None:
    """Weighting a source we never read would be inventing evidence."""
    med = one([gp(5.0), stmt("patient", dose=10.0, row_id="PAT-1")], {"gp": P, "patient": U})
    assert med.attributes["daily_dose"].value == 5.0
    assert "patient" not in med.attributes["daily_dose"].dissenting


def test_a_ceased_listing_votes_against_existence_and_has_no_say_over_dose() -> None:
    med = one([gp(2.5, status="ceased"), fill(5.0)], {"gp": A, "pharmacy": P})
    assert med.attributes["existence"].dissenting.get("gp") == "absent"
    assert med.attributes["daily_dose"].value == 5.0
    assert "gp" not in med.attributes["daily_dose"].dissenting


def test_a_lapsed_supply_votes_against_existence() -> None:
    """Dispensed once, 300 days ago, 30-day supply: well past the 90-day grace."""
    med = one([fill(5.0, days_ago=300)], {"pharmacy": P})
    assert med.attributes["existence"].value == "absent"


def test_learned_trust_changes_the_answer() -> None:
    """The H-MEM demo depends on this: a pharmacist rejects a GP dose as
    outdated, the GP's trust for daily_dose drops, and the next patient's
    conflict resolves the other way."""
    stmts = [stmt("gp", dose=5.0, row_id="GP-1"), stmt("patient", dose=10.0, row_id="PAT-1")]
    evidence = {"gp": P, "patient": P}
    before = one(stmts, evidence, TRUST)
    after = one(stmts, evidence, TRUST | {("gp", "daily_dose"): 0.05})
    assert before.attributes["daily_dose"].value == 5.0
    assert after.attributes["daily_dose"].value == 10.0


def test_old_dispensing_counts_for_less_than_recent() -> None:
    old, recent = fill(5.0, days_ago=150, row_id="PHM-OLD"), stmt(
        "patient", dose=10.0, row_id="PAT-1")
    med = one([old, recent], {"pharmacy": P, "patient": P},
              TRUST | {("pharmacy", "daily_dose"): 0.6, ("patient", "daily_dose"): 0.4})
    # 0.6 * exp(-150/180) = 0.26 < 0.4: recency outweighs the higher prior.
    assert med.attributes["daily_dose"].value == 10.0


def test_one_pharmacy_is_one_vote_however_many_fills() -> None:
    fills = [fill(5.0, days_ago=d, row_id=f"PHM-{d}") for d in (10, 40, 70, 100)]
    med = one(fills + [gp(5.0)], {"pharmacy": P, "gp": P})
    assert med.attributes["daily_dose"].supporting == ["gp", "pharmacy"]
    assert med.attributes["daily_dose"].row_ids.count("PHM-10") == 1


def test_output_is_deterministic_and_sorted_by_generic() -> None:
    stmts = [stmt("gp", generic="warfarin", dose=5.0, row_id="GP-2"), gp(5.0)]
    evidence = {"warfarin": {"gp": P}, "amlodipine": {"gp": P}}
    first = fuse(stmts, evidence, TRUST, ADMITTED)
    assert [m.generic for m in first] == ["amlodipine", "warfarin"]
    assert first == fuse(list(reversed(stmts)), evidence, TRUST, ADMITTED)
