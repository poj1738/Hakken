"""`identity.py`: record linkage, and the guards that keep false merges at zero.

The asymmetry this module is built around: a **missed link** shows the pharmacist
one fewer source and a visible coverage gap. A **false merge** silently blends
two patients' medicines into one list. The first is a stated limitation; the
second is a safety incident. So every guard here can only *demote*, and the
end-to-end test at the bottom pins false-merge rate at zero.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from app.domain.packs.medtrace.identity import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    decide,
    detect_overlay,
    link_identity,
    score_pair,
)
from app.domain.packs.medtrace.parse import build_lexicon, dicts_from_sql, rows_from_sql
from app.domain.packs.medtrace.types import SourceRow

FIXTURES = pathlib.Path("tests/fixtures/medtrace")

pytestmark = pytest.mark.skipif(
    not (FIXTURES / "Q_REF__nicknames.json").exists(), reason="run `make lexicon` first"
)


@pytest.fixture(scope="module")
def lex():
    load = lambda n: dicts_from_sql(json.loads((FIXTURES / f"Q_REF__{n}.json").read_text()))
    return build_lexicon(load("lexicon"), load("apinchs"), load("nicknames"))


def row(source="emr", pid="MRN1", **kwargs) -> SourceRow:
    base = {"source": source, "row_id": f"{source.upper()}-1", "source_patient_id": pid}
    return SourceRow(**(base | kwargs))


# --------------------------------------------------------------------------- #
# Tier 1: the IHI is decisive
# --------------------------------------------------------------------------- #


def test_the_same_ihi_is_a_certain_match(lex) -> None:
    a = row(ihi_syn="SYN-000000000001", name_given="Margaret", name_family="Smith")
    b = row("gp", "GP1", ihi_syn="SYN-000000000001", name_given="Completely", name_family="Different")
    link = score_pair(a, b, lex)
    assert (link.tier, link.band, link.probability) == ("ihi_exact", "auto-merge", 1.0)


def test_conflicting_ihis_are_a_hard_non_link_whatever_else_agrees(lex) -> None:
    """Two different IHIs are **positive evidence of two people**. No amount of
    name and date-of-birth agreement should overturn that -- which is exactly
    the situation a lookalike pair creates."""
    a = row(ihi_syn="SYN-000000000001", name_given="Margaret", name_family="Smith",
            dob=date(1948, 7, 3), dob_raw="1948-07-03")
    b = row("gp", "GP1", ihi_syn="SYN-000000000002", name_given="Margaret",
            name_family="Smith", dob=date(1948, 7, 3), dob_raw="1948-07-03")
    link = score_pair(a, b, lex)
    assert link.tier == "ihi_conflict"
    assert link.band == "new"
    assert link.probability == 0.0


def test_one_missing_ihi_falls_through_to_the_probabilistic_tier(lex) -> None:
    a = row(ihi_syn="SYN-000000000001", name_given="Margaret", name_family="Smith",
            dob=date(1948, 7, 3))
    b = row("gp", "GP1", name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    assert score_pair(a, b, lex).tier == "probabilistic"


# --------------------------------------------------------------------------- #
# Tier 2 comparators
# --------------------------------------------------------------------------- #


def test_a_nickname_counts_as_agreement(lex) -> None:
    """Margaret ~ Peggy. String distance alone scores this as a non-match, which
    is the whole reason the nickname table exists."""
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("gp", "GP1", name_given="Peggy", name_family="Smith", dob=date(1948, 7, 3))
    link = score_pair(a, b, lex)
    assert link.band == "auto-merge"
    assert "nickname" in link.field_evidence["given"]


def test_an_ambiguous_nickname_is_weaker_than_an_unambiguous_one(lex) -> None:
    """`Chris` belongs to both Christine and Christopher, so it is worth less as
    evidence than `Peggy`, which only ever means Margaret."""
    base = {"name_family": "Smith", "dob": date(1948, 7, 3)}
    unambiguous = score_pair(row(name_given="Margaret", **base),
                             row("gp", "GP1", name_given="Peggy", **base), lex)
    ambiguous = score_pair(row(name_given="Christine", **base),
                           row("gp", "GP1", name_given="Chris", **base), lex)
    assert ambiguous.match_weight < unambiguous.match_weight
    assert "ambiguous" in ambiguous.field_evidence["given"]


def test_a_phonetic_surname_match_counts(lex) -> None:
    """Smyth ~ Smith. The demo's opening scene depends on this."""
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("pharmacy", "C1", name_given="Margaret", name_family="Smyth", dob=date(1948, 7, 3))
    link = score_pair(a, b, lex)
    assert "sounds the same" in link.field_evidence["surname"]
    assert link.probability >= REVIEW_THRESHOLD


def test_a_previous_surname_matches(lex) -> None:
    """A maiden name must agree rather than disagree, or every married woman who
    changed her name looks like a different person."""
    a = row(name_given="Margaret", name_family="Jones", dob=date(1948, 7, 3))
    b = row("gp", "GP1", name_given="Margaret", name_family="Smith",
            name_previous="Jones", dob=date(1948, 7, 3))
    link = score_pair(a, b, lex)
    assert "previous surname" in link.field_evidence["surname"]
    assert link.band == "auto-merge"


def test_a_transposed_date_of_birth_gets_partial_credit(lex) -> None:
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("patient", "INT1", name_given="Margaret", name_family="Smith", dob=date(1948, 3, 7))
    link = score_pair(a, b, lex)
    assert "transposed" in link.field_evidence["dob"]
    assert link.probability >= REVIEW_THRESHOLD


def test_a_one_digit_date_of_birth_typo_gets_partial_credit(lex) -> None:
    a = row(name_given="Margaret", name_family="Smith", dob=date(1946, 7, 3))
    b = row("gp", "GP1", name_given="Margaret", name_family="Smith", dob=date(1946, 7, 8))
    assert "one digit" in score_pair(a, b, lex).field_evidence["dob"]


def test_a_genuinely_different_birthday_is_strong_negative_evidence(lex) -> None:
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("gp", "GP1", name_given="Margaret", name_family="Smith", dob=date(1961, 11, 24))
    assert score_pair(a, b, lex).band == "new"


def test_a_missing_field_contributes_nothing_rather_than_disagreeing(lex) -> None:
    """Three of the four silos have no `sex` column at all. Scoring absence as
    disagreement would push every cross-source pair down."""
    both = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3), sex="F")
    with_sex = row("gp", "GP1", name_given="Margaret", name_family="Smith",
                   dob=date(1948, 7, 3), sex="F")
    without = row("pharmacy", "C1", name_given="Margaret", name_family="Smith",
                  dob=date(1948, 7, 3))
    assert score_pair(both, without, lex).match_weight < score_pair(both, with_sex, lex).match_weight
    assert score_pair(both, without, lex).band == "auto-merge"


def test_the_pharmacy_combined_name_field_is_understood(lex) -> None:
    """The pharmacy silo holds `"SMITH, Margaret"` in one column and has no
    surname column, so a naive comparison finds no surname at all."""
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("pharmacy", "C1", name_given="SMITH, Margaret", dob=date(1948, 7, 3))
    link = score_pair(a, b, lex)
    assert link.band == "auto-merge"


def test_field_evidence_is_written_for_a_human(lex) -> None:
    """A pharmacist cannot act on 0.83. They can act on "same DOB, surname
    sounds the same"."""
    a = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    b = row("pharmacy", "C1", name_given="Peggy", name_family="Smyth", dob=date(1948, 3, 7))
    evidence = score_pair(a, b, lex).field_evidence
    assert {"given", "surname", "dob"} <= set(evidence)
    assert all(len(v) > 10 and not v[0].isdigit() for v in evidence.values())


@pytest.mark.parametrize(("probability", "band"), [
    (1.0, "auto-merge"), (0.85, "auto-merge"), (0.8499, "review"),
    (0.82, "review"), (0.8199, "new"), (0.0, "new"),
])
def test_decide_bands(probability: float, band: str) -> None:
    assert decide(probability) == band


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


def test_an_ihi_conflict_elsewhere_in_a_cluster_demotes_a_record_with_no_ihi(lex) -> None:
    """The failure this was written for.

    A lookalike's records do not all carry an IHI. Scored in isolation, the
    decoy's EMR/GP/pharmacy records are rejected on their conflicting IHI while
    its *patient-interview* record -- no IHI, identical name and date of birth --
    sails through at 0.99 and is merged. The evidence to stop that was already
    in hand, attached to a sibling record.
    """
    anchor = row(ihi_syn="SYN-000000000001", name_given="Margaret",
                 name_family="Smith", dob=date(1948, 7, 3), dob_raw="1948-07-03")
    decoy_with_ihi = row("gp", "GP9", ihi_syn="SYN-000000000002", name_given="Margaret",
                         name_family="Smith", dob=date(1948, 7, 3), dob_raw="1948-07-03")
    decoy_without = row("patient", "INT9", name_given="Margaret", name_family="Smith",
                        dob=date(1948, 7, 3), dob_raw="1948-07-03")
    links = {l.candidate_id: l for l in link_identity(anchor, [decoy_with_ihi, decoy_without], lex)}
    assert links["gp:GP9"].band == "new"            # tier 1 rejects it outright
    assert links["patient:INT9"].band != "auto-merge"
    # Review, not rejection. Here INT9 happens to be the decoy, but nothing in
    # the record says so -- same name, same DOB, no IHI -- so it is equally
    # consistent with the patient. Rejecting such records outright threw away
    # P0008's own GP, pharmacy and interview records (25 Oct). Review never
    # merges, so the false-merge guarantee this test exists for is unchanged.
    assert links["patient:INT9"].band == "review"
    assert "ihi_ambiguous_in_cluster" in links["patient:INT9"].guards


def test_a_record_equally_consistent_with_two_people_goes_to_a_human(lex) -> None:
    """When the cluster holds both the patient's IHI and someone else's, a
    member carrying no IHI is an equally good match for either. We cannot tell,
    and pretending otherwise is how a false merge happens -- so it is a review,
    not a merge and not a rejection."""
    anchor = row(ihi_syn="SYN-000000000001", name_given="Margaret", name_family="Smith",
                 dob=date(1948, 7, 3), dob_raw="1948-07-03")
    mine = row("pharmacy", "C1", ihi_syn="SYN-000000000001", name_given="Margaret",
               name_family="Smith", dob=date(1948, 7, 3), dob_raw="1948-07-03")
    theirs = row("emr", "MRN9", ihi_syn="SYN-000000000002", name_given="Margaret",
                 name_family="Smith", dob=date(1948, 7, 3), dob_raw="1948-07-03")
    unknown = row("patient", "INT9", name_given="Margaret", name_family="Smith",
                  dob=date(1948, 7, 3), dob_raw="1948-07-03")
    links = {l.candidate_id: l for l in link_identity(anchor, [mine, theirs, unknown], lex)}
    assert links["pharmacy:C1"].band == "auto-merge"        # carries the patient's own IHI
    assert links["patient:INT9"].band == "review"
    assert "ihi_ambiguous_in_cluster" in links["patient:INT9"].guards


def test_two_plausible_records_in_one_source_both_go_to_review(lex) -> None:
    """A planted lookalike inside one source. The arithmetic cannot separate
    them, so neither may be merged silently."""
    anchor = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    first = row("gp", "GP1", name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    second = row("gp", "GP2", name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    links = link_identity(anchor, [first, second], lex)
    assert all("lookalike_cluster" in l.guards for l in links)
    assert all(l.band != "auto-merge" for l in links)


def test_a_guard_can_only_demote(lex) -> None:
    """Every guard is a reason to doubt, so none may raise a band."""
    anchor = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    weak = row("gp", "GP1", name_given="Unrelated", name_family="Person", dob=date(1970, 1, 1))
    link = link_identity(anchor, [weak], lex)[0]
    assert link.band == "new"


def test_links_come_back_strongest_first(lex) -> None:
    anchor = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    strong = row("gp", "GP1", name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    weak = row("patient", "INT1", name_given="Unrelated", name_family="Person",
               dob=date(1970, 1, 1))
    links = link_identity(anchor, [weak, strong], lex)
    assert [l.probability for l in links] == sorted((l.probability for l in links), reverse=True)


def test_the_anchor_is_not_linked_to_itself(lex) -> None:
    anchor = row(name_given="Margaret", name_family="Smith", dob=date(1948, 7, 3))
    assert link_identity(anchor, [anchor], lex) == []


# --------------------------------------------------------------------------- #
# Overlay
# --------------------------------------------------------------------------- #


def test_detect_overlay_spots_two_people_under_one_record() -> None:
    """An overlay in the *source* data is the one case where linking correctly
    still produces a wrong medication list."""
    rows = [row("pharmacy", "C1", dob_raw="1948-07-03", name_family="Smith"),
            row("pharmacy", "C1", dob_raw="1961-11-24", name_family="Jones")]
    reasons = detect_overlay(rows)
    assert any("dates of birth" in r for r in reasons)
    assert any("surnames" in r for r in reasons)


def test_detect_overlay_is_quiet_on_a_clean_record() -> None:
    rows = [row("pharmacy", "C1", dob_raw="1948-07-03", name_family="Smith") for _ in range(4)]
    assert detect_overlay(rows) == []
    assert detect_overlay([]) == []


# --------------------------------------------------------------------------- #
# End to end, against the planted ground truth
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_linkage_against_ground_truth(lex) -> None:
    """The headline metrics, pinned.

    `false-merge rate` has a target of **zero** and is the one number this
    module exists to protect. F1 is held at DATA_SPEC 11.2's 0.95 target. If a
    weight change trades a false merge for a point of recall, this fails.
    """
    truth_by_key = {p["patient_key"]: p
                    for p in json.loads(pathlib.Path("data/synthetic/ground_truth.json").read_text())["patients"]}
    tp = fp = fn = false_merges = 0
    for path in sorted(FIXTURES.glob("Q1__*.json")):
        patient = truth_by_key[path.stem.split("__")[1]]
        rows = rows_from_sql(json.loads(path.read_text()))
        anchor_key = f"emr:{patient['true_links']['emr'][0]}"
        anchor = next((r for r in rows if r.record_key == anchor_key), None)
        if anchor is None:
            continue
        links = link_identity(anchor, rows, lex)
        truth = {f"{s}:{i}" for s, ids in patient["true_links"].items() for i in ids} - {anchor_key}
        decoys = {f"{s}:{i}" for trap in patient["identity_traps"]
                  for s, ids in truth_by_key[trap["other_patient_key"]]["true_links"].items()
                  for i in ids}
        merged = {l.candidate_id for l in links if l.band == "auto-merge"}
        review = {l.candidate_id for l in links if l.band == "review"}
        tp += len(merged & truth)
        fp += len(merged - truth)
        fn += len(truth - merged - review)
        false_merges += len(merged & decoys)

    assert false_merges == 0, f"{false_merges} merges across a planted identity trap"
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    assert precision >= 0.95, f"precision {precision:.3f}"
    assert f1 >= 0.95, f"F1 {f1:.3f} is below DATA_SPEC 11.2's target"


def test_a_combined_name_field_surname_is_an_exact_match_not_a_previous_one(lex) -> None:
    """The pharmacy silo writes one "SURNAME, Given" field. Its surname used to
    fall through to the previous-surname branch, labelled and weighted as a
    maiden-name match (spotted by Arnav on P0002)."""
    emr = row(name_given="Thomas", name_family="Papadopoulos",
              dob=date(1945, 3, 2), dob_raw="1945-03-02")
    pharmacy = row("pharmacy", "C1", name_given="PAPADOPOULOS, Thomas",
                   dob=date(1945, 3, 2), dob_raw="1945-03-02")
    link = score_pair(emr, pharmacy, lex)
    assert link.field_evidence["surname"] == "surname matches exactly"


def test_a_typo_inside_a_combined_given_family_field_is_still_a_close_given_name(lex) -> None:
    """The interview silo writes "Given Family" in one field. A one-letter typo
    used to be fuzzy-matched against the whole string -- "Marjorie" vs "Marorie
    Kaur" -- so it scored as a different given name, the surname was never
    compared, and P0076's interview record was lost."""
    emr = row(name_given="Marjorie", name_family="Kaur", dob=date(1950, 4, 9),
              dob_raw="1950-04-09")
    interview = row("patient", "INT1", name_given="Marorie Kaur", dob=date(1950, 4, 9),
                    dob_raw="1950-04-09")
    link = score_pair(emr, interview, lex)
    assert "slightly" in link.field_evidence["given"]
    assert link.field_evidence["surname"] == "surname matches exactly"
