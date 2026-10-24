#!/usr/bin/env python3
"""Write the real PBS pack quantity and repeats into `medicines.csv`.

Why this exists, and why it is a one-off rather than a build step:

`generate_synthetic.py` reads each item's real PBS maximum quantity so that
dispensing intervals are believable. It got them from `data/reference/
lexicon.json`, which is **gitignored**. That made the generator's output depend
on a file a fresh clone does not have: CI regenerated the silos with guessed
pack sizes, overwrote the committed fixtures, and then tested data nobody had
committed. The symptom was a free-text resolution rate that fell from 0.846 to
0.820 only on CI.

So the numbers belong in a **committed** source. `medicines.csv` already had
`pack_qty_override` and `repeats_override` columns for exactly this, and they
were empty for all but 21 hand-set rows. This fills the rest from the real
schedule, once, and from then on the generator needs nothing gitignored.

Hand-set overrides are never touched -- a human chose those deliberately.

A row covers several brands and strengths, which can differ in pack size, so
the modal value across its lexicon entries is used and any row whose entries
disagree is reported rather than silently flattened.

Usage:
    python3 scripts/backfill_packs.py            # report only
    python3 scripts/backfill_packs.py --write
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import sys

SRC = pathlib.Path("data/reference_src/medicines.csv")
LEXICON = pathlib.Path("data/reference/lexicon.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write the file (default: report)")
    args = ap.parse_args()

    if not LEXICON.exists():
        print(f"{LEXICON} not found -- run `make lexicon` first. Nothing written.")
        return 1

    packs: dict[tuple[str, str, str], tuple[str, str]] = {}
    for entry in json.loads(LEXICON.read_text())["records"]:
        if entry.get("pack_qty"):
            packs[(entry["generic"], entry["brand"], entry["strength"])] = (
                entry["pack_qty"], entry.get("repeats") or "0")

    rows = list(csv.DictReader(SRC.open()))
    fields = list(rows[0])
    filled = kept = unmatched = 0
    disagreed: list[str] = []

    for row in rows:
        if row["pack_qty_override"]:
            kept += 1
            continue
        found = [packs[(row["generic"], brand, strength)]
                 for brand in row["brands"].split(";")
                 for strength in row["strengths"].split(";")
                 if (row["generic"], brand, strength) in packs]
        if not found:
            unmatched += 1
            continue
        counted = collections.Counter(found)
        # Most frequent wins; ties go to the LARGER pack. A tie broken by
        # insertion order would be arbitrary, and the small side of these ties
        # is usually an artefact rather than a real pack: PBS lists the
        # quantity unit as a pack for some items (escitalopram drops come back
        # as 1) and injections come back as single ampoules (furosemide as 2
        # and 5). The oral maintenance pack is the one a reconciliation sees.
        qty, repeats = max(counted, key=lambda v: (counted[v], int(v[0])))
        if len(counted) > 1:
            disagreed.append(f"  {row['generic']:22} chose {qty}/{repeats} from {dict(counted)}")
        row["pack_qty_override"], row["repeats_override"] = qty, repeats
        filled += 1

    print(f"{filled} row(s) filled, {kept} hand-set kept, {unmatched} with no PBS entry")
    if disagreed:
        print(f"{len(disagreed)} row(s) whose brands/strengths disagree; modal value used:")
        print("\n".join(disagreed))

    if not args.write:
        print("\nreport only -- re-run with --write")
        return 0

    with SRC.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {SRC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
