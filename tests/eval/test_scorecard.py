"""The detector scorecard, pinned (DATA_SPEC 11.2).

Runs `scripts/eval.py`'s real chain -- identity, coverage, fusion, detection,
ranking -- over the synthetic population and holds the headline numbers, the
way `test_identity.py` holds linkage. If a change trades a high-risk finding or
a false merge for a point of F1, this fails.

Skips when `data/synthetic/silos/` is absent (gitignored; `make synth`). A skip
here is a missing build, not a pass.

The F1 floors sit a little under the 25 Oct numbers at 200 patients (tune
0.93, held-out 0.95 before a post-hoc fix, 0.96 after)
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


@pytest.mark.parametrize(("split", "floor"), [("tune", 0.90), ("heldout", 0.90)])
def test_f1_holds(ev, world, split, floor) -> None:
    result = ev.score(world, world.truth["split"][split], review="oracle")
    assert _f1(result) >= floor, f"{split} F1 {_f1(result):.3f} fell below {floor}"


@pytest.mark.parametrize(("split", "floor"), [("tune", 1.0), ("heldout", 0.94)])
def test_high_risk_findings_are_found(ev, world, split, floor) -> None:
    """APINCHS recall has a target of 100% (DATA_SPEC 11.2) -- met on tune
    (34/34), NOT met on held-out (35/37 on 25 Oct, after the consultant's
    brief 12-13 changes). The floor pins that measured value as a regression
    guard; it is not the target. The two misses are both commissions (P0123
    insulin aspart, P0174 temazepam) and are recorded in docs/DECISIONS.md
    rather than tuned against -- fixing a held-out miss by looking at it would
    make held-out a second tune split."""
    result = ev.score(world, world.truth["split"][split], review="oracle")
    assert result.high_risk_found >= floor * result.high_risk_planted


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


def test_patient_free_text_resolves_at_population_scale(ev, world) -> None:
    """DATA_SPEC 11.2's top-1 targets, measured on the whole population rather
    than 10 fixture patients. Structured sources must resolve completely; patient
    free text was 0.847 on 25 Oct against a [ASSUMPTION] target of 0.85, which
    the generator's own vagueness rates cap at about that level. Floored two
    standard errors below. Whatever stays unmapped must be deliberately vague."""
    from app.domain.packs.medtrace.normalise import normalise_med

    vague = set(ev._gen.LAY_TERMS.values()) | {"a little white one"}
    rows = [r for rs in world.rows_by_key.values() for r in rs if r.has_med]
    for source in ("emr", "gp", "pharmacy"):
        mine = [r for r in rows if r.source == source]
        assert all(normalise_med(r, world.lex).resolution != "unmapped" for r in mine), source
    patient = [r for r in rows if r.source == "patient"]
    statements = [normalise_med(r, world.lex) for r in patient]
    rate = sum(s.resolution != "unmapped" for s in statements) / len(patient)
    assert rate >= 0.83, f"patient free-text top-1 {rate:.3f}"
    stray = [r.med_text for r, s in zip(patient, statements)
             if s.resolution == "unmapped" and r.med_text not in vague]
    assert not stray, f"resolvable descriptions left unmapped: {stray[:5]}"
