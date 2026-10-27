"""Scan S42: each TGA shortage row is ranked against the patient's own product. Rows are
hand-written in the export's shape (no TGA data is committed); no network."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.adapters.meterless import MeterlessClient
from app.adapters.zetaris import ZetarisClient
from app.agents import executor
from app.agents.executor import AFFECTS, OTHER_PRODUCT, _patient_products, _Product, _relevance
from app.domain.packs.medtrace.types import MedStatement, NoticeType
from app.orchestrator import Orchestrator
from app.schemas import RunRequest

ORAL_ENDONE = _Product(brands={"endone"}, strengths={5.0}, families={"oral"}, label="Endone 5 mg")


def tga(name: str, form: str, generic: str = "oxycodone") -> dict[str, str | None]:
    return {"generic": generic, "medicine_name": name, "dosage_form": form, "status": "Current",
            "expected_resolution": "2026-10-30", "salt_quantity": "999"}


@pytest.mark.parametrize("row,product,expected", [
    (tga("ENDONE oxycodone hydrochloride 5 mg tablet", "Tablet"), ORAL_ENDONE, AFFECTS),
    (tga("OXYNORM oxycodone hydrochloride 5 mg capsule", "Capsule"), ORAL_ENDONE, OTHER_PRODUCT),
    (tga("OXYCODONE MEDSURGE oxycodone hydrochloride 20 mg/2 mL injection ampoule", "Injection, solution"),
     ORAL_ENDONE, None),
    # No brand in the patient's records: the same strength (and route) is what matches.
    (tga("APO-ESOMEPRAZOLE esomeprazole 40 mg tablet", "Tablet, enteric coated", "esomeprazole"),
     _Product(strengths={40.0}, families={"oral"}), AFFECTS),
    (tga("NOXICID esomeprazole 20 mg tablet", "Tablet, enteric coated", "esomeprazole"),
     _Product(strengths={40.0}, families={"oral"}), OTHER_PRODUCT),
    (tga("LANOXIN digoxin 62.5 microgram tablet", "Tablet", "digoxin"),
     _Product(strengths={0.0625}, families={"oral"}), AFFECTS),
])
def test_relevance(row, product, expected) -> None:
    assert _relevance(row, product) == expected


def test_salt_quantity_is_never_read_as_strength() -> None:
    row = tga("GENERIC oxycodone tablet", "Tablet") | {"salt_quantity": "5"}
    assert _relevance(row, _Product(strengths={5.0}, families={"oral"})) == OTHER_PRODUCT


def test_the_patients_product_comes_from_their_own_rows() -> None:
    lex = SimpleNamespace(by_brand={"endone": SimpleNamespace(generic="oxycodone"),
                                    "oxynorm": SimpleNamespace(generic="oxycodone")})
    stmts = [MedStatement(source="pharmacy", row_id="PHM-1", raw_text="Endone", generic="oxycodone",
                          route="PO", status="active", doc_date=date(2026, 10, 1), resolution="lexicon")]
    raw = {"PHM-1": {"source": "pharmacy", "med_text": "Endone", "strength_text": "5 mg", "route_text": "tablet"}}
    p = _patient_products(["oxycodone"], stmts, raw, lex)["oxycodone"]
    assert p.brands == {"endone"} and p.strengths == {5.0} and p.families == {"oral"}
    assert p.label == "Endone 5 mg"


def _no_network(_request: httpx.Request) -> httpx.Response:
    raise AssertionError("network used")


def test_notices_carry_relevance_and_no_repeated_disclaimer(make_settings, tmp_path, monkeypatch) -> None:
    s = make_settings(sample_mode=True)
    no_net = httpx.MockTransport(_no_network)
    orch = Orchestrator(s, llm=MeterlessClient(s, transport=no_net), zetaris=ZetarisClient(s, transport=no_net),
                        log_dir=tmp_path)
    ctx = orch.runs[orch.create(RunRequest(patient_id="MRN0000089"))].ctx
    rows = [tga("ENDONE oxycodone hydrochloride 5 mg tablet", "Tablet"),
            tga("OXYNORM oxycodone hydrochloride 10 mg capsule", "Capsule"),
            tga("OXYCODONE MEDSURGE oxycodone 20 mg/2 mL injection ampoule", "Injection, solution")]
    headers = list(rows[0])
    record = SimpleNamespace(trace_fields=lambda: {"sql_template_id": "Q4"})
    monkeypatch.setattr(ctx.zetaris, "run", lambda *_a, **_kw: ({"headers": headers,
                                                                 "data": [[r[h] for h in headers] for r in rows]},
                                                                record))
    monkeypatch.setattr(executor, "_patient_products", lambda gs, *_a: {g: ORAL_ENDONE for g in gs})
    notices = executor.check_shortages(ctx, orch.runs[next(iter(orch.runs))].anchor, ["oxycodone"])
    assert [n.relevance for n in notices] == [AFFECTS, OTHER_PRODUCT]  # the ampoule is dropped
    assert all(n.type is NoticeType.KNOWN_SHORTAGE and "incomplete" not in n.detail for n in notices)
    assert "It matches the patient's product (Endone 5 mg)" in notices[0].detail
    assert notices[0].tasks and not notices[1].tasks
    assert "1 dropped" in ctx.tracer.events[-1].message
