"""The detector scorecard, pinned (DATA_SPEC 11.2).

Runs `scripts/eval.py`'s real chain -- identity, coverage, fusion, detection,
ranking -- over the synthetic population and holds the headline numbers, the
way `test_identity.py` holds linkage. If a change trades a high-risk finding or
a false merge for a point of F1, this fails.

Skips when `data/synthetic/silos/` is absent (gitignored; `make synth`). A skip
here is a missing build, not a pass.

The floors sit a little under the 25 Oct numbers (held-out F1 0.88, tune 0.91)
so ordinary regeneration noise does not fail the suite, while a real regression
does. Held-out is reported, never tuned against.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SILOS = ROOT / "data" / "synthetic" / "silos"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not all((SILOS / f"{s}.json").exists()
                               for s in ("emr", "gp", "pharmacy", "patient")),
                       reason="run `make synth` first (data/synthetic/silos/ is gitignored)"),
]


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("medtrace_eval", ROOT / "scripts" / "eval.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["medtrace_eval"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def world(ev):
    return ev.load_world()


def _f1(result) -> float:
    tp, fp, fn = (sum(c.values()) for c in (result.tp, result.fp, result.fn))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


@pytest.mark.parametrize(("split", "floor"), [("tune", 0.85), ("heldout", 0.82)])
def test_f1_holds(ev, world, split, floor) -> None:
    result = ev.score(world, world.truth["split"][split], review="oracle")
    assert _f1(result) >= floor, f"{split} F1 {_f1(result):.3f} fell below {floor}"


@pytest.mark.parametrize("split", ["tune", "heldout"])
def test_every_planted_high_risk_finding_is_found(ev, world, split) -> None:
    """APINCHS recall has a target of 100% (DATA_SPEC 11.2)."""
    result = ev.score(world, world.truth["split"][split], review="oracle")
    assert result.high_risk_found == result.high_risk_planted


def test_no_patient_is_buried_in_alerts(ev, world) -> None:
    keys = world.truth["split"]["tune"] + world.truth["split"]["heldout"]
    result = ev.score(world, keys, review="oracle")
    assert result.findings / result.patients <= 4.0


def test_no_false_merge_anywhere_in_the_pipeline(ev, world) -> None:
    """Measured on the links the pipeline actually acted on, not on Q1 alone."""
    by_key = {p["patient_key"]: p for p in world.truth["patients"]}
    for patient in world.truth["patients"]:
        rec = ev.reconcile(world, patient, review="none")
        if rec is None:
            continue
        decoys = {f"{s}:{i}" for trap in patient["identity_traps"]
                  for s, ids in by_key[trap["other_patient_key"]]["true_links"].items()
                  for i in ids}
        merged = {l.candidate_id for l in rec.links if l.band == "auto-merge"}
        assert not merged & decoys, f"{patient['patient_key']} merged {merged & decoys}"
