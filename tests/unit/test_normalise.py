"""`normalise.py`: free text and codes -> one canonical `MedStatement`.

`daily_dose_mg` is the comparison key for every dose discrepancy, so an error
here is a false flag or a missed one. The end-to-end test at the bottom pins
it against the planted ground truth.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from datetime import date

import pytest

from app.domain.packs.medtrace.normalise import (
    _canonical_route,
    llm_candidates,
    normalise_med,
    parse_frequency,
    parse_release,
    parse_strength_mg,
    strip_salt,
)
from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql, rows_from_sql
from app.domain.packs.medtrace.types import SourceRow

FIXTURES = pathlib.Path("tests/fixtures/medtrace")


def _deliberately_vague() -> frozenset[str]:
    """The generator's intentionally unresolvable patient descriptions."""
    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_for_tests", pathlib.Path("scripts/generate_synthetic.py"))
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    sys.modules["generate_synthetic_for_tests"] = gen
    spec.loader.exec_module(gen)
    return frozenset(gen.LAY_TERMS.values()) | {"a little white one"}


DELIBERATELY_VAGUE = _deliberately_vague()

pytestmark = pytest.mark.skipif(
    not (FIXTURES / "Q_REF__lexicon.json").exists(), reason="run `make lexicon` first"
)


@pytest.fixture(scope="module")
def lex():
    load = lambda n: dicts_from_sql(json.loads((FIXTURES / f"Q_REF__{n}.json").read_text()))
    return build_lexicon(load("lexicon"), load("apinchs"), load("nicknames"))


def row(source="gp", **kwargs) -> SourceRow:
    base = {"source": source, "row_id": "GP-000001", "source_patient_id": "GPP000001"}
    return SourceRow(**(base | kwargs))


# --------------------------------------------------------------------------- #
# Strength: mcg vs mg is a 1000x error
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("text", "expected"), [
    ("40 mg", 40.0), ("40mg", 40.0), ("0.5 mg", 0.5),
    ("62.5 microgram", 0.0625),   # digoxin -- high-risk, and 1000x if read as mg
    ("100 mcg", 0.1), ("1 g", 1000.0),
    ("5/1.25 mg", 5.0),            # combination: first component
    ("1000 IU", 1000.0),           # not a mass; carried unscaled
    ("", None), (None, None), ("as directed", None),
])
def test_parse_strength_mg(text, expected) -> None:
    assert parse_strength_mg(text) == expected


def test_microgram_and_milligram_are_not_confused() -> None:
    """Digoxin is 62.5 **microgram**. Read as milligrams it is 1000x the dose,
    and digoxin is high-risk under our own extension table."""
    assert parse_strength_mg("62.5 microgram") * 1000 == parse_strength_mg("62.5 mg")


# --------------------------------------------------------------------------- #
# Frequency
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("text", "per_day", "prn"), [
    ("1 tab bd", 2.0, False), ("bd", 2.0, False), ("morning and night", 2.0, False),
    ("1 mane", 1.0, False), ("nocte", 1.0, False), ("one a day", 1.0, False),
    ("tds", 3.0, False), ("qid", 4.0, False),
    ("weekly", 1 / 7, False), ("6-monthly", 1 / 182, False),
    ("nocte prn", 1.0, True), ("only when I need it", None, True),
    ("as directed per INR", None, False),
])
def test_parse_frequency(text, per_day, prn) -> None:
    got_per_day, got_prn = parse_frequency(text)
    assert got_prn is prn
    if per_day is None:
        assert got_per_day is None
    else:
        assert got_per_day == pytest.approx(per_day)


def test_a_written_out_number_counts(lex=None) -> None:
    """The GP silo renders "2 tds" as "two three times a day". A digit-only
    regex reads that as one dose and halves the daily total."""
    assert parse_frequency("two three times a day")[0] == 6.0
    assert parse_frequency("2 tds")[0] == 6.0


def test_a_dose_range_is_averaged() -> None:
    """"1 to 2 nocte" is how metformin XR and gliclazide MR are written. Taking
    the low end understates every titrated dose and the high end overstates it;
    both land on a dose comparison that reports a discrepancy that is not there."""
    assert parse_frequency("1 to 2 nocte")[0] == 1.5
    assert parse_frequency("1 to 2 mane")[0] == 1.5


def test_an_unparseable_frequency_is_none_not_once_daily() -> None:
    """Defaulting to once daily produces a confidently wrong daily dose."""
    assert parse_frequency("take as directed")[0] is None
    assert parse_frequency(None)[0] is None


# --------------------------------------------------------------------------- #
# Release and salts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("texts", "expected"), [
    (("modified release tablet",), "MR"),
    (("Capsule (controlled delivery)",), "MR"),
    (("Tablet 190 mg (controlled release)",), "MR"),
    (("tablet",), "IR"),
    (("Efexor-XR",), "MR"),
    (("",), "unknown"),
])
def test_parse_release(texts, expected) -> None:
    assert parse_release(*texts) == expected


def test_strip_salt_is_for_lookup_only() -> None:
    assert strip_salt("atorvastatin calcium") == "atorvastatin"
    assert strip_salt("perindopril arginine") == "perindopril"
    assert strip_salt("perindopril erbumine") == "perindopril"


def test_stripping_the_metoprolol_salt_does_not_collapse_its_two_forms(lex) -> None:
    """Metoprolol **tartrate** is immediate release and **succinate** modified
    release, and they are not interchangeable 1:1. Salt stripping is safe only
    because `release` is determined independently of the salt -- if release were
    ever inferred from the salt word, this would become a correctness bug."""
    assert strip_salt("metoprolol tartrate") == strip_salt("metoprolol succinate")
    ir = normalise_med(row(med_text="metoprolol tartrate 50 mg", route_text="tablet",
                           strength_text="50 mg", freq_text="1 bd"), lex)
    mr = normalise_med(row(med_text="Toprol-XL 95 mg", strength_text="95 mg",
                           route_text="modified release tablet", freq_text="1 daily"), lex)
    assert ir.release == "IR"
    assert mr.release == "MR"


# --------------------------------------------------------------------------- #
# Resolution order
# --------------------------------------------------------------------------- #


def test_a_code_wins_outright(lex) -> None:
    """A code is a fact. It beats a name that disagrees with it."""
    entry = next(e for e in lex.entries if e.pbs_code and not e.pbs_code.startswith("SYN-"))
    statement = normalise_med(row(med_text="something else entirely",
                                  med_code=entry.pbs_code, code_system="pbs"), lex)
    assert statement.resolution == "code"
    assert statement.generic == entry.generic


def test_a_brand_resolves_through_the_lexicon(lex) -> None:
    """Lipitor and atorvastatin are the same medicine -- the demo shows this
    *not* being flagged."""
    statement = normalise_med(row(med_text="Lipitor 40mg", strength_text="40 mg",
                                  freq_text="1 daily"), lex)
    assert statement.resolution == "lexicon"
    assert statement.generic == "atorvastatin"


def test_a_trailing_strength_does_not_defeat_the_lookup(lex) -> None:
    """The GP silo writes "Lipitor 40mg" and "perindopril/indapamide 5/1.25 mg"."""
    assert normalise_med(row(med_text="rosuvastatin 20 mg"), lex).generic == "rosuvastatin"
    assert normalise_med(row(med_text="perindopril/indapamide 5/1.25 mg"), lex).generic \
        == "perindopril/indapamide"


def test_an_unrecognisable_name_is_unmapped_not_guessed(lex) -> None:
    """`unmapped` is an honest answer the UI renders as "could not resolve".
    `safety_gate` escalates anything resting on one."""
    statement = normalise_med(row(source="patient", med_text="a little white one"), lex)
    assert statement.resolution == "unmapped"
    assert statement.generic is None


def test_a_combination_decomposes_into_its_ingredients(lex) -> None:
    """`detect.duplication` intersects ingredient sets, so a combination that
    does not decompose is invisible to it."""
    statement = normalise_med(row(med_text="Coversyl Plus", strength_text="5/1.25 mg"), lex)
    assert [name for name, _mg in statement.ingredients] == ["perindopril", "indapamide"]


# --------------------------------------------------------------------------- #
# Daily dose
# --------------------------------------------------------------------------- #


def test_the_same_daily_dose_written_two_ways_is_the_same_number(lex) -> None:
    """"500mg bd" and "1g daily" must not read as a dose discrepancy."""
    bd = normalise_med(row(med_text="metformin", strength_text="500 mg", freq_text="1 bd"), lex)
    daily = normalise_med(row(med_text="metformin", strength_text="1 g", freq_text="1 daily"), lex)
    assert bd.daily_dose_mg == daily.daily_dose_mg == 1000.0


def test_a_device_pack_does_not_imply_a_daily_dose(lex) -> None:
    """One inhaler per 7 days is not 0.14 doses a day. The pharmacy silo has no
    directions, and inferring from the pack produced daily doses wrong by an
    order of magnitude -- a GTN spray came out at 0.057 mg/day against 0.4."""
    spray = normalise_med(row(source="pharmacy", med_text="Nitrolingual Pumpspray",
                              strength_text="400 microgram/dose", route_text="spray",
                              qty=1, days_supply=7), lex)
    assert spray.daily_dose_mg is None
    tablet = normalise_med(row(source="pharmacy", med_text="atorvastatin",
                               strength_text="40 mg", route_text="tablet",
                               qty=30, days_supply=30), lex)
    assert tablet.daily_dose_mg == 40.0


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("source", "text", "expected"), [
    ("patient", "yes", "active"),
    ("patient", "no", "ceased"),
    ("patient", "unsure", "unknown"),     # never "ceased"
    ("gp", "active", "active"),
    ("gp", "ceased", "ceased"),
    ("emr", "cease", "ceased"),
    ("emr", "continue", "active"),
    ("emr", "change", "active"),
    ("gp", "", "unknown"),
])
def test_status_mapping(lex, source, text, expected) -> None:
    assert normalise_med(row(source=source, med_text="atorvastatin",
                             status_text=text), lex).status == expected


def test_patient_uncertainty_is_never_read_as_cessation(lex) -> None:
    """"unsure" is the patient saying they do not know. Reading it as "ceased"
    is how a tool tells someone to stop a medicine they are still taking."""
    assert normalise_med(row(source="patient", med_text="warfarin",
                             status_text="unsure"), lex).status == "unknown"


# --------------------------------------------------------------------------- #
# llm_candidates: the constraint that keeps the model honest
# --------------------------------------------------------------------------- #


def test_llm_candidates_only_ever_offers_things_in_the_lexicon(lex) -> None:
    """This is what makes "the LLM never invents drug names" enforceable in code
    rather than in a prompt."""
    known = {e.generic for e in lex.entries if e.generic}
    for text in ("my blood thinner", "a little white one", "Lipitor", "the water tablet"):
        offered = llm_candidates(text, lex)
        assert set(offered["ingredients"]) <= known, text
        assert len(offered["ingredients"]) <= 5


def test_a_lay_term_offers_a_class_not_a_single_guess(lex) -> None:
    """"My blood thinner" has no single right answer. `B01` plus "matches
    warfarin (GP), confirm" is true and useful; guessing warfarin is neither."""
    offered = llm_candidates("my blood thinner", lex)
    assert offered["atc_classes"]
    assert all(c.startswith("B01") for c in offered["atc_classes"])
    assert len(offered["ingredients"]) > 1, "a lay term should not resolve to one drug"


def test_an_unknown_phrase_still_returns_only_known_options(lex) -> None:
    offered = llm_candidates("something nobody has ever written", lex)
    assert set(offered["ingredients"]) <= {e.generic for e in lex.entries if e.generic}


# --------------------------------------------------------------------------- #
# End to end, against the planted ground truth
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_normalisation_accuracy_against_ground_truth(lex) -> None:
    """DATA_SPEC 11.2: top-1 of 0.95 on structured sources, 0.85 on patient text.

    Also pins daily-dose correctness. Where a dose is computed at all it must
    match the planted truth exactly; where the pack is a device we compute
    nothing rather than inventing a number, and that is counted separately.
    """
    truth_by_key = {p["patient_key"]: p for p in json.loads(
        pathlib.Path("data/synthetic/ground_truth.json").read_text())["patients"]}
    resolved = {"structured": [0, 0], "patient": [0, 0]}
    dose_ok = dose_total = 0
    left_unresolved: list[str] = []

    for path in sorted(FIXTURES.glob("Q2__*.json")):
        patient = truth_by_key[path.stem.split("__")[1]]
        timeline = {t["generic"]: t for t in patient["timeline"]}
        planted = {r for f in patient["planted"] if f["type"] in ("dose", "frequency")
                   for r in f["row_ids"]}
        for source_row in rows_from_sql(json.loads(path.read_text())):
            if not source_row.has_med:
                continue
            statement = normalise_med(source_row, lex)
            bucket = "patient" if source_row.source == "patient" else "structured"
            resolved[bucket][1] += 1
            resolved[bucket][0] += statement.resolution != "unmapped"
            if statement.resolution == "unmapped":
                left_unresolved.append(source_row.med_text or "")
            want = timeline.get(statement.generic or "", {}).get("true_daily_dose_mg")
            if want and statement.daily_dose_mg is not None and source_row.row_id not in planted:
                dose_total += 1
                dose_ok += abs(statement.daily_dose_mg - want) < 0.01

    structured = resolved["structured"][0] / resolved["structured"][1]
    assert structured >= 0.95, f"structured top-1 {structured:.3f}"
    # Patient free text is checked exactly, not statistically. Everything left
    # unresolved must be a description the generator makes vague ON PURPOSE --
    # "a little white one", or a class-level lay term ("cholesterol tablet")
    # that goes to the LLM candidate step instead of being guessed. A rate
    # floor here measured the generator's dice on 10 patients (about +-0.04),
    # not normalise: it failed at 0.837 when 82 of 82 resolvable rows resolved.
    # The population-level DATA_SPEC 11.2 figure is in tests/eval/test_scorecard.py.
    unexpected = [t for t in left_unresolved if t not in DELIBERATELY_VAGUE]
    assert not unexpected, f"resolvable descriptions left unmapped: {unexpected}"
    assert dose_total > 500
    assert dose_ok / dose_total >= 0.99, f"daily dose {dose_ok}/{dose_total}"


# --------------------------------------------------------------------------- #
# Release and route: false formulation and route conflicts (25 Oct)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("texts", "expected"), [
    # Bare-substring MR markers matched the start of ordinary names.
    (("Crestor",), "unknown"),
    (("Crestor 5 mg",), "unknown"),
    (("Lasix",), "unknown"),
    (("lansoprazole",), "unknown"),
    (("lamotrigine",), "unknown"),
    # ...while the real suffixes still count, as whole words.
    (("Inderal LA",), "MR"),
    (("Cardizem CD",), "MR"),
    (("Diamicron MR",), "MR"),
    (("Toprol-XL",), "MR"),
])
def test_mr_suffixes_match_whole_words_only(texts, expected) -> None:
    assert parse_release(*texts) == expected


def test_rosuvastatin_is_never_modified_release(lex) -> None:
    """"Crestor" contains " cr", which used to make rosuvastatin MR. There is no
    MR rosuvastatin in Australia, so every Crestor line set up a false
    formulation finding against an EMR that correctly said nothing."""
    statement = normalise_med(row("gp", med_text="Crestor 5 mg", strength_text="5 mg"), lex)
    assert statement.generic == "rosuvastatin"
    assert statement.release == "IR"


def test_a_generic_level_code_does_not_invent_a_release(lex) -> None:
    """An AMT MP code is shared by every product of a medicine, and
    `by_amt_code` keeps whichever was loaded first. Metformin comes in IR and
    MR, so the EMR's plain "metformin" must stay `unknown` -- not borrow the
    release of an arbitrary product and contradict a GP who named Diabex XR."""
    mp_code = next(e.amt_mp for e in lex.entries if e.generic == "metformin")
    statement = normalise_med(row("emr", row_id="EMR-000001", med_text="metformin",
                                  med_code=mp_code, code_system="AMT_MP",
                                  strength_text="1000 mg", route_text="PO"), lex)
    assert statement.generic == "metformin"
    assert statement.release == "unknown"


def test_a_product_level_code_does_pin_the_release(lex) -> None:
    entry = next(e for e in lex.entries if e.generic == "metformin" and e.release == "MR")
    statement = normalise_med(row("gp", med_text="metformin 1000 mg", med_code=entry.amt_mpp,
                                  code_system="AMT_MPP", strength_text="1000 mg"), lex)
    assert statement.release == "MR"


@pytest.mark.parametrize(("text", "expected"), [
    ("PO", "PO"), ("SL", "SL"), ("INH", "INH"), ("SC", "SC"),
    ("tablet", "PO"), ("capsule", "PO"), ("modified release tablet", "PO"),
    ("inhaler", "INH"), ("patch", "TD"),
    # Ambiguous forms say nothing about route -- None, never a guess.
    ("spray", None), ("injection", None), (None, None), ("", None),
])
def test_canonical_route(text, expected) -> None:
    """The pharmacy silo has no route column; `route_text` is the dosage form.
    Raw, it disagreed with the EMR's "PO" on nearly every medicine."""
    assert _canonical_route(text) == expected


def test_a_named_mr_product_outranks_a_plain_form_word(lex) -> None:
    """The pharmacy form column says just "capsule" for Cymbalta, a
    delayed-release capsule. Read alone, "capsule" made it IR and contradicted
    the GP and EMR. A pinned product is a stronger signal than a form word."""
    entry = next(e for e in lex.entries if e.generic == "duloxetine" and e.release == "MR")
    statement = normalise_med(row("pharmacy", row_id="PHM-000001", med_text=entry.brand,
                                  med_code=entry.pbs_code, code_system="PBS",
                                  route_text="capsule", strength_text=entry.strength), lex)
    assert statement.release == "MR"
