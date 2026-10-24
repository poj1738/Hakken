"""`scripts/generate_synthetic.py`, against the invariants DATA_SPEC 4.4 names.

These are the checks the spec asks for by name -- determinism, planted row_ids
exist, the split is disjoint, every type and notice appears in tune, and no
rendered identifier looks real -- plus the ones that protect the eval harness
from scoring something that was never detectable.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

from app.domain.packs.medtrace.queries import HARMONISED_COLUMNS, IDENTITY_COLUMNS
from app.domain.packs.medtrace.types import DiscrepancyType, NoticeType

OUT = pathlib.Path("data/synthetic")
SILOS = OUT / "silos"
FIXTURES = pathlib.Path("tests/fixtures/medtrace")
SOURCES = ("emr", "gp", "pharmacy", "patient")

pytestmark = pytest.mark.skipif(
    not (OUT / "ground_truth.json").exists(),
    reason="run `make synth` first (data/synthetic/silos/ is gitignored)",
)


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    return json.loads((OUT / "ground_truth.json").read_text())


@pytest.fixture(scope="module")
def silo_rows() -> dict[str, list[dict[str, str]]]:
    return {s: json.loads((SILOS / f"{s}.json").read_text())["records"] for s in SOURCES}


@pytest.fixture(scope="module")
def all_row_ids(silo_rows: dict[str, list[dict[str, str]]]) -> set[str]:
    return {r["row_id"] for rows in silo_rows.values() for r in rows}


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def _digest(paths: list[pathlib.Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(path.read_bytes())
    return h.hexdigest()


@pytest.mark.slow
def test_the_generator_is_deterministic() -> None:
    """Same seed, byte-identical output. Without this, `output_examples/` and the
    eval numbers cannot be reproduced by a judge, and every rate in DATA_SPEC
    becomes unverifiable.

    Runs the generator **twice and compares the two runs**, rather than
    comparing against whatever is on disk. Comparing to the committed files
    tests staleness, not determinism: regenerating the lexicon with real PBS
    codes legitimately changes the output, and that must not read as a
    non-determinism failure.
    """
    def regenerate() -> str:
        result = subprocess.run([sys.executable, "scripts/generate_synthetic.py"],
                                capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stderr[-2000:]
        return _digest(sorted(SILOS.glob("*.json")) + [OUT / "ground_truth.json"])

    assert regenerate() == regenerate(), "two runs of the same seed differed"


# --------------------------------------------------------------------------- #
# Ground truth integrity
# --------------------------------------------------------------------------- #


def test_the_split_is_disjoint_and_covers_everyone(ground_truth: dict) -> None:
    tune, heldout = set(ground_truth["split"]["tune"]), set(ground_truth["split"]["heldout"])
    assert tune and heldout
    assert not tune & heldout
    assert tune | heldout == {p["patient_key"] for p in ground_truth["patients"]}


def test_every_planted_row_id_exists_in_a_silo(ground_truth: dict, all_row_ids: set[str]) -> None:
    for patient in ground_truth["patients"]:
        for finding in patient["planted"]:
            assert finding["row_ids"], f"{patient['patient_key']} {finding['type']} cites nothing"
            for row_id in finding["row_ids"]:
                assert row_id in all_row_ids, row_id


def test_no_planted_finding_is_unciteable(ground_truth: dict) -> None:
    """DATA_SPEC 11.2 scores a true positive by row_id **overlap**, so a planted
    finding with no row_ids can never be matched and would cap its type's recall
    below 1.0 for a reason unrelated to the detector. The generator drops those
    rather than keeping them."""
    for patient in ground_truth["patients"]:
        assert all(f["row_ids"] for f in patient["planted"])


def test_planted_types_are_all_in_the_frozen_enum(ground_truth: dict) -> None:
    """A type the pack cannot represent can never be reported."""
    known = {t.value for t in DiscrepancyType}
    for patient in ground_truth["patients"]:
        for finding in patient["planted"]:
            assert finding["type"] in known, finding["type"]


def test_notice_types_are_all_in_the_frozen_enum(ground_truth: dict) -> None:
    known = {n.value for n in NoticeType}
    for patient in ground_truth["patients"]:
        for notice in patient["notices"]:
            assert notice["type"] in known, notice["type"]


def test_the_core_discrepancy_types_all_appear_in_tune(ground_truth: dict) -> None:
    """DATA_SPEC 5.2 marks these "yes" for today. A type with zero tune instances
    cannot be tuned against or reported on."""
    tune = set(ground_truth["split"]["tune"])
    present = {f["type"] for p in ground_truth["patients"] if p["patient_key"] in tune
               for f in p["planted"]}
    for required in ("omission", "commission", "dose", "frequency", "duplication",
                     "stale_listing", "dose_unconfirmable"):
        assert required in present, f"no {required} planted in tune"


def test_the_hidden_error_rates_are_recorded_for_every_source(ground_truth: dict) -> None:
    """These are H-MEM's learning target: trust MAE is measured against
    `1 - hidden_error`, so a missing source has nothing to converge on."""
    rates = ground_truth["hidden_error_rates"]
    assert set(rates) == set(SOURCES)
    for source, attributes in rates.items():
        assert attributes, source
        assert all(0.0 <= v <= 1.0 for v in attributes.values()), source


def test_true_links_only_name_sources_the_patient_is_present_in(ground_truth: dict) -> None:
    for patient in ground_truth["patients"]:
        coverage = patient["coverage_truth"]
        links = patient["true_links"]
        assert "emr" in links, patient["patient_key"]
        for source in ("gp", "pharmacy", "patient"):
            assert (source in links) == coverage[f"{source}_present"], (
                f"{patient['patient_key']}: {source} link and coverage_truth disagree")


# --------------------------------------------------------------------------- #
# Synthetic identifier safety (DATA_SPEC 1)
# --------------------------------------------------------------------------- #


def test_no_rendered_identifier_looks_like_a_real_ihi(silo_rows) -> None:
    """`ihi_syn` is `SYN-` plus 12 digits. A real IHI is 16 digits beginning
    800360. Rendering one of those, even by accident, would turn a synthetic
    dataset into something that looks like real health data."""
    import re

    for source, rows in silo_rows.items():
        for row in rows:
            ihi = row.get("ihi_syn", "")
            if ihi:
                assert re.fullmatch(r"SYN-\d{12}", ihi), f"{source}: {ihi!r}"
        blob = json.dumps(rows)
        assert not re.search(r"\b800360\d{10}\b", blob), f"{source}: real IHI prefix"
        assert not re.search(r"\b\d{16}\b", blob), f"{source}: 16-digit run"


def test_prescribers_are_marked_synthetic(silo_rows) -> None:
    for row in silo_rows["pharmacy"]:
        if row.get("prescriber"):
            assert row["prescriber"].endswith("-SYN"), row["prescriber"]


# --------------------------------------------------------------------------- #
# Silo shapes (DATA_SPEC 2)
# --------------------------------------------------------------------------- #


def test_row_ids_are_unique_and_source_prefixed(silo_rows) -> None:
    expected = {"emr": "EMR-", "gp": "GP-", "pharmacy": "PHM-", "patient": "PAT-"}
    seen: set[str] = set()
    for source, rows in silo_rows.items():
        for row in rows:
            assert row["row_id"].startswith(expected[source]), row["row_id"]
            assert row["row_id"] not in seen, f"duplicate {row['row_id']}"
            seen.add(row["row_id"])


def test_a_patient_absent_from_a_source_has_no_rows_there(ground_truth: dict, silo_rows) -> None:
    """DATA_SPEC 2's absence rule. If an absent patient still had rows, a
    coverage gap would be invisible and `evidence_state` would return
    ABSENT_IN_SCOPE where the truth is UNKNOWN."""
    id_field = {"emr": "mrn", "gp": "gp_pid", "pharmacy": "cust_no", "patient": "intake_id"}
    present_ids = {s: {r[id_field[s]] for r in rows} for s, rows in silo_rows.items()}
    for patient in ground_truth["patients"]:
        for source in ("gp", "pharmacy", "patient"):
            if not patient["coverage_truth"][f"{source}_present"]:
                linked = patient["true_links"].get(source, [])
                assert not linked
                assert not (set(linked) & present_ids[source])


def test_every_value_in_every_silo_is_a_string(silo_rows) -> None:
    """Zetaris returns strings, so the silos must too -- otherwise the fixtures
    and the live view disagree about types and `parse.py` is tested against the
    wrong thing."""
    for source, rows in silo_rows.items():
        for row in rows:
            for key, value in row.items():
                assert isinstance(value, str), f"{source}.{key} is {type(value).__name__}"


# --------------------------------------------------------------------------- #
# Fixtures (DATA_SPEC 2.9)
# --------------------------------------------------------------------------- #


def test_fixtures_exist_for_tune_patients(ground_truth: dict) -> None:
    assert sorted(p.name for p in FIXTURES.glob("Q1__*.json")), "no Q1 fixtures"
    for template in ("Q1", "Q2", "Q3"):
        assert list(FIXTURES.glob(f"{template}__*.json")), template


@pytest.mark.parametrize("template,columns", [("Q1", IDENTITY_COLUMNS),
                                              ("Q2", HARMONISED_COLUMNS),
                                              ("Q3", HARMONISED_COLUMNS)])
def test_fixture_envelopes_match_their_sql_template(template: str, columns: tuple) -> None:
    """The replayed envelope's headers must be exactly what the live query
    selects, in order -- `headers` is positional against every row."""
    for path in sorted(FIXTURES.glob(f"{template}__*.json")):
        doc = json.loads(path.read_text())
        assert doc["headers"] == list(columns), path.name
        assert doc["total"] == len(doc["data"]), path.name
        for row in doc["data"]:
            assert len(row) == len(columns), path.name
            assert all(isinstance(v, str) for v in row), path.name


def test_q_ref_fixtures_are_present_and_shaped() -> None:
    for name in ("lexicon", "apinchs", "nicknames"):
        doc = json.loads((FIXTURES / f"Q_REF__{name}.json").read_text())
        assert doc["total"] == len(doc["data"]) > 0, name
        assert doc["headers"], name


def test_q1_returns_at_least_the_patients_own_emr_rows(ground_truth: dict) -> None:
    """Q1 is the identity-blocking query: a record it does not return can never
    be linked, so its recall caps the whole identity stage."""
    for path in sorted(FIXTURES.glob("Q1__*.json"))[:5]:
        key = path.stem.split("__")[1]
        patient = next(p for p in ground_truth["patients"] if p["patient_key"] == key)
        doc = json.loads(path.read_text())
        idx = doc["headers"].index("source_patient_id")
        returned = {row[idx] for row in doc["data"]}
        for source, ids in patient["true_links"].items():
            assert set(ids) <= returned, f"{key}: Q1 missed the {source} record"
