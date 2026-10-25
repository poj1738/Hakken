#!/usr/bin/env python3
"""Build the medicines lexicon served at `/ref/lexicon`.

Inputs, all committed, all our own work:

  data/reference_src/medicines.csv     ~104 products transcribed from DATA_SPEC
                                       4.2 (bundles) and 4.3 (combination traps)
  data/reference_src/apinchs_atc.csv   DATA_SPEC 10.1, 40 rows verbatim
  data/reference_src/nicknames.csv     DATA_SPEC 10.2, hand-selected pairs

Optional inputs, fetched and **gitignored**, used to make the codes real:

  data/reference/raw/pbs_items_<sched>.csv                  PBS public API v3
  data/reference/raw/pbs_item-atc-relationships_<sched>.csv  "
  data/reference/raw/pbs_amt-items_<sched>.csv               "
  data/reference/raw/pbs_item_report_2016.csv                data.gov.au, CC BY

**The clinical content is ours and the codes are real where we can match them.**
Where a product has no PBS match, the code columns fall back to clearly synthetic
values (`SYN-PBS-0001`, `SYN-AMT-MP-0001`) so the code-matching path in
`normalise_med` is still exercised end to end -- a run must never silently lose
its `code` resolution tier just because one product failed to match.

**ATC codes come from DATA_SPEC, never from the PBS join and never from general
knowledge.** The PBS `atc_priority_pct` value is read purely as a *cross-check*:
disagreements are reported for a human to resolve, never silently applied. The
spec is the clinical contract; the API is evidence about it.

Outputs (gitignored, regenerate with `make data`):

  data/reference/lexicon.json    {"records": [...]}  -> served at /ref/lexicon
  data/reference/apinchs.json    {"records": [...]}  -> served at /ref/apinchs
  data/reference/nicknames.json  {"records": [...]}  -> served at /ref/nicknames
  tests/fixtures/medtrace/Q_REF__*.json   Zetaris envelopes for SAMPLE_MODE
  tests/fixtures/reference/lexicon_sample.csv   <=200 attributed rows (committed)
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import re
import sys

SRC = pathlib.Path("data/reference_src")
RAW = pathlib.Path("data/reference/raw")
OUT = pathlib.Path("data/reference")
FIXTURES = pathlib.Path("tests/fixtures/medtrace")
SAMPLE = pathlib.Path("tests/fixtures/reference")

#: Exactly the columns `queries.q_reference("lexicon")` selects, in order.
LEXICON_COLUMNS = (
    "pbs_code", "brand", "generic", "amt_mp", "amt_mpp", "amt_tpp", "atc_primary",
    "strength", "form", "release", "pack_qty", "repeats", "is_combination",
    "ingredients", "dos_weight",
)
APINCHS_COLUMNS = ("atc_prefix", "apinchs_class", "label")
NICKNAME_COLUMNS = ("canonical", "variant", "sex")


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def norm(text: str) -> str:
    """Casefold and collapse whitespace, for name matching only."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def strength_number(strength: str) -> str:
    """`"400 microgram"` -> `"400"`. Used to match our strength into PBS `li_form`."""
    m = re.match(r"\s*([\d.]+)", strength or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# Optional PBS snapshot
# --------------------------------------------------------------------------- #


def find_snapshot(table: str) -> pathlib.Path | None:
    hits = sorted(RAW.glob(f"pbs_{table}_*.csv"))
    hits = [h for h in hits if not re.search(r"_p\d+\.csv$", h.name)]
    return hits[-1] if hits else None


def load_pbs() -> dict[str, object]:
    """Load whatever of the PBS snapshot exists. Missing files are not an error."""
    items_path = find_snapshot("items")
    atc_path = find_snapshot("item-atc-relationships")
    amt_path = find_snapshot("amt-items")

    items: list[dict[str, str]] = read_csv(items_path) if items_path else []
    atc_rows: list[dict[str, str]] = read_csv(atc_path) if atc_path else []
    amt_rows: list[dict[str, str]] = read_csv(amt_path) if amt_path else []

    # generic (drug_name) -> its items
    by_generic: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for row in items:
        by_generic[norm(row.get("drug_name", ""))].append(row)

    # pbs_code -> highest-priority ATC (PLAN 3's "highest ATC_PRIORITY_PCT")
    best_atc: dict[str, tuple[int, str]] = {}
    for row in atc_rows:
        code, atc = row.get("pbs_code", ""), row.get("atc_code", "")
        try:
            pct = int(float(row.get("atc_priority_pct") or 0))
        except ValueError:
            pct = 0
        if code and atc and pct >= best_atc.get(code, (-1, ""))[0]:
            best_atc[code] = (pct, atc)

    # li_item_id -> {concept_type_code: amt_code}
    amt: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for row in amt_rows:
        li, kind, code = row.get("li_item_id", ""), row.get("concept_type_code", ""), row.get("amt_code", "")
        if li and kind and code:
            amt[li].setdefault(kind.upper(), code)

    # pbs_code -> annual services, from the data.gov.au Item Report (CC BY)
    volumes: dict[str, int] = collections.Counter()
    report = RAW / "pbs_item_report_2016.csv"
    if report.exists():
        with report.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                code = (row.get("Item_number") or "").strip()
                try:
                    volumes[code] += int(row.get("Services") or 0)
                except ValueError:
                    continue

    log(f"PBS snapshot: items={len(items)} atc_rel={len(atc_rows)} amt={len(amt_rows)} "
        f"item_report_codes={len(volumes)}")
    if not items:
        log("  (no PBS items snapshot found -- every code will be synthetic. "
            "Run scripts/fetch_reference.py first for real codes.)")
    return {"by_generic": by_generic, "best_atc": best_atc, "amt": amt, "volumes": volumes}


def match_item(pbs: dict[str, object], generic: str, brand: str, strength: str,
               ingredients: list[str]) -> dict[str, str] | None:
    """Best PBS item for one of our products, or None.

    **A wrong real code is far worse than a synthetic one.** A synthetic code is
    visibly ours and resolves to nothing; a real code belonging to a *different
    medicine* is confidently wrong, and the whole value of the `code` resolution
    tier in `normalise_med` is that it is a fact rather than a guess.

    An earlier version fell back to the first ingredient when a combination's
    name did not match, which silently gave **every one of our 15 combination
    products the PBS code of one of its components**: Caduet got amlodipine's,
    Targin got OxyContin's, Panadeine Forte got plain paracetamol's. It also
    manufactured 33 of the 35 "ATC disagreements" we then spent time reviewing,
    because the ATC came back correct *for the wrong item*.

    So matching is now by **molecule set**, never by one component:

      * single-ingredient -- `drug_name` must equal the generic, then prefer a
        brand match, then a strength appearing in `li_form`;
      * combination -- the PBS `drug_name` must mention **every** ingredient, or
        the PBS `brand_name` must equal ours. PBS writes these inconsistently
        ("Amlodipine with atorvastatin", "amlodipine + atorvastatin"), so the
        test is containment of all parts rather than an exact string.

    Anything else returns `None` and gets a synthetic code.
    """
    by_generic: dict[str, list[dict[str, str]]] = pbs["by_generic"]  # type: ignore[assignment]
    want_brand = norm(brand)
    num = strength_number(strength)
    parts = [norm(i) for i in ingredients if i.strip()]
    is_combination = len(parts) > 1

    if is_combination:
        # Scan every item whose name mentions all the ingredients, or whose
        # brand is ours. Never fall back to a single component.
        candidates = [
            row for rows in by_generic.values() for row in rows
            if (want_brand and norm(row.get("brand_name", "")) == want_brand)
            or all(part in norm(row.get("drug_name", "")) for part in parts)
        ]
    else:
        candidates = list(by_generic.get(norm(generic), []))

    if not candidates:
        return None

    def score(row: dict[str, str]) -> tuple[int, int]:
        return (
            1 if want_brand and norm(row.get("brand_name", "")) == want_brand else 0,
            1 if num and num in norm(row.get("li_form", "")) else 0,
        )

    return max(candidates, key=lambda row: (sum(score(row)), score(row)[1]))


# --------------------------------------------------------------------------- #
# Derived values
# --------------------------------------------------------------------------- #


def pack_and_repeats(row: dict[str, str], item: dict[str, str] | None) -> tuple[str, str]:
    """Real PBS pack size and repeats where matched, else DATA_SPEC 9.2's fallback."""
    if item:
        qty = (item.get("maximum_quantity_units") or item.get("pack_size") or "").strip()
        rpt = (item.get("number_of_repeats") or "").strip()
        if qty and rpt:
            return qty, rpt
    if row["pack_qty_override"]:
        qty = row["pack_qty_override"]
    else:
        regimen = row["regimen"].lower()
        if "weekly" in regimen or "monthly" in regimen or "yearly" in regimen:
            qty = "4"
        elif any(f in regimen for f in (" bd", " tds", " qid")) or regimen.endswith(("bd", "tds", "qid")):
            qty = "60"
        else:
            qty = "30"
    rpt = row["repeats_override"] or "5"
    return qty, rpt


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def build() -> int:
    medicines = read_csv(SRC / "medicines.csv")
    apinchs_src = read_csv(SRC / "apinchs_atc.csv")
    nicknames = read_csv(SRC / "nicknames.csv")
    log(f"source: {len(medicines)} products, {len(apinchs_src)} APINCHS rows, "
        f"{len(nicknames)} nickname pairs")
    pbs = load_pbs()

    # One synthetic MP per molecule, so EMR's amt_mp_code is stable per generic.
    generics = sorted({r["generic"] for r in medicines})
    syn_mp = {g: f"SYN-AMT-MP-{i + 1:04d}" for i, g in enumerate(generics)}

    records: list[dict[str, str]] = []
    atc_conflicts: list[tuple[str, str, str, str]] = []
    unmatched: list[str] = []
    real_codes = 0

    for row in medicines:
        ingredients = [i for i in row["ingredients"].split(";") if i]
        brands = [b for b in row["brands"].split(";") if b] or [""]
        strengths = [s for s in row["strengths"].split(";") if s] or [""]
        for brand in brands:
            for strength in strengths:
                item = match_item(pbs, row["generic"], brand, strength, ingredients)
                n = len(records) + 1
                if item:
                    real_codes += 1
                    pbs_code = item.get("pbs_code", "") or f"SYN-PBS-{n:04d}"
                    li = item.get("li_item_id", "")
                    amt_for_item: dict[str, str] = pbs["amt"].get(li, {})  # type: ignore[union-attr]
                    amt_mp = amt_for_item.get("MP") or syn_mp[row["generic"]]
                    amt_mpp = amt_for_item.get("MPP") or f"SYN-AMT-MPP-{n:04d}"
                    amt_tpp = amt_for_item.get("TPP") or f"SYN-AMT-TPP-{n:04d}"
                    # Cross-check only. DATA_SPEC's ATC is authoritative.
                    pbs_atc = pbs["best_atc"].get(pbs_code, (0, ""))[1]  # type: ignore[union-attr]
                    if pbs_atc and row["atc"] and pbs_atc != row["atc"]:
                        atc_conflicts.append((row["generic"], brand, row["atc"], pbs_atc))
                else:
                    unmatched.append(f'{row["generic"]} / {brand or "-"} / {strength or "-"}')
                    pbs_code = f"SYN-PBS-{n:04d}"
                    amt_mp = syn_mp[row["generic"]]
                    amt_mpp = f"SYN-AMT-MPP-{n:04d}"
                    amt_tpp = f"SYN-AMT-TPP-{n:04d}"

                pack_qty, repeats = pack_and_repeats(row, item)
                records.append({
                    "pbs_code": pbs_code,
                    "brand": brand,
                    "generic": row["generic"],
                    "amt_mp": amt_mp,
                    "amt_mpp": amt_mpp,
                    "amt_tpp": amt_tpp,
                    "atc_primary": row["atc"],
                    "strength": strength,
                    "form": row["form"],
                    "release": row["release"],
                    "pack_qty": pack_qty,
                    "repeats": repeats,
                    "is_combination": "true" if len(ingredients) > 1 else "false",
                    "ingredients": row["ingredients"],
                    "dos_weight": "",
                })

    # dos_weight: real 2016 service volumes where the PBS code matched, as a
    # share of the total across the lexicon. DATA_SPEC's within-bundle `share`
    # drives sampling and stays generator-side; this is reference information.
    volumes: dict[str, int] = pbs["volumes"]  # type: ignore[assignment]
    matched = {r["pbs_code"]: volumes.get(r["pbs_code"], 0) for r in records}
    total = sum(matched.values())
    for rec in records:
        v = matched.get(rec["pbs_code"], 0)
        rec["dos_weight"] = f"{v / total:.6f}" if total and v else "0.000000"
    with_volume = sum(1 for r in records if r["dos_weight"] != "0.000000")

    # APINCHS: expand the two multi-prefix rows, longest prefix first so the most
    # specific rule wins (A10AB must beat A10).
    apinchs: list[dict[str, str]] = []
    for row in apinchs_src:
        for prefix in (p.strip() for p in row["atc_prefixes"].split(";") if p.strip()):
            apinchs.append({"atc_prefix": prefix, "apinchs_class": row["apinchs_class"],
                            "label": row["label"]})
    apinchs.sort(key=lambda r: (-len(r["atc_prefix"]), r["atc_prefix"]))

    nick = [{"canonical": r["canonical"], "variant": r["variant"],
         "sex": r.get("sex", "")} for r in nicknames]

    # -- write ---------------------------------------------------------------
    # A build with no PBS snapshot has only synthetic codes. It must not replace
    # committed fixtures that carry real ones: on a fresh clone that turned the
    # README's own `make lexicon && make synth` into 21 rewritten fixtures and two
    # failing tests (judge-clone audit, 25 Oct). data/reference/ is still written.
    committed = FIXTURES / "Q_REF__lexicon.json"
    keep_committed = False
    if real_codes == 0 and committed.exists():
        env = json.loads(committed.read_text())
        i = env["headers"].index("pbs_code")
        keep_committed = any(r[i] and not r[i].startswith("SYN") for r in env["data"])
    OUT.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for name, rows, cols in (("lexicon", records, LEXICON_COLUMNS),
                             ("apinchs", apinchs, APINCHS_COLUMNS),
                             ("nicknames", nick, NICKNAME_COLUMNS)):
        payload = {"records": [{c: str(r.get(c, "")) for c in cols} for r in rows]}
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        # Zetaris envelope, every value a string, for SAMPLE_MODE replay.
        envelope = {
            "headers": list(cols),
            "data": [[str(r.get(c, "")) for c in cols] for r in rows],
            "total": len(rows),
        }
        if name == "lexicon" and keep_committed:
            log(f"  wrote {name}: {len(rows)} rows (committed fixture left alone)")
            continue
        (FIXTURES / f"Q_REF__{name}.json").write_text(json.dumps(envelope, indent=1), encoding="utf-8")
        log(f"  wrote {name}: {len(rows)} rows")

    # Committed attributed sample, <=200 rows (PLAN 4.2).
    if not keep_committed:
        with (SAMPLE / "lexicon_sample.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(LEXICON_COLUMNS))
            w.writeheader()
            for rec in records[:200]:
                w.writerow(rec)

    # -- report --------------------------------------------------------------
    log(f"\nlexicon: {len(records)} rows from {len(medicines)} products")
    log(f"  real PBS codes:      {real_codes}/{len(records)}")
    log(f"  synthetic codes:     {len(records) - real_codes}/{len(records)}")
    log(f"  with real dos_weight: {with_volume}/{len(records)}")
    if atc_conflicts:
        # Written to a file as well as logged, because APINCHS classification is
        # by ATC prefix: a disagreement can move a medicine in or out of a
        # high-risk class, and that is a clinical decision, not a build detail.
        apinchs_prefixes = [r["atc_prefix"] for r in apinchs]

        def apinchs_for(code: str) -> str:
            for prefix in apinchs_prefixes:  # already longest-first
                if code.startswith(prefix):
                    return next(r["apinchs_class"] for r in apinchs if r["atc_prefix"] == prefix)
            return ""

        review = OUT / "atc_crosscheck.csv"
        with review.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["generic", "brand", "spec_atc", "spec_apinchs",
                        "pbs_atc", "pbs_apinchs", "changes_high_risk"])
            for generic, brand, spec_atc, pbs_atc in atc_conflicts:
                a, b = apinchs_for(spec_atc), apinchs_for(pbs_atc)
                w.writerow([generic, brand, spec_atc, a, pbs_atc, b, "YES" if a != b else ""])
        moved = [(g, b, s, p2) for g, b, s, p2 in atc_conflicts
                 if apinchs_for(s) != apinchs_for(p2)]
        log(f"\n  ATC cross-check: {len(atc_conflicts)} disagreement(s) between DATA_SPEC "
            f"and PBS -> {review}")
        if moved:
            log(f"  *** {len(moved)} of them CHANGE the APINCHS class, which changes whether a")
            log(f"      medicine is high-risk. DATA_SPEC wins, but these need a human:")
            for generic, brand, spec_atc, pbs_atc in moved:
                log(f"        {generic:34} spec={spec_atc:9} ({apinchs_for(spec_atc) or '-'})"
                    f"  pbs={pbs_atc:9} ({apinchs_for(pbs_atc) or '-'})")
        log("  full list:")
        for generic, brand, spec_atc, pbs_atc in atc_conflicts[:25]:
            log(f"    {generic:44} {brand:22} spec={spec_atc:10} pbs={pbs_atc}")
        if len(atc_conflicts) > 25:
            log(f"    ... and {len(atc_conflicts) - 25} more")
    if unmatched:
        log(f"\n  no PBS match for {len(unmatched)} row(s) (synthetic codes used):")
        for u in unmatched[:20]:
            log(f"    {u}")
        if len(unmatched) > 20:
            log(f"    ... and {len(unmatched) - 20} more")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    if not (SRC / "medicines.csv").exists():
        sys.exit(f"missing {SRC / 'medicines.csv'}")
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
