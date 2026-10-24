#!/usr/bin/env python3
"""Parse the TGA Medicine Shortage Reports CSV export. **Not wired up.**

Q4 / `MT_TGA` / `/ref/tga` / `medtrace.tga_shortages` is **Monday, optional**, and
sixth in PLAN section 4's cut order. This script exists so that Monday is a
registration step rather than a parsing problem; nothing imports it, nothing
registers its output, and `queries.q_shortages` still raises.

**The shortage database is incomplete, so it is never ground truth.** Anything
derived from it is rendered as `NoticeType.KNOWN_SHORTAGE` -- "known shortage" --
and never as "unavailable". A medicine missing from this file says nothing.

Format facts, all of which the export actually requires (and none of which a
naive `csv.DictReader` gets right):

  * `utf-8-sig` -- the file carries a BOM.
  * A ~10-line preamble sits above the header, so the header row has to be
    found by looking for `ARTG ID` rather than assumed to be line 1.
  * 16 columns. `Phone` is dropped: it is a contact detail we have no use for,
    and keeping personal contact data in a synthetic-data project is worse than
    pointless.
  * Ingredients are `~`-separated **in either order**, so they are split and
    sorted rather than read positionally.
  * `Quantity of active ingredients` is **salt mass, not strength.** It must
    never be compared with a dispensed strength; doing so would manufacture a
    dose discrepancy out of a formulation difference.
  * Dates are **day-first** (`DD/MM/YYYY`).
  * Status is one of `Current`, `Anticipated`, `Resolved`, `Discontinued`.
    **Only `Current` and `Anticipated` produce a notice.**

Usage:
    python3 scripts/load_tga_shortages.py                     # default input
    python3 scripts/load_tga_shortages.py --in <csv> --out <json>
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import sys

DEFAULT_IN = pathlib.Path("data/reference/raw/tga_shortages_active_20261024.csv")
DEFAULT_OUT = pathlib.Path("data/reference/tga_shortages.json")

HEADER_MARKER = "ARTG ID"
DROP_COLUMNS = {"Phone"}

#: Only these two statuses mean "a pharmacist might care right now".
NOTIFIABLE_STATUSES = frozenset({"Current", "Anticipated"})
ALL_STATUSES = frozenset({"Current", "Anticipated", "Resolved", "Discontinued"})

#: Served columns. `salt_quantity` is named to make its meaning unmistakable.
OUT_COLUMNS = (
    "artg_id", "medicine_name", "sponsor", "ingredients", "salt_quantity",
    "dosage_form", "status", "shortage_start", "expected_resolution",
    "impact_rating",
    "availability", "reason", "notifiable",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def find_header(text: str) -> int:
    """Index of the header line. The preamble length is not guaranteed."""
    for i, line in enumerate(text.splitlines()):
        if HEADER_MARKER.lower() in line.lower():
            return i
    raise ValueError(
        f"no header row containing {HEADER_MARKER!r} found. This is probably not "
        f"the TGA shortage export, or its format has changed -- stop and look at it."
    )


def split_ingredients(raw: str) -> list[str]:
    """`"a~b"` -> `["a", "b"]`, sorted, because the export's order is not stable."""
    parts = [p.strip() for p in (raw or "").split("~")]
    return sorted(p for p in parts if p)


def parse_day_first(raw: str) -> str | None:
    """`DD/MM/YYYY` -> ISO. Returns None rather than guessing on anything else."""
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _pick(row: dict[str, str], *candidates: str) -> str:
    """First non-empty column whose name contains one of `candidates`."""
    for want in candidates:
        for key, value in row.items():
            if key and want.lower() in key.lower() and (value or "").strip():
                return value.strip()
    return ""


def parse(text: str) -> list[dict[str, object]]:
    start = find_header(text)
    body = "\n".join(text.splitlines()[start:])
    reader = csv.DictReader(io.StringIO(body))
    out: list[dict[str, object]] = []
    unknown_statuses: set[str] = set()
    for raw in reader:
        row = {k: v for k, v in raw.items() if k and k not in DROP_COLUMNS}
        artg = _pick(row, "ARTG ID")
        if not artg:
            continue
        status = _pick(row, "Status")
        if status and status not in ALL_STATUSES:
            unknown_statuses.add(status)
        out.append({
            "artg_id": artg,
            # The column is "ARTG name". "Medicine name" matched nothing, so
            # this was empty for all 1,010 rows while the loader reported
            # success -- a row count is not a shape check.
            "medicine_name": _pick(row, "ARTG name", "Medicine name", "Medicine"),
            "sponsor": _pick(row, "Sponsor"),
            "ingredients": split_ingredients(_pick(row, "ingredient")),
            # Salt mass. NOT a dispensed strength -- see the module docstring.
            "salt_quantity": _pick(row, "Quantity of active"),
            "dosage_form": _pick(row, "Dosage form", "form"),
            "status": status,
            "shortage_start": parse_day_first(_pick(row, "start")),
            "expected_resolution": parse_day_first(
                _pick(row, "Supply impact end date", "resolution", "expected")),
            # How badly the shortage bites. Critical and Low are not the same
            # notice, so the triage layer needs this rather than inferring it.
            "impact_rating": _pick(row, "Shortage impact rating", "impact rating"),
            "availability": _pick(row, "Availability"),
            "reason": _pick(row, "Reason"),
            "notifiable": status in NOTIFIABLE_STATUSES,
        })
    if unknown_statuses:
        log(f"  WARNING unexpected status value(s): {sorted(unknown_statuses)} -- "
            f"expected {sorted(ALL_STATUSES)}. Check before Monday's registration.")
    # A column name that matches nothing yields "" for every row, and the
    # loader still reports a healthy row count. That is exactly how
    # medicine_name and expected_resolution stayed empty for all 1,010 rows
    # through a green run. An always-empty column is a broken mapping until
    # someone proves otherwise, so say so loudly.
    if out:
        dead = [c for c in OUT_COLUMNS
                if c != "notifiable" and not any(r.get(c) for r in out)]
        if dead:
            log(f"  WARNING these columns are empty for all {len(out)} rows: "
                f"{dead}. That usually means the CSV header changed and the "
                f"mapping no longer matches -- check against: "
                f"{sorted(k for k in out[0] if k)[:4]}...")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", type=pathlib.Path, default=DEFAULT_IN)
    ap.add_argument("--out", dest="dst", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.src.exists():
        log(f"not found: {args.src}\n"
            f"This is Monday's optional Q4 work. Copy the TGA shortage CSV export to\n"
            f"that path first. Nothing else depends on it.")
        return 1

    rows = parse(args.src.read_text(encoding="utf-8-sig"))
    notifiable = [r for r in rows if r["notifiable"]]
    payload = {"records": [
        {c: ("|".join(r[c]) if isinstance(r[c], list) else
             ("true" if r[c] is True else "false" if r[c] is False else "" if r[c] is None else str(r[c])))
         for c in OUT_COLUMNS}
        for r in rows
    ]}
    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    log(f"parsed {len(rows)} shortage rows -> {args.dst}")
    log(f"  notifiable (Current or Anticipated): {len(notifiable)}")
    log(f"  not notifiable (Resolved or Discontinued): {len(rows) - len(notifiable)}")
    log("\nNot registered. Q4 is Monday and optional; queries.q_shortages still raises.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
