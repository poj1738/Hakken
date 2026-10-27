#!/usr/bin/env python3
"""Zetaris scoring 2a: one USL question answered by hand, compared honestly with the USL.

    python3 scripts/handcoded_comparison.py

The question (USL result `1c_usl_2`): for each APINCHS high-risk class, how many medicine
lines and how many distinct patient IDs does each source hold?

By hand that means fetching six sources from `datasvc`, knowing each silo's own field names,
resolving three coding systems (plus a brand fallback) against the lexicon, matching ATC codes
to APINCHS by longest prefix, and aggregating. The hand-coded part sits between the BEGIN/END
markers below, so its size is measured from this file rather than claimed.

Plain Python (stdlib only), not pandas: pandas is not a project dependency, and adding one on
deadline day was not worth it. pandas would shorten the joins; it would not remove a single
mapping step. Saves `docs/zetaris_usl/results/2a_handcoded_comparison.json`.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.zetaris import ZetarisClient  # noqa: E402
from app.config import get_settings  # noqa: E402

OUT = ROOT / "docs" / "zetaris_usl" / "results" / "2a_handcoded_comparison.json"
USL_SQL = ("SELECT high_risk_class, source_system, COUNT(*) AS lines, COUNT(DISTINCT patient_id) AS patients "
           "FROM lightning.metastore.medtrace.medtrace_usl.medication_statement WHERE high_risk_class IS NOT NULL "
           "GROUP BY high_risk_class, source_system ORDER BY high_risk_class, source_system")

# ---- BEGIN hand-coded ----------------------------------------------------------------
# Manual mapping steps, each one knowledge the hand-coder must hold and keep current:
MAPPING_STEPS = [
    "Know each silo's endpoint and envelope ({'records': [...]}) -- 6 sources",
    "Map each silo's patient-ID field: emr.mrn, gp.gp_pid, pharmacy.cust_no, patient.intake_id",
    "Map each silo's medicine-code field: emr.amt_mp_code, gp.amt_code, pharmacy.pbs_code",
    "Know EMR codes are AMT medicinal products (lexicon.amt_mp)",
    "Know GP codes are AMT medicinal product PACKS (lexicon.amt_mpp), not amt_mp",
    "Know pharmacy codes are PBS item codes (lexicon.pbs_code), and that pbs_code is not unique",
    "Know private scripts carry no PBS code and must resolve by brand, case-insensitively",
    "Know patient interview lines carry no code and cannot be resolved by code",
    "Build one lookup per coding system from the lexicon",
    "Match ATC to APINCHS by the LONGEST matching prefix",
    "Aggregate lines and distinct patient IDs per (class, source)",
]

SILO_FIELDS = {  # source -> (patient-id field, code field, lookup used for that code)
    "emr": ("mrn", "amt_mp_code", "amt_mp"),
    "gp": ("gp_pid", "amt_code", "amt_mpp"),
    "pharmacy": ("cust_no", "pbs_code", "pbs_code"),
    "patient": ("intake_id", None, None),
}


def fetch(base: str, path: str) -> list[dict]:
    with urllib.request.urlopen(f"{base}{path}", timeout=120) as resp:
        return json.loads(resp.read())["records"]


def handcoded(base: str) -> dict[tuple[str, str], tuple[int, int]]:
    silos = {s: fetch(base, f"/silos/{s}") for s in SILO_FIELDS}
    lexicon, apinchs = fetch(base, "/ref/lexicon"), fetch(base, "/ref/apinchs")

    lookups: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for row in lexicon:
        for key in ("amt_mp", "amt_mpp", "pbs_code"):
            if row.get(key):
                lookups[key][row[key]] = (row["generic"], row["atc_primary"])
        if row.get("brand"):
            lookups["brand"][row["brand"].lower()] = (row["generic"], row["atc_primary"])
    prefixes = sorted(apinchs, key=lambda r: len(r["atc_prefix"]), reverse=True)

    def high_risk(atc: str | None) -> str | None:
        return next((p["apinchs_class"] for p in prefixes if atc and atc.startswith(p["atc_prefix"])), None)

    lines: dict[tuple[str, str], int] = defaultdict(int)
    patients: dict[tuple[str, str], set] = defaultdict(set)
    for source, rows in silos.items():
        pid_field, code_field, lookup = SILO_FIELDS[source]
        for row in rows:
            if lookup is None:
                continue  # free text: unresolvable by code
            if source == "pharmacy" and row.get("script_type") == "private":
                hit = lookups["brand"].get((row.get("brand") or "").lower())
            else:
                hit = lookups[lookup].get(row.get(code_field) or "")
            cls = high_risk(hit[1]) if hit else None
            if cls:
                lines[(cls, source)] += 1
                patients[(cls, source)].add(row.get(pid_field))
    return {k: (lines[k], len(patients[k])) for k in lines}
# ---- END hand-coded ------------------------------------------------------------------


def _hand_coded_size() -> dict[str, int]:
    text = Path(__file__).read_text().split("# ---- BEGIN hand-coded")[1].split("# ---- END hand-coded")[0]
    code = [l for l in text.splitlines()[1:] if l.strip() and not l.strip().startswith("#")]
    return {"lines_of_code": len(code), "manual_mapping_steps": len(MAPPING_STEPS)}


def main() -> int:
    settings = get_settings()
    base = settings.datasvc_internal_url.rstrip("/")

    start = time.monotonic()
    hand = handcoded(base)
    hand_s = time.monotonic() - start

    client = ZetarisClient(settings.model_copy(update={"sample_mode": False}))
    start = time.monotonic()
    result, record = client.run(USL_SQL, template_id="2a_usl", limit=1000)
    usl_s = time.monotonic() - start
    usl = {(r[0], r[1]): (int(r[2]), int(r[3])) for r in result["data"]}

    differences = [{"high_risk_class": k[0], "source": k[1], "usl": usl.get(k), "hand_coded": hand.get(k)}
                   for k in sorted(set(usl) | set(hand)) if usl.get(k) != hand.get(k)]
    usl_files = ["07_usl_activate_medication_statement.sql"]
    usl_build_lines = sum(1 for f in usl_files for l in (ROOT / "data/zetaris/usl" / f).read_text().splitlines()
                          if l.strip() and not l.strip().startswith("--"))
    report = {
        "id": "2a_handcoded_comparison",
        "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": "Lines and distinct patient IDs per APINCHS high-risk class and source",
        "usl": {"sql": USL_SQL, "query_lines": 1, "runtime_s": round(usl_s, 2), "zetaris_ms": record.ms,
                "rows": len(usl), "one_time_activation_sql_lines": usl_build_lines},
        "hand_coded": {**_hand_coded_size(), "runtime_s": round(hand_s, 2), "rows": len(hand),
                       "mapping_steps": MAPPING_STEPS, "implementation": "Python stdlib (no pandas)"},
        "results_match_exactly": not differences,
        "differences": differences,
        "rows": [{"high_risk_class": k[0], "source": k[1], "lines": v[0], "patients": v[1]}
                 for k, v in sorted(hand.items())],
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"USL        {report['usl']['runtime_s']:6.2f}s  {len(usl)} rows  (1 query)")
    print(f"hand-coded {report['hand_coded']['runtime_s']:6.2f}s  {len(hand)} rows  "
          f"({report['hand_coded']['lines_of_code']} lines, {len(MAPPING_STEPS)} mapping steps)")
    print("match exactly:", report["results_match_exactly"], "| differences:", len(differences))
    for d in differences:
        print("  ", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
