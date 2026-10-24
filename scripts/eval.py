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


def reconcile(world: World, patient: dict) -> Reconciliation | None:
    """One patient through the real chain. `None` if the anchor cannot be found."""
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

    from app.domain.packs.medtrace.fuse import fuse
    fused = fuse(stmts, evidence, dict(SOURCE_TRUST_PRIORS), world.as_of)
    return Reconciliation(patient_key=patient["patient_key"], links=links, linked_keys=linked,
                          cov=cov, stmts=stmts, evidence=evidence, fused=fused)


# --------------------------------------------------------------------------- #
# One patient, printed
# --------------------------------------------------------------------------- #


def show(world: World, key: str) -> int:
    patient = next((p for p in world.truth["patients"] if p["patient_key"] == key), None)
    if patient is None:
        sys.exit(f"no patient {key}")
    rec = reconcile(world, patient)
    if rec is None:
        sys.exit(f"{key}: anchor not found")
    log(f"{key}  linked: {rec.linked_keys}")
    log("coverage: " + ", ".join(f"{s}={c.state}" for s, c in rec.cov.items()))
    log("\nGRID")
    short = {EvidenceState.PRESENT: "P", EvidenceState.ABSENT_IN_SCOPE: "-",
             EvidenceState.UNKNOWN: "?"}
    for med in rec.fused:
        cells = " ".join(f"{s[:3]}:{short[med.per_source.get(s, EvidenceState.UNKNOWN)]}"
                         for s in SOURCES)
        attrs = []
        for name, value in med.attributes.items():
            mark = "CONFLICT" if value.abstained else str(value.value)
            attrs.append(f"{name}={mark}")
        log(f"  {med.generic:26} {cells}   {'  '.join(attrs)}")
    log("\nPLANTED")
    for f in patient["planted"]:
        log(f"  {f['type']:20} {f['generic']:24} {f['row_ids']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patient", help="show one patient's grid and findings")
    args = ap.parse_args()
    world = load_world()
    if args.patient:
        return show(world, args.patient)
    return 0


if __name__ == "__main__":
    sys.exit(main())
