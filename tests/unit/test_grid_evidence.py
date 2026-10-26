"""Anshu's asks (HANDOFF 26 Oct 12:16): every row behind a grid cell is in `evidence_index`,
and a resolved daily dose says what unit it is in. No network."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents.evaluator import _dose_units, _row_dose_unit
from app.domain.packs.medtrace.types import FusedMed, FusedValue
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


@pytest.mark.parametrize("mrn", ["MRN0000001", "MRN0000089"])
def test_every_grid_row_is_in_the_evidence_index(orch, mrn) -> None:
    r = orch.start(RunRequest(patient_id=mrn))
    cited = {x for m in r.grid for x in [*m.row_ids, *(y for v in m.attributes.values() for y in v.row_ids)]}
    assert cited and cited <= set(r.evidence_index)
    for rid in cited:
        ev = r.evidence_index[rid]
        assert ev.row_id == rid and ev.sql_template_id == "Q2" and ev.fields


def test_p0001_dose_units(orch) -> None:
    r = orch.start(RunRequest(patient_id="MRN0000001"))
    assert r.dose_units["amlodipine"] == "mg"
    assert r.dose_units["colecalciferol"] == "units"        # IU are not a mass
    assert r.dose_units["empagliflozin/metformin"] == "mg"  # first component of "25/1000 mg"
    resolved = {m.generic for m in r.grid if (d := m.attributes.get("daily_dose")) and d.value is not None}
    assert set(r.dose_units) <= resolved


@pytest.mark.parametrize("fields,unit", [
    ({"strength_text": "5 mg"}, "mg"),
    ({"strength_text": "62.5 microgram"}, "mg"),     # converted to mg by parse_strength_mg
    ({"strength_text": "1 g"}, "mg"),
    ({"strength_text": "1000 IU"}, "units"),
    ({"strength_text": "25/1000 mg"}, "mg"),
    ({"strength_text": "100 units/mL", "freq_text": "10 to 40 units nocte"}, "units"),  # stated dose wins
    ({"dose_text": "10 mL"}, "mL"),
    ({"dose_text": "2 puffs"}, None),                 # no unit stated: not labelled
    ({"strength_text": None}, None),
])
def test_row_dose_unit(fields, unit) -> None:
    assert _row_dose_unit(fields) == unit


def test_disagreeing_or_unstated_rows_give_no_unit() -> None:
    def med(generic: str, rows: list[str]) -> FusedMed:
        return FusedMed(generic=generic, attributes={"daily_dose": FusedValue(attribute="daily_dose", value=10.0,
                                                                               row_ids=rows)})
    raw = {"A": {"strength_text": "10 mg"}, "B": {"strength_text": "10 units"}, "C": {"dose_text": "10"}}
    assert _dose_units([med("x", ["A"]), med("y", ["A", "B"]), med("z", ["A", "C"])], raw) == {"x": "mg"}
