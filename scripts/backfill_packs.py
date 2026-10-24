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

Values are written **per strength**: a ";"-separated list aligned with the
row's `strengths`, because one value per product gave every prednisolone
strength the 200-tablet pack that is right only for 5 mg.

Usage:
    python3 scripts/backfill_packs.py            # report only
    python3 scripts/backfill_packs.py --write
    python3 scripts/backfill_packs.py --write --hand-set original.csv
        # recompute every row except those that had an override in
        # original.csv -- for redoing an earlier backfill
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
    ap.add_argument("--hand-set", type=pathlib.Path,
                    help="a medicines.csv from before any backfill; rows with an override "
                         "there are kept, every other row is recomputed")
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
    hand_set: set[tuple[str, str]] | None = None
    if args.hand_set:
        hand_set = {(r["generic"], r["strengths"]) for r in csv.DictReader(args.hand_set.open())
                    if r["pack_qty_override"]}
    filled = kept = unmatched = 0
    disagreed: list[str] = []

    for row in rows:
        is_hand_set = ((row["generic"], row["strengths"]) in hand_set) if hand_set is not None \
            else bool(row["pack_qty_override"])
        if is_hand_set:
            kept += 1
            continue
        qtys: list[str] = []
        reps: list[str] = []
        for strength in row["strengths"].split(";"):
            found = [packs[(row["generic"], brand, strength)]
                     for brand in row["brands"].split(";")
                     if (row["generic"], brand, strength) in packs]
            if not found:
                qtys.append("")
                reps.append("")
                continue
            counted = collections.Counter(found)
            # Most frequent wins; ties go to the LARGER pack. A tie broken by
            # insertion order would be arbitrary, and the small side is usually
            # an artefact rather than a real pack: PBS lists the quantity unit as
            # a pack for some items (escitalopram drops come back as 1) and
            # injections come back as single ampoules (furosemide as 2 and 5).
            qty, repeats = max(counted, key=lambda v: (counted[v], int(v[0])))
            if len(counted) > 1:
                disagreed.append(f"  {row['generic']:22} {strength:10} chose {qty}/{repeats} "
                                 f"from {dict(counted)}")
            qtys.append(qty)
            reps.append(repeats)
        if not any(qtys):
            unmatched += 1
            continue
        # One value when every strength agrees, so the common case stays readable.
        row["pack_qty_override"] = qtys[0] if len(set(qtys)) == 1 else ";".join(qtys)
        row["repeats_override"] = reps[0] if len(set(reps)) == 1 else ";".join(reps)
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
