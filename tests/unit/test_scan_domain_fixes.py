"""Scan S20, S32, S33 (Arpon's domain items, handed to Arnav): regression tests. No network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents import executor
from app.domain.packs.medtrace.coverage import _accepted
from app.domain.packs.medtrace.fuse import _resolve
from app.domain.packs.medtrace.types import IdentityLink
from app.orchestrator import Orchestrator
from app.schemas import RunRequest


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used in SAMPLE_MODE")


@pytest.fixture
def orch(make_settings: Callable[..., Any], tmp_path) -> Orchestrator:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    return Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)


# -- S20: a finding resting on a model-resolved line needs a pharmacist -----------------


def test_findings_carry_the_weakest_resolution_behind_them(orch) -> None:
    r = orch.start(RunRequest(patient_id="MRN0000089"))
    assert all(f.detail.get("resolution") in ("code", "lexicon", "fuzzy") for f in r.findings)
    esomeprazole = next(f for f in r.findings if f.id == "frequency:esomeprazole")
    assert not esomeprazole.needs_pharmacist  # not high-risk, resolved by code/lexicon


def test_a_model_resolved_line_routes_the_finding_to_the_pharmacist(orch, monkeypatch) -> None:
    """Before S20 safety_gate read detail['resolution'], which nothing set: the rule never fired."""
    real = executor.normalise

    def normalise(ctx, rows):
        return [s.model_copy(update={"resolution": "llm"}) if s.generic == "esomeprazole" and s.source == "gp"
                else s for s in real(ctx, rows)]

    monkeypatch.setattr(executor, "normalise", normalise)
    r = orch.start(RunRequest(patient_id="MRN0000089"))
    f = next(f for f in r.findings if f.id == "frequency:esomeprazole")
    assert f.detail["resolution"] == "llm" and f.needs_pharmacist
    assert any("Confirm the medicine name" in t for t in f.tasks)


# -- S32: no weight behind the leader is no answer ----------------------------------------


def test_every_voter_at_zero_trust_abstains() -> None:
    v = _resolve("daily_dose", {"gp": (10.0, 0.0, "GP-1"), "pharmacy": (20.0, 0.0, "PHM-1")}, margin=0.10)
    assert v.abstained and v.value is None and not v.supporting


def test_a_sole_voter_at_zero_trust_abstains() -> None:
    v = _resolve("daily_dose", {"gp": (10.0, 0.0, "GP-1")}, margin=0.10)
    assert v.abstained and v.value is None


def test_a_trusted_sole_voter_still_wins() -> None:
    v = _resolve("daily_dose", {"gp": (10.0, 0.7, "GP-1")}, margin=0.10)
    assert not v.abstained and v.value == 10.0 and v.supporting == ["gp"]


# -- S33: the anchor is always found --------------------------------------------------------


def _link(candidate: str, band: str) -> IdentityLink:
    return IdentityLink(anchor_id="emr:MRN0000001", candidate_id=candidate, match_weight=1.0, probability=0.8,
                        band=band, tier="probabilistic")  # type: ignore[arg-type]


def test_a_review_band_link_does_not_make_the_anchor_pending() -> None:
    best = _accepted([_link("gp:GP0001", "review")])
    assert best["emr"] == ("emr:MRN0000001", "auto-merge")
    assert best["gp"] == ("gp:GP0001", "review")


def test_a_new_band_link_still_leaves_the_anchor_found() -> None:
    best = _accepted([_link("gp:GP0002", "new")])
    assert best == {"emr": ("emr:MRN0000001", "auto-merge")}
