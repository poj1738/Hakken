#!/usr/bin/env python3
"""Score the MedTrace clinical pipeline against the planted ground truth.

Implements `docs/DATA_SPEC.md` 11.2. For every patient it runs the **real** chain
the orchestrator runs -- Q1 candidates, `link_identity`, Q2 for the auto-merge
set only, `normalise_med`, `coverage`, `evidence_state`, `fuse`,
`detect_discrepancies`, `prioritise` -- and scores what comes out.

Identity is not short-circuited. The committed Q2 fixtures read each patient's
*true* records, which scores detection as if linkage were perfect; this reads
whatever `link_identity` actually linked, so a missed link costs recall and a
false merge costs precision, the way it would for a pharmacist.

**Where the rows come from.** By default, offline: the silos are harmonised with
the generator's own `harmonise()` and Q1 is selected with its `q1_matches()` --
the single definition the committed fixtures were built from, which were diffed
byte-for-byte against the live Zetaris views (`register_sources.py
--diff-fixtures`). The lexicon is the recorded Q_REF envelopes, the same one
`SAMPLE_MODE` replays. This is a scorer, not an agent: it reads the files the
views are built over so that it can run in CI and on a laptop with no services.

Matching (DATA_SPEC 11.2): a finding is a true positive when it has the same
patient, type and generic as a planted one, with overlapping row ids, matched
one-to-one greedily by largest overlap. Per-type precision and recall carry
Wilson 95% intervals, because at this population size a point estimate alone
overstates what we know.

Usage:
    python3 scripts/eval.py                    # tune split, summary
    python3 scripts/eval.py --split heldout    # the numbers we report
    python3 scripts/eval.py --split all --misses
    python3 scripts/eval.py --patient P0002    # one patient's grid and findings
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import math
import pathlib
import sys
from dataclasses import dataclass, field
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.domain.packs.medtrace import coverage as cov_mod
from app.domain.packs.medtrace.detect import detect_discrepancies
from app.domain.packs.medtrace.fuse import fuse
from app.domain.packs.medtrace.triage import MUST_REVIEW_FLOOR, prioritise
from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql, rows_from_sql
from app.domain.packs.medtrace.identity import link_identity
from app.domain.packs.medtrace.normalise import normalise_med
from app.domain.packs.medtrace.queries import HARMONISED_COLUMNS, IDENTITY_COLUMNS
from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.domain.packs.medtrace.types import (
    SOURCES,
    Coverage,
    EvidenceState,
    FusedMed,
    IdentityLink,
    Lexicon,
    MedStatement,
    SourceRow,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "medtrace"
SYNTHETIC = ROOT / "data" / "synthetic"

_spec = importlib.util.spec_from_file_location("generate_synthetic", ROOT / "scripts" / "generate_synthetic.py")
assert _spec and _spec.loader
_gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_synthetic"] = _gen
_spec.loader.exec_module(_gen)


def log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# The world: lexicon, harmonised rows, ground truth
# --------------------------------------------------------------------------- #


def load_lexicon() -> Lexicon:
    """From the recorded Q_REF envelopes -- what SAMPLE_MODE replays."""
    def load(name: str) -> list[dict[str, str]]:
        return dicts_from_sql(json.loads((FIXTURES / f"Q_REF__{name}.json").read_text()))
    return build_lexicon(load("lexicon"), load("apinchs"), load("nicknames"))


@dataclass
class World:
    lex: Lexicon
    truth: dict
    as_of: date
    harmonised: list[dict[str, str | None]]
    rows_by_key: dict[str, list[SourceRow]]


def load_world() -> World:
    silos = SYNTHETIC / "silos"
    missing = [s for s in SOURCES if not (silos / f"{s}.json").exists()]
    if missing:
        sys.exit(f"data/synthetic/silos/ is missing {missing}. Run `make synth` first "
                 f"(the silos are gitignored, and nothing builds them for you).")
    harmonised: list[dict[str, str | None]] = []
    for source in SOURCES:
        records = json.loads((silos / f"{source}.json").read_text())["records"]
        harmonised.extend(_gen.harmonise(source, r) for r in records)
    rows = rows_from_sql(_gen.envelope(HARMONISED_COLUMNS, harmonised))
    rows_by_key: dict[str, list[SourceRow]] = collections.defaultdict(list)
    for row in rows:
        rows_by_key[row.record_key].append(row)
    truth = json.loads((SYNTHETIC / "ground_truth.json").read_text())
    return World(lex=load_lexicon(), truth=truth, as_of=date.fromisoformat(truth["as_of"]),
                 harmonised=harmonised, rows_by_key=dict(rows_by_key))


# --------------------------------------------------------------------------- #
# The pipeline, as the orchestrator runs it
# --------------------------------------------------------------------------- #


@dataclass
class Reconciliation:
    patient_key: str
    links: list[IdentityLink]
    linked_keys: list[str]
    cov: dict[str, Coverage]
    stmts: list[MedStatement]
    evidence: dict[str, dict[str, EvidenceState]]
    fused: list[FusedMed]
    findings: list = field(default_factory=list)
    needed_review: int = 0


def reconcile(world: World, patient: dict, review: str = "oracle") -> Reconciliation | None:
    """One patient through the real chain. `None` if the anchor cannot be found.

    `review` is what happens at the human gate. `"none"`: nobody confirms a
    near-miss, so review-band records are never read -- what the system does on
    its own. `"oracle"`: a pharmacist confirms exactly the review-band links
    that are truly this patient and rejects the rest -- the designed workflow
    (`POST /run/{id}/identity`), simulated with the ground truth. The scorecard
    reports which mode it ran in, and how many links needed a human.
    """
    mrn = patient["true_links"]["emr"][0]
    anchor_dict = next((h for h in world.harmonised
                        if h["source"] == "emr" and h["source_patient_id"] == mrn), None)
    if anchor_dict is None:
        return None
    # Q1: the identity candidates the real template would return.
    q1 = [h for h in world.harmonised if _gen.q1_matches(anchor_dict, h)]
    candidates = rows_from_sql(_gen.envelope(IDENTITY_COLUMNS, q1))
    anchor = rows_from_sql(_gen.envelope(IDENTITY_COLUMNS, [anchor_dict]))[0]
    links = link_identity(anchor, [c for c in candidates if c.record_key != anchor.record_key],
                          world.lex)
    needed_review = [l for l in links if l.band == "review"]
    if review == "oracle" and needed_review:
        truly_mine = {f"{src}:{rid}" for src, ids in patient["true_links"].items() for rid in ids}
        links = [l.model_copy(update={"band": "auto-merge" if l.candidate_id in truly_mine else "new"})
                 if l.band == "review" else l for l in links]

    # Q2: the anchor and the auto-merge set only. A review-band link waits for a
    # human (POST /run/{id}/identity) before its rows are read.
    linked = [anchor.record_key] + [l.candidate_id for l in links if l.band == "auto-merge"]
    linked = list(dict.fromkeys(linked))
    q2 = [row for key in linked for row in world.rows_by_key.get(key, [])]

    cov = cov_mod.coverage(links, q2)
    stmts = [normalise_med(row, world.lex) for row in q2 if row.has_med]
    generics = sorted({s.generic for s in stmts if s.generic})
    evidence = {g: {src: cov_mod.evidence_state(g, src, cov[src], stmts) for src in SOURCES}
                for g in generics}

    fused = fuse(stmts, evidence, dict(SOURCE_TRUST_PRIORS), world.as_of)
    findings = prioritise(detect_discrepancies(fused, stmts, cov, world.as_of, world.lex), {})
    return Reconciliation(patient_key=patient["patient_key"], links=links, linked_keys=linked,
                          cov=cov, stmts=stmts, evidence=evidence, fused=fused,
                          findings=findings, needed_review=len(needed_review))


# --------------------------------------------------------------------------- #
# Scoring (DATA_SPEC 11.2)
# --------------------------------------------------------------------------- #


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Honest at small n, where a point estimate is not."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _norm(generic: str) -> str:
    return " ".join((generic or "").split()).casefold()


def match(predicted: list, planted: list[dict]) -> tuple[list, list, list]:
    """One-to-one greedy matching by largest row overlap, within type and generic.

    Returns (true positives as (pred, planted) pairs, false positives, misses).
    """
    pairs = []
    for i, pred in enumerate(predicted):
        for j, plant in enumerate(planted):
            if pred.type.value != plant["type"] or _norm(pred.generic) != _norm(plant["generic"]):
                continue
            overlap = len(set(pred.row_ids) & set(plant["row_ids"]))
            if overlap:
                pairs.append((overlap, i, j))
    used_p, used_t, tps = set(), set(), []
    for _overlap, i, j in sorted(pairs, key=lambda t: (-t[0], t[1], t[2])):
        if i in used_p or j in used_t:
            continue
        used_p.add(i)
        used_t.add(j)
        tps.append((predicted[i], planted[j]))
    fps = [p for i, p in enumerate(predicted) if i not in used_p]
    misses = [t for j, t in enumerate(planted) if j not in used_t]
    return tps, fps, misses


@dataclass
class Score:
    tp: collections.Counter = field(default_factory=collections.Counter)
    fp: collections.Counter = field(default_factory=collections.Counter)
    fn: collections.Counter = field(default_factory=collections.Counter)
    fp_items: list = field(default_factory=list)
    fn_items: list = field(default_factory=list)
    high_risk_planted: int = 0
    high_risk_found: int = 0
    # Core ACSQHC APINCHS and our facility extensions, kept apart (DECISIONS 24 Oct):
    # pooled, a weak extension row moves a number that reads as ACSQHC compliance.
    high_risk_by_list: collections.Counter = field(default_factory=collections.Counter)
    high_risk_found_by_list: collections.Counter = field(default_factory=collections.Counter)
    patients: int = 0
    findings: int = 0
    # Linkage: every auto-merged record, and those that are not this patient's.
    auto_merged: int = 0
    false_merges: int = 0
    needed_review: int = 0


def score(world: World, keys: list[str], review: str) -> Score:
    result = Score()
    by_key = {p["patient_key"]: p for p in world.truth["patients"]}
    for key in keys:
        patient = by_key[key]
        rec = reconcile(world, patient, review)
        if rec is None:
            continue
        result.patients += 1
        result.findings += len(rec.findings)
        result.needed_review += rec.needed_review
        truly_mine = {f"{src}:{rid}" for src, ids in patient["true_links"].items() for rid in ids}
        merged = {l.candidate_id for l in rec.links if l.band == "auto-merge"}
        result.auto_merged += len(merged)
        result.false_merges += len(merged - truly_mine)
        tps, fps, misses = match(rec.findings, patient["planted"])
        for pred, plant in tps:
            result.tp[plant["type"]] += 1
            if plant.get("high_risk_class"):
                result.high_risk_found += 1
                result.high_risk_found_by_list[_risk_list(plant)] += 1
        for pred in fps:
            result.fp[pred.type.value] += 1
            result.fp_items.append((key, pred))
        for plant in misses:
            result.fn[plant["type"]] += 1
            result.fn_items.append((key, plant))
        result.high_risk_planted += sum(1 for t in patient["planted"] if t.get("high_risk_class"))
        result.high_risk_by_list.update(_risk_list(t) for t in patient["planted"]
                                        if t.get("high_risk_class"))
    return result


def _risk_list(plant: dict) -> str:
    return "extended" if plant["high_risk_class"] == "ext" else "core"


def as_json(result: Score, split: str, review: str) -> dict:
    """The scorecard as data, for `scripts/scorecard_page.py` and the pitch.

    Every number here comes from this run; nothing is typed in by hand.
    """
    def rate(k: int, n: int) -> dict:
        lo, hi = wilson(k, n)
        return {"k": k, "n": n, "value": k / n if n else None, "lo": lo, "hi": hi}

    tp, fp, fn = (sum(c.values()) for c in (result.tp, result.fp, result.fn))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "split": split, "review": review, "patients": result.patients,
        "links_needing_review": result.needed_review,
        "overall": {"tp": tp, "fp": fp, "fn": fn, "precision": rate(tp, tp + fp),
                    "recall": rate(tp, tp + fn), "f1": 2 * p * r / (p + r) if p + r else 0.0},
        "by_type": {kind: {"tp": result.tp[kind], "fp": result.fp[kind], "fn": result.fn[kind],
                           "precision": rate(result.tp[kind], result.tp[kind] + result.fp[kind]),
                           "recall": rate(result.tp[kind], result.tp[kind] + result.fn[kind])}
                    for kind in sorted(set(result.tp) | set(result.fp) | set(result.fn))},
        "high_risk": {name: rate(result.high_risk_found_by_list[name], result.high_risk_by_list[name])
                      for name in ("core", "extended")},
        "linkage": {"auto_merged": result.auto_merged, "false_merges": result.false_merges},
        "findings_per_patient": result.findings / max(result.patients, 1),
    }


def report(result: Score, split: str, review: str, misses: bool) -> None:
    log(f"\nMedTrace eval -- split={split}, {result.patients} patients, review={review} "
        f"({result.needed_review} link(s) needed a human)")
    log(f"{'type':30} {'TP':>3} {'FP':>3} {'FN':>3}   {'precision':>20}   {'recall':>20}")
    types = sorted(set(result.tp) | set(result.fp) | set(result.fn))
    for kind in types:
        tp, fp, fn = result.tp[kind], result.fp[kind], result.fn[kind]
        p_lo, p_hi = wilson(tp, tp + fp)
        r_lo, r_hi = wilson(tp, tp + fn)
        prec = f"{tp / (tp + fp):.2f} [{p_lo:.2f},{p_hi:.2f}]" if tp + fp else "   --"
        rec = f"{tp / (tp + fn):.2f} [{r_lo:.2f},{r_hi:.2f}]" if tp + fn else "   -- (not planted)"
        log(f"{kind:30} {tp:3} {fp:3} {fn:3}   {prec:>20}   {rec:>20}")
    tp, fp, fn = sum(result.tp.values()), sum(result.fp.values()), sum(result.fn.values())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    log(f"{'ALL':30} {tp:3} {fp:3} {fn:3}   precision {p:.2f}  recall {r:.2f}  F1 {f1:.2f}")
    if result.high_risk_planted:
        log(f"APINCHS / high-risk recall: {result.high_risk_found}/{result.high_risk_planted}")
        for name in ("core", "extended"):
            found, planted = result.high_risk_found_by_list[name], result.high_risk_by_list[name]
            if planted:
                lo, hi = wilson(found, planted)
                log(f"  {name:8} {found}/{planted}  [{lo:.2f},{hi:.2f}]")
    log(f"findings per patient: {result.findings / max(result.patients, 1):.2f} (target <= 4, "
        f"before notices)")
    log(f"linkage: {result.auto_merged} records auto-merged, {result.false_merges} false merge(s)")
    if misses:
        log("\nMISSED")
        for key, plant in result.fn_items:
            log(f"  {key} {plant['type']:20} {plant['generic']:24} {plant['row_ids']}")
        log("\nFALSE POSITIVES")
        for key, pred in result.fp_items:
            log(f"  {key} {pred.type.value:20} {pred.generic:24} {pred.row_ids[:4]} {pred.detail}")


# --------------------------------------------------------------------------- #
# One patient, printed
# --------------------------------------------------------------------------- #


def show(world: World, key: str, review: str) -> int:
    patient = next((p for p in world.truth["patients"] if p["patient_key"] == key), None)
    if patient is None:
        sys.exit(f"no patient {key}")
    rec = reconcile(world, patient, review)
    if rec is None:
        sys.exit(f"{key}: anchor not found")
    log(f"{key}  linked: {rec.linked_keys}  (review={review}, {rec.needed_review} needed a human)")
    log("coverage: " + ", ".join(f"{s}={c.state}" for s, c in rec.cov.items()))
    log("\nGRID")
    short = {EvidenceState.PRESENT: "P", EvidenceState.ABSENT_IN_SCOPE: "-",
             EvidenceState.UNKNOWN: "?"}
    for med in rec.fused:
        cells = " ".join(f"{s[:3]}:{short[med.per_source.get(s, EvidenceState.UNKNOWN)]}"
                         for s in SOURCES)
        attrs = [f"{n}={'CONFLICT' if v.abstained else v.value}" for n, v in med.attributes.items()]
        log(f"  {med.generic:26} {cells}   {'  '.join(attrs)}")
    log("\nFINDINGS (ranked)")
    for f in rec.findings:
        tier = "MUST REVIEW" if f.priority >= MUST_REVIEW_FLOOR else ""
        log(f"  {f.priority:5.2f} {tier:11} {f.type.value:20} {f.generic:24} {f.severity:6} "
            f"{f.row_ids[:4]}")
    log("\nPLANTED")
    for f in patient["planted"]:
        log(f"  {f['type']:20} {f['generic']:24} {f['row_ids']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patient", help="show one patient's grid and findings")
    ap.add_argument("--split", choices=("tune", "heldout", "all"), default="tune")
    ap.add_argument("--review", choices=("oracle", "none"), default="oracle",
                    help="who resolves review-band identity links (default: a simulated "
                         "pharmacist who confirms only true links)")
    ap.add_argument("--misses", action="store_true", help="list misses and false positives")
    ap.add_argument("--json", type=pathlib.Path, metavar="PATH",
                    help="also write the scorecard as JSON (see scripts/scorecard_page.py)")
    args = ap.parse_args()
    world = load_world()
    if args.patient:
        return show(world, args.patient, args.review)
    split = world.truth["split"]
    keys = split["tune"] + split["heldout"] if args.split == "all" else split[args.split]
    result = score(world, keys, args.review)
    report(result, args.split, args.review, args.misses)
    if args.json:
        args.json.write_text(json.dumps(as_json(result, args.split, args.review), indent=1))
        log(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
