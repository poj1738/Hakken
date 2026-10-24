"""The hand-built reference tables, checked against `docs/DATA_SPEC.md`.

These three CSVs are transcribed by hand from the spec, which makes a quiet
transcription error the most likely defect in the whole data pipeline -- and the
hardest to notice, because a wrong share or a shifted column produces plausible
output. This file is the safeguard. It already caught a missing empty field that
had shifted `60` into the `high_risk` column.

The tables are our own work (`docs/DATA_LICENCES.md` section 3): PBS schedule data
is not publicly obtainable without a login, so the clinical content comes from
the spec and the codes are minted or joined by `scripts/build_lexicon.py`.
"""

from __future__ import annotations

import csv
import pathlib

import pytest

SRC = pathlib.Path("data/reference_src")

#: DATA_SPEC 4.2's bundles, plus 17 (4.3 combination traps) and 18 (OTC items),
#: which are not sampled as bundles and so carry no shares.
SPEC_BUNDLES = set(range(1, 17))
UNSAMPLED_BUNDLES = {17, 18}

#: DATA_SPEC 4.2 bundle 6's anchor shares sum to 0.95, not 1.00
#: (0.30 + 0.28 + 0.18 + 0.12 + 0.07). Transcribed faithfully rather than
#: silently "corrected": it is the spec's arithmetic, and Arpon should decide
#: whether a share is missing or one is wrong. The generator normalises anchor
#: shares before sampling, so a bundle summing to 0.95 still behaves correctly.
#: If the spec is fixed, this test fails and tells us to update it.
KNOWN_SPEC_SHARE_GAPS = {6: 0.95}


def read(name: str) -> list[dict[str, str]]:
    with (SRC / name).open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


@pytest.fixture(scope="module")
def medicines() -> list[dict[str, str]]:
    return read("medicines.csv")


@pytest.fixture(scope="module")
def apinchs() -> list[dict[str, str]]:
    return read("apinchs_atc.csv")


@pytest.fixture(scope="module")
def nicknames() -> list[dict[str, str]]:
    return read("nicknames.csv")


# --------------------------------------------------------------------------- #
# medicines.csv
# --------------------------------------------------------------------------- #


def test_every_row_has_every_column(medicines: list[dict[str, str]]) -> None:
    """A short row shifts every later value by one and is nearly invisible."""
    lines = (SRC / "medicines.csv").read_text(encoding="utf-8-sig").splitlines()
    width = len(next(csv.reader([lines[0]])))
    for number, line in enumerate(lines[1:], start=2):
        assert len(next(csv.reader([line]))) == width, f"line {number} is misaligned"


def test_all_sixteen_spec_bundles_are_present(medicines: list[dict[str, str]]) -> None:
    assert {int(r["bundle_id"]) for r in medicines} == SPEC_BUNDLES | UNSAMPLED_BUNDLES


def test_anchor_shares_sum_to_one_per_bundle(medicines: list[dict[str, str]]) -> None:
    """Within a bundle the anchor is drawn by share, so the shares must be a
    distribution. Add-ons are independent probabilities and are excluded."""
    sums: dict[int, float] = {}
    for row in medicines:
        bundle = int(row["bundle_id"])
        if bundle in UNSAMPLED_BUNDLES or row["is_addon"] == "1":
            continue
        sums[bundle] = sums.get(bundle, 0.0) + float(row["share"])
    assert set(sums) == SPEC_BUNDLES
    for bundle, total in sorted(sums.items()):
        expected = KNOWN_SPEC_SHARE_GAPS.get(bundle, 1.0)
        assert total == pytest.approx(expected, abs=1e-9), f"bundle {bundle} sums to {total}"


def test_addon_probabilities_are_probabilities(medicines: list[dict[str, str]]) -> None:
    for row in medicines:
        if row["is_addon"] == "1":
            assert 0.0 < float(row["share"]) <= 1.0, row["generic"]


def test_high_risk_column_preserves_the_specs_three_states(medicines: list[dict[str, str]]) -> None:
    """DATA_SPEC distinguishes `Y` from `Y (ext)`; collapsing them loses the fact
    that digoxin, sulfonylureas and prednisolone are facility extensions rather
    than core APINCHS classes."""
    assert {r["high_risk"] for r in medicines} == {"", "Y", "ext"}
    by_generic = {r["generic"]: r["high_risk"] for r in medicines}
    assert by_generic["warfarin"] == "Y"
    assert by_generic["apixaban"] == "Y"
    assert by_generic["digoxin"] == "ext"
    assert by_generic["prednisolone"] == "ext"
    assert by_generic["rosuvastatin"] == ""


def test_combinations_declare_more_than_one_ingredient(medicines: list[dict[str, str]]) -> None:
    """`detect.duplication` works by intersecting ingredient sets, so a
    combination with one declared ingredient silently stops being detectable."""
    for row in medicines:
        ingredients = [i for i in row["ingredients"].split(";") if i]
        assert ingredients, row["generic"]
        if "/" in row["generic"]:
            assert len(ingredients) > 1, f"{row['generic']} declares {ingredients}"


def test_the_combination_traps_from_spec_4_3_are_all_present(medicines: list[dict[str, str]]) -> None:
    """Each of these must exist or its planted duplication cannot be generated."""
    generics = {r["generic"] for r in medicines}
    for required in [
        "perindopril/indapamide", "perindopril/amlodipine",
        "irbesartan/hydrochlorothiazide", "candesartan/hydrochlorothiazide",
        "telmisartan/amlodipine", "amlodipine/atorvastatin",
        "ezetimibe/rosuvastatin", "ezetimibe/atorvastatin",
        "sitagliptin/metformin", "empagliflozin/metformin",
        "aspirin/clopidogrel", "oxycodone/naloxone",
        "alendronate/colecalciferol", "dutasteride/tamsulosin",
        "paracetamol/codeine",
    ]:
        assert required in generics, required


def test_atc_codes_are_well_formed_or_deliberately_absent(medicines: list[dict[str, str]]) -> None:
    """ATC codes come from the spec only. The complementary items have none,
    which the spec states explicitly ("none") -- so blank is a real value here,
    not a gap to be filled from general knowledge."""
    import re

    blank_allowed = {"fish oil", "glucosamine", "turmeric"}
    for row in medicines:
        atc = row["atc"]
        if not atc:
            assert row["generic"] in blank_allowed, f"{row['generic']} has no ATC"
            continue
        assert re.fullmatch(r"[A-Z]\d{2}[A-Z]{0,2}\d{0,2}", atc), f"{row['generic']}: {atc!r}"


def test_release_and_form_agree(medicines: list[dict[str, str]]) -> None:
    """`formulation` discrepancies compare `release`, so MR must be marked."""
    for row in medicines:
        assert row["release"] in {"IR", "MR"}, row["generic"]
        if "modified release" in row["form"]:
            assert row["release"] == "MR", row["generic"]


def test_both_forms_exist_for_every_formulation_trap_drug() -> None:
    """DATA_SPEC 5.2 plants `formulation` on metformin, metoprolol, gliclazide,
    oxycodone, paracetamol, venlafaxine and tamsulosin -- but an IR/MR
    discrepancy needs **both** forms in the lexicon.

    The spec supplies both only for metformin, oxycodone and paracetamol. The
    other four appear once each, so no IR/MR pair can be planted for them
    without a brand and strength the spec does not give. This test records that
    gap rather than papering over it: it is in the handoff for Arpon to fill,
    and inventing the missing products is exactly what we agreed not to do.
    """
    rows = read("medicines.csv")
    forms: dict[str, set[str]] = {}
    for row in rows:
        forms.setdefault(row["generic"], set()).add(row["release"])
    have_both = {g for g, f in forms.items() if f == {"IR", "MR"}}
    assert {"metformin", "oxycodone", "paracetamol"} <= have_both
    missing = {g for g in ("metoprolol", "gliclazide", "venlafaxine", "tamsulosin")
               if g not in have_both}
    assert missing == {"metoprolol", "gliclazide", "venlafaxine", "tamsulosin"}, (
        f"a formulation pair was added for {missing ^ {'metoprolol', 'gliclazide', 'venlafaxine', 'tamsulosin'}}; "
        "update docs/DATA_SPEC.md 4.2 and this test together"
    )


def test_no_identifier_in_the_reference_data_looks_real(medicines: list[dict[str, str]]) -> None:
    """Nothing here should resemble a real IHI or Medicare number."""
    import re

    blob = (SRC / "medicines.csv").read_text(encoding="utf-8-sig")
    assert not re.search(r"\b\d{16}\b", blob), "16-digit run: possible real IHI format"
    assert not re.search(r"\b800360\d{10}\b", blob), "real IHI prefix"


# --------------------------------------------------------------------------- #
# apinchs_atc.csv
# --------------------------------------------------------------------------- #


def test_apinchs_is_exactly_the_specs_forty_rows(apinchs: list[dict[str, str]]) -> None:
    assert len(apinchs) == 40
    assert [int(r["row_no"]) for r in apinchs] == list(range(1, 41))


def test_apinchs_classes_are_the_expected_letters(apinchs: list[dict[str, str]]) -> None:
    """A-P-I-N-C-H plus `Ext`. `S` (Systems) is a process category, not a drug
    class, so it correctly has no ATC prefix and no row."""
    assert {r["apinchs_class"] for r in apinchs} == {"A", "P", "I", "N", "C", "H", "Ext"}


def test_the_two_multi_prefix_rows_are_preserved(apinchs: list[dict[str, str]]) -> None:
    """Spec rows 22 and 40 each carry two ATC prefixes. Kept as written -- the
    build expands them, so the served view has 42 prefixes from 40 rows."""
    multi = {r["row_no"]: r["atc_prefixes"] for r in apinchs if ";" in r["atc_prefixes"]}
    assert multi == {"22": "N01AX10;N01AF", "40": "M03AC;M03AB"}
    total = sum(len(r["atc_prefixes"].split(";")) for r in apinchs)
    assert total == 42


def test_apinchs_prefixes_are_well_formed(apinchs: list[dict[str, str]]) -> None:
    import re

    for row in apinchs:
        for prefix in row["atc_prefixes"].split(";"):
            assert re.fullmatch(r"[A-Z]\d{2}[A-Z]{0,2}\d{0,2}", prefix), prefix


def test_the_high_risk_classes_our_medicines_need_are_covered(apinchs: list[dict[str, str]]) -> None:
    """Every medicine marked high-risk must match some APINCHS prefix, or
    `safety.high_risk_class` returns None and APINCHS recall cannot reach 100%."""
    prefixes = [p for r in apinchs for p in r["atc_prefixes"].split(";")]
    for atc in ("B01AA03", "B01AF02", "B01AF01", "B01AE07", "N02AA05", "N02AE01",
                "N02AX06", "N02AJ06", "A10AE04", "A10AB05", "A10BB09", "C01AA05",
                "N05CD07", "L04AX03"):
        assert any(atc.startswith(p) for p in prefixes), f"{atc} matches no APINCHS prefix"


# --------------------------------------------------------------------------- #
# nicknames.csv
# --------------------------------------------------------------------------- #


def test_nicknames_are_the_right_shape(nicknames: list[dict[str, str]]) -> None:
    assert len(nicknames) >= 100, "DATA_SPEC 10.2 asks for about 100 pairs"
    for row in nicknames:
        assert row["canonical"] and row["variant"]
        assert row["canonical"] != row["variant"]
        assert row["canonical"][0].isupper() and row["variant"][0].isupper()


def test_the_specs_named_examples_are_all_present(nicknames: list[dict[str, str]]) -> None:
    pairs = {(r["canonical"], r["variant"]) for r in nicknames}
    for pair in [("Margaret", "Peggy"), ("Margaret", "Peg"), ("Margaret", "Maggie"),
                 ("Elizabeth", "Betty"), ("Elizabeth", "Liz"), ("Patricia", "Pat"),
                 ("Patricia", "Trish"), ("Dorothy", "Dot"), ("Beverley", "Bev"),
                 ("Robert", "Bob"), ("William", "Bill"), ("Richard", "Dick"),
                 ("John", "Jack"), ("Edward", "Ted"), ("Geoffrey", "Geoff"),
                 ("Michael", "Mick")]:
        assert pair in pairs, pair


def test_ambiguous_variants_exist_and_must_not_be_closed_over(nicknames: list[dict[str, str]]) -> None:
    """Some variants belong to two canonical names, and that is why
    `parse.build_lexicon` must **not** transitively close the nickname map.

    `Chris` is a variant of both Christine and Christopher. Closing through it
    would make Christine equivalent to Christopher -- a false merge across two
    people of different sexes, and false-merge rate has a target of zero.
    """
    import collections

    owners = collections.defaultdict(set)
    for row in nicknames:
        owners[row["variant"]].add(row["canonical"])
    ambiguous = {v: c for v, c in owners.items() if len(c) > 1}
    assert "Chris" in ambiguous
    assert ambiguous["Chris"] == {"Christine", "Christopher"}
    assert {"Pat", "Jan", "Harry", "Terry"} <= set(ambiguous)
