"""output_examples/ are real runs, differ by input, and still match the code (rule 6, scan S2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.schemas import RunResponse

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output_examples"
NAMES = ["example_1", "example_2", "example_3", "example_4_learning_teach", "example_5_learning_learn"]


def _load(mode: str, name: str) -> RunResponse:
    return RunResponse.model_validate_json((OUT / mode / f"{name}.json").read_text())


def _findings(r: RunResponse) -> set[tuple[str, str]]:
    return {(f.type.value, f.generic) for f in r.findings}


def _generator():
    spec = importlib.util.spec_from_file_location("generate_examples", ROOT / "scripts" / "generate_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.mark.parametrize("name", NAMES)
def test_every_sample_example_is_a_valid_run_with_a_trace(name) -> None:
    r = _load("sample_mode", name)
    assert r.status == "success" and r.sample_mode
    trace = [json.loads(line) for line in (OUT / "sample_mode" / f"{name}.trace.jsonl").read_text().splitlines()]
    assert trace and trace[-1]["run_id"] == r.run_id


def test_outputs_differ_by_input() -> None:
    sets = [frozenset(_findings(_load("sample_mode", n))) for n in NAMES]
    non_empty = [s for s in sets if s]
    assert len(set(non_empty)) == len(non_empty)  # no two inputs gave the same findings


def test_examples_show_what_input_examples_readme_promises() -> None:
    assert (OUT / "sample_mode" / "example_1.needs_review.json").exists()
    assert ("dose_unconfirmable", "warfarin") in _findings(_load("sample_mode", "example_1"))
    ex3 = _load("sample_mode", "example_3")
    assert ex3.findings == [] and not ex3.bpmh_confirmable
    assert ("dose", "rosuvastatin") in _findings(_load("sample_mode", "example_5_learning_learn"))
    fb = json.loads((OUT / "sample_mode" / "example_4_learning_teach.feedback.json").read_text())
    assert fb["trust_updates"][0]["before"] == 0.7 and fb["trust_updates"][0]["after"] == 0.5


def test_live_examples_name_the_nemotron_that_answered() -> None:
    if not (OUT / "live").exists():
        pytest.skip("no live examples committed")
    for name in NAMES:
        r = _load("live", name)
        assert not r.sample_mode
        answered = {c.routed_model for c in r.model_calls if c.routed_model}
        assert answered and all(m.startswith("nvidia/") for m in answered), answered
        # A request no model answered is listed with no model (scan S9) -- only in a run that says so.
        if any(c.routed_model is None for c in r.model_calls):
            assert r.status == "partial", name


def test_committed_sample_examples_match_a_fresh_regeneration(tmp_path, make_settings) -> None:
    """Stale examples would show findings the code no longer produces."""
    _generator().run_mode("sample_mode", out_root=tmp_path, settings=make_settings())
    for name in NAMES:
        fresh = RunResponse.model_validate_json((tmp_path / "sample_mode" / f"{name}.json").read_text())
        assert _findings(fresh) == _findings(_load("sample_mode", name)), name
