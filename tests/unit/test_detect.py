"""`detect_discrepancies` -- what counts as a finding, and what never does.

Each test builds statements, runs the real `evidence_state` and `fuse`, and then
detects -- so these pin behaviour through the same chain the orchestrator uses.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.packs.medtrace.coverage import evidence_state
from app.domain.packs.medtrace.detect import detect_discrepancies
from app.domain.packs.medtrace.fuse import fuse
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.domain.packs.medtrace.types import (
    SOURCES,
    Coverage,
    DiscrepancyType,
    Lexicon,
    MedStatement,
)

ADMITTED = date(2026, 10, 24)
LEX = Lexicon()
D = DiscrepancyType
_ids: dict[str, int] = {}


def s(source, generic, dose=None, freq="1 daily", status="active", days_ago=0,
      ingredients=None, release="IR", qty=None, days_supply=None, note=None,
      script_type=None, atc=None) -> MedStatement:
    _ids[source] = _ids.get(source, 0) + 1
    if source == "emr" and days_ago == 0:
        status = "unknown"            # the admission chart carries no status
    if source == "pharmacy":
        freq = None                   # dispensing has no directions
        status = "unknown"
    return MedStatement(
        source=source, row_id=f"{source.upper()}-{_ids[source]:03d}", raw_text=generic,
        generic=generic, ingredients=ingredients or [(generic, None)], atc=atc,
        daily_dose_mg=dose, frequency=freq, status=status, release=release,
        doc_date=ADMITTED - timedelta(days=days_ago), qty=qty, days_supply=days_supply,
        note_text=note, script_type=script_type)


def chart(generic, dose=None, freq="1 daily", **kw):
    return s("emr", generic, dose, freq, **kw)


def gp(generic, dose=None, freq="1 daily", **kw):
    return s("gp", generic, dose, freq, days_ago=60, **kw)


def fill(generic, dose=None, days_ago=20, qty=30, days_supply=30, **kw):
    return s("pharmacy", generic, dose, days_ago=days_ago, qty=qty, days_supply=days_supply, **kw)


def patient(generic, status="active", **kw):
    return s("patient", generic, status=status, **kw)


def run(stmts, found=("emr", "gp", "pharmacy", "patient")):
    cov = {src: Coverage(source=src, state="found" if src in found else "not_found")
           for src in SOURCES}
    generics = sorted({x.generic for x in stmts if x.generic})
    evidence = {g: {src: evidence_state(g, src, cov[src], stmts) for src in SOURCES}
                for g in generics}
    fused = fuse(stmts, evidence, dict(SOURCE_TRUST_PRIORS), ADMITTED)
    return detect_discrepancies(fused, stmts, cov, ADMITTED, LEX)


def kinds(findings, generic=None):
    return {(f.type, f.generic) for f in findings if generic is None or f.generic == generic}


# --------------------------------------------------------------------------- #
# omission
# --------------------------------------------------------------------------- #


def test_omission_when_gp_and_pharmacy_support_it_and_the_chart_does_not() -> None:
    found = run([chart("amlodipine", 5.0), gp("famotidine", 40.0), fill("famotidine", 40.0)])
    assert (D.OMISSION, "famotidine") in kinds(found)
    omission = next(f for f in found if f.type is D.OMISSION)
    assert omission.row_ids and all(not r.startswith("EMR") for r in omission.row_ids)


def test_no_omission_on_a_gp_listing_alone() -> None:
    """GP lists keep ~30% of stopped medicines as active; a listing with no
    supply and no patient behind it is not enough."""
    found = run([chart("amlodipine", 5.0), gp("alendronate", 70.0, freq="weekly")],
                found=("emr", "gp"))
    assert (D.OMISSION, "alendronate") not in kinds(found)


def test_a_patient_only_item_is_not_an_omission() -> None:
    found = run([chart("amlodipine", 5.0), patient("magnesium")])
    assert (D.OMISSION, "magnesium") not in kinds(found)


def test_a_combination_charted_as_its_components_is_not_an_omission() -> None:
    """Brief 8, section 4: Coversyl Plus versus perindopril + indapamide is the
    same therapy written two ways."""
    combo = [("perindopril", 5.0), ("indapamide", 1.25)]
    found = run([chart("perindopril", 5.0), chart("indapamide", 1.25),
                 gp("perindopril/indapamide", ingredients=combo),
                 fill("perindopril/indapamide", ingredients=combo)])
    assert not [f for f in found if f.type is D.OMISSION]


# --------------------------------------------------------------------------- #
# commission
# --------------------------------------------------------------------------- #


def test_commission_when_sources_say_it_stopped() -> None:
    found = run([chart("spironolactone", 25.0), gp("spironolactone", 25.0, status="ceased"),
                 patient("spironolactone", status="ceased")])
    assert (D.COMMISSION, "spironolactone") in kinds(found)


def test_silence_alone_never_makes_a_commission() -> None:
    """A patient and a pharmacy that simply never mention a charted medicine
    have not said it stopped."""
    found = run([chart("esomeprazole", 40.0), patient("amlodipine"), fill("amlodipine", 5.0)])
    assert (D.COMMISSION, "esomeprazole") not in kinds(found)


def test_a_prn_medicine_rarely_refilled_is_not_a_commission() -> None:
    """A GTN spray dispensed once, a year ago, is normal for a PRN medicine."""
    found = run([chart("glyceryl trinitrate", freq="prn"),
                 gp("glyceryl trinitrate", freq="only when I need it"),
                 fill("glyceryl trinitrate", days_ago=360, qty=1, days_supply=30)])
    assert (D.COMMISSION, "glyceryl trinitrate") not in kinds(found)


# --------------------------------------------------------------------------- #
# dose and frequency
# --------------------------------------------------------------------------- #


def test_a_different_strength_is_a_dose_discrepancy() -> None:
    found = run([chart("amlodipine", 2.5), gp("amlodipine", 5.0), fill("amlodipine", 5.0)])
    assert (D.DOSE, "amlodipine") in kinds(found)


def test_same_strength_at_a_different_frequency_is_a_frequency_discrepancy() -> None:
    """Clopidogrel charted bd instead of daily: the daily dose doubles, but what
    went wrong is the frequency."""
    found = run([chart("clopidogrel", 150.0, freq="1 bd"),
                 gp("clopidogrel", 75.0, freq="1 daily"), fill("clopidogrel", 75.0)])
    assert (D.FREQUENCY, "clopidogrel") in kinds(found)
    assert (D.DOSE, "clopidogrel") not in kinds(found)


def test_an_equal_daily_dose_is_never_flagged_however_it_is_split() -> None:
    """Brief 8, section 2: 500 mg bd and 1 g daily are the same dose."""
    found = run([chart("metformin", 1000.0, freq="1 bd"),
                 gp("metformin", 1000.0, freq="1 daily"), fill("metformin", 1000.0)])
    assert not [f for f in found if f.type in (D.DOSE, D.FREQUENCY)]


def test_a_documented_reason_is_kept_but_marked_intentional() -> None:
    found = run([chart("amlodipine", 2.5, note="dose reduced: hypotension"),
                 gp("amlodipine", 5.0), fill("amlodipine", 5.0)])
    dose = next(f for f in found if f.type is D.DOSE)
    assert dose.intent_status == "documented_intentional"


# --------------------------------------------------------------------------- #
# dose_unconfirmable
# --------------------------------------------------------------------------- #


def test_warfarin_is_always_dose_unconfirmable_and_never_a_plain_dose_finding() -> None:
    """Agreement between sources that cannot see a phone instruction is not
    confirmation (DATA_SPEC 9.5)."""
    found = run([chart("warfarin", 5.0), gp("warfarin", 5.0, freq="as directed per INR"),
                 fill("warfarin", 5.0), patient("warfarin", freq="4 mg Mon Wed Fri")])
    unconfirmable = [f for f in found if f.type is D.DOSE_UNCONFIRMABLE]
    assert len(unconfirmable) == 1
    assert unconfirmable[0].severity == "high"
    assert unconfirmable[0].tasks
    assert (D.DOSE, "warfarin") not in kinds(found)


# --------------------------------------------------------------------------- #
# stale_listing
# --------------------------------------------------------------------------- #


def test_stale_listing_when_the_gp_lists_it_and_supply_ran_out() -> None:
    found = run([chart("amlodipine", 5.0), gp("levothyroxine", 0.1),
                 fill("levothyroxine", 0.1, days_ago=300)])
    assert (D.STALE_LISTING, "levothyroxine") in kinds(found)


def test_no_stale_listing_when_the_patient_says_they_still_take_it() -> None:
    found = run([chart("amlodipine", 5.0), gp("levothyroxine", 0.1),
                 fill("levothyroxine", 0.1, days_ago=300), patient("levothyroxine")])
    assert (D.STALE_LISTING, "levothyroxine") not in kinds(found)


def test_no_stale_listing_for_a_medicine_dispensed_privately() -> None:
    found = run([chart("amlodipine", 5.0), gp("levothyroxine", 0.1),
                 fill("levothyroxine", 0.1, days_ago=300, script_type="private")])
    assert (D.STALE_LISTING, "levothyroxine") not in kinds(found)


def test_another_medicines_private_script_does_not_hide_a_stale_listing() -> None:
    found = run([chart("amlodipine", 5.0), fill("amlodipine", 5.0, script_type="private"),
                 gp("levothyroxine", 0.1), fill("levothyroxine", 0.1, days_ago=300)])
    assert (D.STALE_LISTING, "levothyroxine") in kinds(found)


# --------------------------------------------------------------------------- #
# duplication
# --------------------------------------------------------------------------- #

CADUET = [("amlodipine", 5.0), ("atorvastatin", 10.0)]


def test_a_combination_and_its_component_on_one_list_is_a_duplication() -> None:
    found = run([chart("amlodipine/atorvastatin", ingredients=CADUET),
                 gp("amlodipine/atorvastatin", ingredients=CADUET), gp("atorvastatin", 40.0),
                 fill("amlodipine/atorvastatin", ingredients=CADUET), fill("atorvastatin", 40.0)])
    dup = [f for f in found if f.type is D.DUPLICATION]
    assert [d.generic for d in dup] == ["amlodipine/atorvastatin"]
    assert dup[0].detail["overlaps_with"] == "atorvastatin"


def test_a_stale_gp_line_does_not_make_a_duplication() -> None:
    """The GP still lists atorvastatin, but its supply ran out long ago: that is
    a stale listing, not a second current statin."""
    found = run([chart("amlodipine/atorvastatin", ingredients=CADUET),
                 gp("amlodipine/atorvastatin", ingredients=CADUET), gp("atorvastatin", 40.0),
                 fill("amlodipine/atorvastatin", ingredients=CADUET),
                 fill("atorvastatin", 40.0, days_ago=300)])
    assert not [f for f in found if f.type is D.DUPLICATION]


# --------------------------------------------------------------------------- #
# Properties of every output
# --------------------------------------------------------------------------- #


@pytest.fixture
def busy():
    return [chart("amlodipine", 2.5), gp("amlodipine", 5.0), fill("amlodipine", 5.0),
            gp("famotidine", 40.0), fill("famotidine", 40.0),
            chart("warfarin", 5.0), gp("warfarin", 5.0), fill("warfarin", 5.0)]


def test_every_finding_cites_its_rows(busy) -> None:
    found = run(busy)
    assert found
    assert all(f.row_ids for f in found)


def test_output_is_deterministic_and_ordered(busy) -> None:
    found = run(busy)
    assert found == run(list(reversed(busy)))
    order = [(f.generic, f.type.value) for f in found]
    assert order == sorted(order)
