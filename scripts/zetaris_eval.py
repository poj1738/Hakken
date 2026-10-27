#!/usr/bin/env python3
"""Run the Zetaris Scoring Methodology evidence live and save every result (docs/zetaris_usl/).

    python3 scripts/zetaris_eval.py            # all of it, live
    python3 scripts/zetaris_eval.py --only 1c  # one part

Each query is saved to `docs/zetaris_usl/results/<id>.json` with its SQL, row count, the
first 10 rows, latency and a UTC timestamp, plus `index.json` listing them all. Nothing in
the docs is typed by hand: `scripts/zetaris_docs.py` renders them from these files.

Queries go through the app's own read-only adapter (`app/adapters/zetaris.py`: SELECT,
SHOW, DESCRIBE or WITH only). The three data-quality commands (`LIST DQ`, `RUN DQ`,
`SHOW DQ`) are not in that read-only set, so they use `register_sources.py`'s build-time
client. Each result says which client ran it. Read-only throughout: nothing is created.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.adapters.zetaris import ZetarisClient, ZetarisError  # noqa: E402
from app.config import get_settings  # noqa: E402

OUT = ROOT / "docs" / "zetaris_usl" / "results"
USL = "lightning.metastore.medtrace.medtrace_usl"

#: (id, part, source, question, sql). 1b: 2-3 real questions per source; 1c: the USL.
QUERIES: list[tuple[str, str, str, str, str]] = [
    # -- 1b: hospital EMR -------------------------------------------------------------
    ("1b_emr_1", "1b", "Hospital EMR", "How many patients and medicine lines does the EMR hold, by record kind?",
     "SELECT record_kind, COUNT(DISTINCT source_patient_id) AS patients, COUNT(*) AS lines "
     "FROM medtrace.EMR GROUP BY record_kind ORDER BY lines DESC"),
    ("1b_emr_2", "1b", "Hospital EMR", "Which medicines are charted most often on admission?",
     "SELECT med_text AS medicine, COUNT(*) AS charted FROM medtrace.EMR "
     "WHERE record_kind = 'admission_chart' GROUP BY med_text ORDER BY charted DESC LIMIT 10"),
    ("1b_emr_3", "1b", "Hospital EMR", "Which chart notes document a medicine as withheld, and how often?",
     "SELECT note_text, COUNT(*) AS lines FROM medtrace.EMR "
     "WHERE note_text IS NOT NULL AND note_text <> '' GROUP BY note_text ORDER BY lines DESC"),
    # -- 1b: GP -------------------------------------------------------------------------
    ("1b_gp_1", "1b", "GP", "How many patients does the GP silo cover, and what status are their medicines in?",
     "SELECT status_text, COUNT(DISTINCT source_patient_id) AS patients, COUNT(*) AS lines "
     "FROM medtrace.GP GROUP BY status_text ORDER BY lines DESC"),
    ("1b_gp_2", "1b", "GP", "Which GP directions give no dose a pharmacist could confirm?",
     "SELECT freq_text AS directions, COUNT(*) AS lines FROM medtrace.GP "
     "WHERE lower(freq_text) LIKE '%as directed%' OR lower(freq_text) LIKE '%per inr%' "
     "OR lower(freq_text) LIKE '%variable%' GROUP BY freq_text ORDER BY lines DESC"),
    ("1b_gp_3", "1b", "GP", "How old are the GP medication lists (year of last update)?",
     "SELECT substring(doc_date, 7, 4) AS year_updated, COUNT(DISTINCT source_patient_id) AS patients "
     "FROM medtrace.GP GROUP BY substring(doc_date, 7, 4) ORDER BY year_updated"),
    # -- 1b: community pharmacy ---------------------------------------------------------
    ("1b_pharmacy_1", "1b", "Community pharmacy", "What are the most-dispensed products?",
     "SELECT med_text AS product, strength_text AS strength, COUNT(*) AS fills FROM medtrace.PHARMACY "
     "GROUP BY med_text, strength_text ORDER BY fills DESC LIMIT 10"),
    ("1b_pharmacy_2", "1b", "Community pharmacy", "How many fills are PBS and how many private (no PBS code)?",
     "SELECT script_type, COUNT(*) AS fills, COUNT(DISTINCT source_patient_id) AS patients "
     "FROM medtrace.PHARMACY GROUP BY script_type"),
    ("1b_pharmacy_3", "1b", "Community pharmacy", "How many patients fill at more than one pharmacy?",
     "SELECT pharmacies, COUNT(*) AS patients FROM (SELECT source_patient_id, "
     "COUNT(DISTINCT pharmacy_id) AS pharmacies FROM medtrace.PHARMACY GROUP BY source_patient_id) p "
     "GROUP BY pharmacies ORDER BY pharmacies"),
    # -- 1b: patient interview ----------------------------------------------------------
    ("1b_patient_1", "1b", "Patient interview", "How do patients answer 'are you taking this?'",
     "SELECT status_text AS answer, COUNT(*) AS lines, COUNT(DISTINCT source_patient_id) AS patients "
     "FROM medtrace.PATIENT_REPORT GROUP BY status_text ORDER BY lines DESC"),
    ("1b_patient_2", "1b", "Patient interview", "Which free-text descriptions do patients use most (no code at all)?",
     "SELECT med_text AS patient_words, COUNT(*) AS lines FROM medtrace.PATIENT_REPORT "
     "GROUP BY med_text ORDER BY lines DESC LIMIT 10"),
    # -- 1b: PBS medicines lexicon ------------------------------------------------------
    ("1b_lexicon_1", "1b", "PBS medicines lexicon", "How many products and generics per ATC anatomical group?",
     "SELECT substring(atc_primary, 1, 1) AS atc_group, COUNT(*) AS products, COUNT(DISTINCT generic) AS generics "
     "FROM medtrace.MED_LEXICON GROUP BY substring(atc_primary, 1, 1) ORDER BY products DESC"),
    ("1b_lexicon_2", "1b", "PBS medicines lexicon", "Which generics come in the most strengths (where a dose can go wrong)?",
     "SELECT generic, COUNT(DISTINCT strength) AS strengths, COUNT(*) AS products FROM medtrace.MED_LEXICON "
     "GROUP BY generic ORDER BY strengths DESC, generic LIMIT 10"),
    # -- 1b: APINCHS --------------------------------------------------------------------
    ("1b_apinchs_1", "1b", "ACSQHC APINCHS", "Which high-risk classes are there, and how many ATC prefixes define each?",
     "SELECT apinchs_class, COUNT(*) AS atc_prefixes FROM medtrace.APINCHS "
     "GROUP BY apinchs_class ORDER BY atc_prefixes DESC"),
    ("1b_apinchs_2", "1b", "ACSQHC APINCHS",
     "Which ATC prefixes put a medicine in APINCHS class I (insulins) or H (heparin and anticoagulants)?",
     "SELECT apinchs_class, atc_prefix, label FROM medtrace.APINCHS "
     "WHERE apinchs_class IN ('I', 'H') ORDER BY apinchs_class, atc_prefix"),
    # -- 1c: the USL is active -------------------------------------------------------------
    ("1c_usl_1", "1c", "USL", "Is the USL active? Every line from four silos, resolved to a medicine, in one table.",
     f"SELECT source_system, resolved_by, COUNT(*) AS lines, COUNT(generic) AS resolved, "
     f"COUNT(high_risk_class) AS high_risk_lines FROM {USL}.medication_statement "
     f"GROUP BY source_system, resolved_by ORDER BY source_system"),
    ("1c_usl_2", "1c", "USL",
     "Which high-risk classes appear in which source? (Without the USL: 4 silos x 3 coding systems + lexicon + APINCHS.)",
     f"SELECT high_risk_class, source_system, COUNT(*) AS lines, COUNT(DISTINCT patient_id) AS patients "
     f"FROM {USL}.medication_statement WHERE high_risk_class IS NOT NULL "
     f"GROUP BY high_risk_class, source_system ORDER BY high_risk_class, source_system"),
    ("1c_usl_3", "1c", "USL", "For each strength that is not a real product, what strengths does the medicine come in?",
     f"SELECT s.row_id, s.patient_id, s.generic, s.strength_text AS charted, m.strengths AS made_in "
     f"FROM {USL}.medication_statement s JOIN {USL}.medicine m ON s.generic = m.generic "
     f"WHERE s.strength_listed = false ORDER BY s.row_id"),
    ("1c_usl_tables", "1c", "USL", "The USL's tables and activation state.",
     "SHOW NAMESPACES OR TABLES IN lightning.metastore.medtrace"),
]

#: Native data-quality commands (build-time client: not in the adapter's read-only set).
DQ_COMMANDS: list[tuple[str, str, str, str]] = [
    ("1c_dq_list", "1c", "Which data-quality rules does the USL carry?", f"LIST DQ USL {USL}"),
    ("1c_dq_run", "1c", "Run the custom rule: is every charted strength a real product?",
     f"RUN DQ strength_is_a_real_product TABLE {USL}.medication_statement"),
    ("1c_dq_invalid", "1c", "Which records fail it?",
     f"SHOW DQ INVALID RECORD strength_is_a_real_product TABLE {USL}.medication_statement"),
    ("1c_dq_fk", "1c", "Run the foreign-key rule: does every resolved generic exist in medicine?",
     f"RUN DQ generic TABLE {USL}.medication_statement"),
]


def _save(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{entry['id']}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
    status = entry.get("error") or f"{entry['row_count']} rows"
    print(f"  {entry['id']:16} {entry['latency_ms']:7d} ms  {status[:120]}", flush=True)


def _entry(qid: str, part: str, source: str, question: str, sql: str, client: str, headers: list,
           rows: list, ms: int, error: str | None) -> dict:
    return {"id": qid, "part": part, "source": source, "question": question, "sql": sql, "client": client,
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "latency_ms": ms, "row_count": None if error else len(rows), "headers": headers,
            "first_rows": rows[:10], "error": error,
            # Small results are kept whole, so the docs can check every row (e.g. each DQ violation).
            **({"all_rows": rows} if not error and len(rows) <= 100 else {})}


def run(only: str | None = None) -> int:
    adapter = ZetarisClient(get_settings().model_copy(update={"sample_mode": False}))
    failures, index = 0, []
    for qid, part, source, question, sql in QUERIES:
        if only and part != only:
            continue
        try:
            # High limit: these are evidence, not agent queries (the adapter enforces a LIMIT).
            result, record = adapter.run(sql, template_id=qid, limit=1000)
            entry = _entry(qid, part, source, question, sql, "app/adapters/zetaris.py (read-only)",
                           list(result["headers"]), [list(r) for r in result["data"]], record.ms, None)
        except ZetarisError as exc:
            entry = _entry(qid, part, source, question, sql, "app/adapters/zetaris.py (read-only)",
                           [], [], 0, str(exc)[:500])
        failures += entry["error"] is not None
        _save(entry)
        index.append({k: entry[k] for k in ("id", "part", "source", "question", "row_count", "error")})
    if not only or only == "1c":
        from register_sources import Zetaris  # build-time client; reads ZETARIS_API_KEY by name

        client = Zetaris()
        for qid, part, question, sql in DQ_COMMANDS:
            start = time.monotonic()
            result, _secs, error = client.run(sql)
            ms = int((time.monotonic() - start) * 1000)
            entry = _entry(qid, part, "USL data quality", question, sql, "scripts/register_sources.py (build-time)",
                           list(result["headers"]) if result else [],
                           [list(r) for r in result["data"]] if result else [], ms, error)
            failures += entry["error"] is not None
            _save(entry)
            index.append({k: entry[k] for k in ("id", "part", "source", "question", "row_count", "error")})
    existing = {}
    if (OUT / "index.json").exists():
        existing = {e["id"]: e for e in json.loads((OUT / "index.json").read_text())["results"]}
    existing.update({e["id"]: e for e in index})
    (OUT / "index.json").write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "results": sorted(existing.values(), key=lambda e: e["id"])}, indent=2) + "\n")
    print(f"{len(index)} results, {failures} failed -> {OUT.relative_to(ROOT)}/")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=["1b", "1c"])
    return run(ap.parse_args().only)


if __name__ == "__main__":
    sys.exit(main())
