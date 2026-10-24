"""Record linkage across the four silos (brief section 1; PLAN 2.5).

Two tiers. A matching synthetic IHI is decisive; everything else is
Fellegi-Sunter, where each field contributes a log2 weight for agreeing or
disagreeing and the sum becomes a posterior.

The asymmetry that drives every threshold here: a **missed link** shows the
pharmacist one fewer source and a visible coverage gap, while a **false merge**
silently blends two patients' medicines into one list. The first is a stated
limitation; the second is a safety incident. So guards push to `review` rather
than resolving, and false-merge rate has a target of zero (PLAN 4, Sunday).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date

import jellyfish

from app.domain.packs.medtrace.parse import normalise_text
from app.domain.packs.medtrace.types import IdentityBand, IdentityLink, Lexicon, SourceRow

#: Fellegi-Sunter posterior at or above this merges without asking.
AUTO_MERGE_THRESHOLD = 0.85
#: Between this and `AUTO_MERGE_THRESHOLD`, a human decides.
REVIEW_THRESHOLD = 0.82

#: Prior odds that two arbitrary records are the same person. Deliberately low:
#: most pairs in a candidate set are strangers who share a birth year. Hand-set
#: today and re-estimated from the tune split on Sunday (PLAN 2.5), which is
#: why it is one named constant rather than scattered through the weights.
PRIOR_ODDS = 0.001

#: `field -> (weight if it agrees, weight if it disagrees)`, in log2 odds.
#: Derived from hand-set m/u probabilities; the comment on each line is the m/u
#: pair it came from, so Sunday's re-estimation has something to replace.
WEIGHTS: dict[str, tuple[float, float]] = {
    "surname":  (7.49, -3.31),   # m .90 / u .005 -- highly discriminating
    "given":    (4.82, -2.69),   # m .85 / u .03
    "dob":      (11.58, -3.64),  # m .92 / u .0003 -- the strongest single field
    "sex":      (0.97, -4.64),   # m .98 / u .50 -- weak to agree, strong to disagree
    "postcode": (5.13, -1.71),   # m .70 / u .02 -- see the note below
}

#: Partial-credit weights for the near-misses the generator plants (DATA_SPEC 7).
#: Each is worth less than an exact match and far more than a disagreement.
PARTIAL: dict[str, float] = {
    "given_nickname": 4.00,           # Margaret ~ Peggy, via an unambiguous variant
    "given_nickname_ambiguous": 2.74, # ... via a variant belonging to two canonicals
    "given_fuzzy": 2.40,              # Jaro-Winkler >= 0.90, e.g. a one-char typo
    "surname_previous": 6.00,         # matches the recorded maiden/previous surname
    "surname_phonetic": 3.80,         # Smyth ~ Smith, same metaphone code
    "surname_fuzzy": 2.20,
    "dob_swap": 7.64,                 # day and month transposed
    "dob_one_digit": 4.90,            # a single digit differs
    "dob_year_near": 3.32,            # year out by 1 or 10
}

#: Jaro-Winkler at or above this counts as a fuzzy agreement.
FUZZY_THRESHOLD = 0.90

#: A `review`-band ceiling applied when a guard fires. A guard can only ever
#: *demote*: it never raises a score, because every guard is a reason to doubt.
GUARD_CEILING = 0.84

_DIGITS = re.compile(r"\d")


def decide(probability: float) -> IdentityBand:
    """Band a posterior: `>=0.85` auto-merge, `>=0.82` review, else new.

    **TODO (Arpon, 4pm): replace with `app.engines.world_model.decide`.** This is
    a deliberate three-line duplicate so `identity.py` is importable before
    Arnav's World Model port lands (PLAN 5.9, 7). The thresholds are the same
    numbers; when the engine lands this body becomes a delegation and the
    constants above are deleted.

    The 0.82-0.85 review band is narrow on purpose. It is the only part of the
    pipeline that stops the run and asks a human (`needs_review`), so widening it
    costs a pharmacist's attention on every patient and narrowing it converts
    near-misses into silent merges.
    """
    if probability >= AUTO_MERGE_THRESHOLD:
        return "auto-merge"
    if probability >= REVIEW_THRESHOLD:
        return "review"
    return "new"


def _posterior(weight: float) -> float:
    """Log2-odds -> probability, with the prior folded in."""
    log_odds = math.log2(PRIOR_ODDS) + weight
    # Clamp before exponentiating: a 40-field agreement would otherwise overflow.
    log_odds = max(-60.0, min(60.0, log_odds))
    return 1.0 / (1.0 + 2.0 ** (-log_odds))


def _compare_given(a: SourceRow, b: SourceRow, lex: Lexicon) -> tuple[float, str | None]:
    """Given names, through the nickname table and then string distance."""
    left, right = normalise_text(a.name_given), normalise_text(b.name_given)
    if not left or not right:
        return 0.0, None
    if left == right:
        return WEIGHTS["given"][0], "given name matches exactly"

    # The pharmacy silo holds "SMITH, Margaret" in one field, so compare parts too.
    left_parts = {p for p in re.split(r"[,\s]+", left) if p}
    right_parts = {p for p in re.split(r"[,\s]+", right) if p}
    if left_parts & right_parts:
        return WEIGHTS["given"][0], "given name matches exactly (within a combined name field)"

    for lpart in left_parts or {left}:
        family = lex.nicknames.get(lpart, frozenset())
        hit = family & (right_parts or {right})
        if hit:
            other = next(iter(hit))
            # A variant belonging to two canonical names is weaker evidence:
            # "Chris" could be Christine or Christopher.
            ambiguous = _is_ambiguous(lpart, lex) or _is_ambiguous(other, lex)
            key = "given_nickname_ambiguous" if ambiguous else "given_nickname"
            label = "ambiguous nickname" if ambiguous else "nickname"
            return PARTIAL[key], f"{label} {a.name_given} ~ {b.name_given}"

    score = jellyfish.jaro_winkler_similarity(left, right)
    if score >= FUZZY_THRESHOLD:
        return PARTIAL["given_fuzzy"], f"given name differs slightly ({score:.2f})"
    return WEIGHTS["given"][1], f"given name differs ({a.name_given} vs {b.name_given})"


def _is_ambiguous(name: str, lex: Lexicon) -> bool:
    """Whether a name belongs to more than one canonical family.

    The nickname map is closed within a canonical name but deliberately **not**
    across one (`parse.build_lexicon`), so `nicknames["chris"]` holds Christine
    and Christopher while neither holds the other. That asymmetry is the signal:
    a family containing two names that are not in each other's families came
    from two canonicals, so the variant is ambiguous and worth less as evidence.
    """
    family = lex.nicknames.get(name, frozenset())
    return any(other not in lex.nicknames.get(member, frozenset())
               for member in family for other in family)


def _current_surname(row: SourceRow) -> str:
    """`name_family`, or the surname inside a combined "SURNAME, Given" field."""
    if row.name_family:
        return normalise_text(row.name_family)
    if row.name_given and "," in row.name_given:
        return normalise_text(row.name_given.split(",", 1)[0])
    return ""


def _compare_surname(a: SourceRow, b: SourceRow) -> tuple[float, str | None]:
    """Surnames, against both the current and any recorded previous surname."""
    lefts = {normalise_text(a.name_family), normalise_text(a.name_previous)} - {""}
    rights = {normalise_text(b.name_family), normalise_text(b.name_previous)} - {""}
    # The pharmacy silo has no surname column; its surname is the first part of
    # the combined name field.
    for row, bucket in ((a, lefts), (b, rights)):
        if not row.name_family and row.name_given and "," in (row.name_given or ""):
            bucket.add(normalise_text(row.name_given.split(",", 1)[0]))
    if not lefts or not rights:
        return 0.0, None

    # The current surname includes the one parsed from a combined name field.
    # Comparing only `name_family` here meant a pharmacy record -- whose surname
    # exists only inside "PAPADOPOULOS, Thomas" -- could never match exactly, so
    # an exact match fell through to the previous-surname branch below and was
    # labelled AND weighted as a maiden-name match (spotted by Arnav on P0002).
    current = {_current_surname(a)} & {_current_surname(b)} - {""}
    if current:
        return WEIGHTS["surname"][0], "surname matches exactly"
    if lefts & rights:
        return PARTIAL["surname_previous"], "surname matches a previous surname"

    for left in lefts:
        for right in rights:
            if jellyfish.metaphone(left) == jellyfish.metaphone(right):
                return PARTIAL["surname_phonetic"], f"surname sounds the same ({left} ~ {right})"
            if jellyfish.jaro_winkler_similarity(left, right) >= FUZZY_THRESHOLD:
                return PARTIAL["surname_fuzzy"], f"surname differs slightly ({left} ~ {right})"
    return WEIGHTS["surname"][1], "surname differs"


def _compare_dob(a: SourceRow, b: SourceRow) -> tuple[float, str | None]:
    """Dates of birth, with partial credit for the planted corruptions.

    Compares the parsed dates where both parsed, so `1948-07-03` and
    `03/07/1948` agree. The raw text is the fallback when one side is
    unparseable, which is itself a fact about that silo.
    """
    left, right = a.dob, b.dob
    if left is None or right is None:
        lraw, rraw = (a.dob_raw or "").strip(), (b.dob_raw or "").strip()
        if lraw and rraw and lraw == rraw:
            return WEIGHTS["dob"][0], "date of birth matches exactly (unparsed)"
        return 0.0, None
    if left == right:
        return WEIGHTS["dob"][0], "date of birth matches exactly"

    swapped = _swap_day_month(left)
    if swapped is not None and swapped == right:
        return PARTIAL["dob_swap"], (
            f"date of birth day and month transposed ({left.isoformat()} vs {right.isoformat()})")

    ldigits, rdigits = left.strftime("%Y%m%d"), right.strftime("%Y%m%d")
    differing = sum(1 for x, y in zip(ldigits, rdigits) if x != y)
    if differing == 1:
        return PARTIAL["dob_one_digit"], (
            f"date of birth differs by one digit ({left.isoformat()} vs {right.isoformat()})")
    if (left.month, left.day) == (right.month, right.day) and abs(left.year - right.year) in (1, 10):
        return PARTIAL["dob_year_near"], (
            f"date of birth year out by {abs(left.year - right.year)}")
    return WEIGHTS["dob"][1], "date of birth differs"


def _swap_day_month(value: date) -> date | None:
    if value.day > 12 or value.day == value.month:
        return None
    try:
        return date(value.year, value.day, value.month)
    except ValueError:
        return None


def score_pair(a: SourceRow, b: SourceRow, lex: Lexicon) -> IdentityLink:
    """Score one candidate pairing, with the field-level reasons.

    Tier 1 -- `ihi_syn`:
      - equal -> probability 1.0, tier `ihi_exact`.
      - both present and different -> **hard non-link**, tier `ihi_conflict`.
        Not a low score: two different IHIs are positive evidence of two people,
        and no amount of name agreement should overturn it.

    Tier 2 -- Fellegi-Sunter, tier `probabilistic`. Every contributing
    comparison is recorded in `field_evidence` in the words the UI shows the
    pharmacist, because "0.83" is not something anyone can act on and
    "same DOB, surname differs by one letter" is.

    A field missing on either side contributes **nothing** rather than counting
    as disagreement. Three of the four silos have no `sex` column at all, so
    scoring absence as disagreement would push every cross-source pair down.
    """
    evidence: dict[str, str] = {}

    left_ihi, right_ihi = (a.ihi_syn or "").strip(), (b.ihi_syn or "").strip()
    if left_ihi and right_ihi:
        if left_ihi == right_ihi:
            return IdentityLink(
                anchor_id=a.record_key, candidate_id=b.record_key,
                match_weight=float("inf") if False else 99.0, probability=1.0,
                band="auto-merge", tier="ihi_exact",
                field_evidence={"ihi_syn": "same synthetic IHI"}, guards=[])
        return IdentityLink(
            anchor_id=a.record_key, candidate_id=b.record_key,
            match_weight=-99.0, probability=0.0, band="new", tier="ihi_conflict",
            field_evidence={"ihi_syn": f"different synthetic IHI ({left_ihi} vs {right_ihi})"},
            guards=["ihi_conflict"])

    weight = 0.0
    for field, (compare, label) in {
        "given": (lambda: _compare_given(a, b, lex), "given"),
        "surname": (lambda: _compare_surname(a, b), "surname"),
        "dob": (lambda: _compare_dob(a, b), "dob"),
    }.items():
        contribution, note = compare()
        weight += contribution
        if note:
            evidence[field] = note

    left_sex, right_sex = normalise_text(a.sex)[:1], normalise_text(b.sex)[:1]
    if left_sex and right_sex:
        agree = left_sex == right_sex
        weight += WEIGHTS["sex"][0 if agree else 1]
        evidence["sex"] = "sex matches" if agree else "sex differs"

    left_pc, right_pc = (a.postcode or "").strip(), (b.postcode or "").strip()
    if left_pc and right_pc:
        agree = left_pc == right_pc
        # Weak positive only. Agreement is common by chance in an age-skewed
        # cohort, and disagreement usually just means someone moved.
        weight += WEIGHTS["postcode"][0 if agree else 1]
        evidence["postcode"] = "postcode matches" if agree else "postcode differs (a move?)"

    probability = _posterior(weight)
    return IdentityLink(
        anchor_id=a.record_key, candidate_id=b.record_key,
        match_weight=round(weight, 3), probability=round(probability, 6),
        band=decide(probability), tier="probabilistic",
        field_evidence=evidence, guards=[])


def _collapse(rows: list[SourceRow]) -> dict[str, SourceRow]:
    """One representative row per `(source, source_patient_id)`.

    Q1 returns one row per medicine, so a record appears many times. The
    representative is the most complete row, because demographics can be
    sparser on some rows than others within the same record.
    """
    best: dict[str, SourceRow] = {}
    for row in rows:
        key = row.record_key
        filled = sum(1 for v in (row.ihi_syn, row.name_given, row.name_family,
                                 row.dob_raw, row.sex, row.postcode) if v)
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        current_filled = sum(1 for v in (current.ihi_syn, current.name_given, current.name_family,
                                         current.dob_raw, current.sex, current.postcode) if v)
        if filled > current_filled:
            best[key] = row
    return best


def link_identity(anchor: SourceRow, candidates: list[SourceRow], lex: Lexicon) -> list[IdentityLink]:
    """Score every candidate against the anchor, then apply the guards.

    Candidates arrive as rows (Q1 returns one row per medicine), so they are
    first collapsed to one record per `(source, source_patient_id)`.

    Guards, each of which can only *demote* a band:
      - `lookalike_cluster`: two records **within one source** that both score
        highly and are indistinguishable from each other. The planted lookalike
        and twin pairs are exactly this, and the arithmetic cannot tell them
        apart -- so the threshold rises and a distinguishing field is required.
      - `transitivity_suspect`: A~B and B~C but not A~C. The triangle is
        inconsistent, so at most one of the three can be trusted silently.
      - `overlay_suspect`: `detect_overlay` flagged the candidate record.

    Returns at most one link per candidate record, highest probability first.
    """
    records = _collapse(candidates)
    rows_by_record: dict[str, list[SourceRow]] = defaultdict(list)
    for row in candidates:
        rows_by_record[row.record_key].append(row)

    links: list[IdentityLink] = []
    for key, row in records.items():
        if key == anchor.record_key:
            continue
        links.append(score_pair(anchor, row, lex))

    # -- cluster the candidates among themselves ------------------------------
    # A lookalike's records do not all carry an IHI. Scoring each candidate
    # against the anchor in isolation therefore rejects the decoy's EMR, GP and
    # pharmacy records (their IHI conflicts) while *accepting* its patient-
    # interview record, which has no IHI and an identical name and DOB.
    #
    # The evidence to reject it was already in hand, just attached to a sibling.
    # So candidates are clustered against each other first, and an IHI conflict
    # anywhere in a cluster condemns the whole cluster. This is what takes the
    # planted lookalike traps from 2 false merges to 0.
    keys = sorted(records)
    parent = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if find(left) == find(right):
                continue
            if score_pair(records[left], records[right], lex).probability >= AUTO_MERGE_THRESHOLD:
                parent[find(left)] = find(right)

    clusters: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        clusters[find(key)].append(key)

    anchor_ihi = (anchor.ihi_syn or "").strip()
    if anchor_ihi:
        rejected: set[str] = set()
        ambiguous: set[str] = set()
        for members in clusters.values():
            ihis = {(records[m].ihi_syn or "").strip() for m in members} - {""}
            conflicting = ihis - {anchor_ihi}
            if not conflicting:
                continue
            # The cluster holds someone else's IHI. Members carrying it are that
            # person. Members carrying NO IHI are not known to be: a lookalike
            # is identical on name and date of birth, so an un-identified record
            # is equally consistent with either person. We cannot tell, and
            # pretending otherwise either way is wrong -- so they go to a human.
            # This is the demo's "a lookalike refused auto-link, one review
            # click".
            #
            # That used to apply only when the patient's own IHI also appeared
            # in the cluster. When it did not -- P0008, whose GP, pharmacy and
            # interview records all lack an IHI while the lookalike's carry
            # one -- the whole cluster was rejected, the patient's own records
            # with it, and every finding resting on them was lost. Review never
            # merges anything, so this cannot raise the false-merge rate.
            ambiguous.update(m for m in members if not (records[m].ihi_syn or "").strip())
            if anchor_ihi not in ihis:
                rejected.update(m for m in members if (records[m].ihi_syn or "").strip())

        for link in links:
            if link.tier == "ihi_conflict":
                continue
            if link.candidate_id in rejected:
                link.guards.append("ihi_conflict_in_cluster")
                link.field_evidence["guard"] = (
                    "another record that is clearly the same person as this one carries an "
                    "IHI that conflicts with the patient's, so this belongs to someone else"
                )
                link.probability = 0.0
                link.band = "new"
            elif link.candidate_id in ambiguous:
                link.guards.append("ihi_ambiguous_in_cluster")
                link.field_evidence["guard"] = (
                    "this record carries no IHI and is an equally good match for two "
                    "different people with the same name and date of birth — confirm which"
                )
                link.probability = min(link.probability, GUARD_CEILING)
                link.band = decide(link.probability)

    # -- lookalike guard: two plausible records inside one source -------------
    plausible_by_source: dict[str, list[IdentityLink]] = defaultdict(list)
    for link in links:
        if link.probability >= REVIEW_THRESHOLD:
            plausible_by_source[link.candidate_id.split(":", 1)[0]].append(link)
    for source, group in plausible_by_source.items():
        if len(group) < 2:
            continue
        for link in group:
            link.guards.append("lookalike_cluster")
            link.field_evidence["guard"] = (
                f"{len(group)} records in {source} score as this patient; a distinguishing "
                f"field or a human decision is needed before merging either"
            )

    # -- transitivity guard: an inconsistent triangle -------------------------
    accepted = [l for l in links if l.probability >= AUTO_MERGE_THRESHOLD]
    for i, first in enumerate(accepted):
        for second in accepted[i + 1:]:
            a_row, b_row = records[first.candidate_id], records[second.candidate_id]
            if score_pair(a_row, b_row, lex).probability < REVIEW_THRESHOLD:
                for link in (first, second):
                    if "transitivity_suspect" not in link.guards:
                        link.guards.append("transitivity_suspect")
                        link.field_evidence["guard"] = (
                            "both records match this patient but not each other, so at most "
                            "one of them can be right"
                        )

    # -- overlay guard --------------------------------------------------------
    for link in links:
        reasons = detect_overlay(rows_by_record.get(link.candidate_id, []))
        if reasons:
            link.guards.append("overlay_suspect")
            link.field_evidence["guard"] = "; ".join(reasons)

    # A guard can only demote. It never raises a band, because every guard is a
    # reason to doubt -- and a false merge is the one error with a target of zero.
    for link in links:
        if link.guards and link.tier != "ihi_exact":
            capped = min(link.probability, GUARD_CEILING)
            link.probability = capped
            link.band = decide(capped)

    links.sort(key=lambda l: (-l.probability, l.candidate_id))
    return links


def detect_overlay(rows_for_one_record: list[SourceRow]) -> list[str]:
    """Flag a single source record that looks like two people merged upstream.

    Signals: two different DOBs or sexes under one `source_patient_id`, or the
    same chronic drug dispensed at two pharmacies on the same day. An overlay in
    the *source* data is the one case where linking correctly still produces a
    wrong medication list, so it is surfaced rather than resolved.

    Stretch (PLAN 4, cut order item 1). Returns the reasons found, or `[]`.
    """
    if len(rows_for_one_record) < 2:
        return []
    reasons: list[str] = []

    dobs = {r.dob_raw for r in rows_for_one_record if r.dob_raw}
    if len(dobs) > 1:
        reasons.append(f"one record holds {len(dobs)} different dates of birth "
                       f"({', '.join(sorted(dobs)[:3])})")
    sexes = {normalise_text(r.sex)[:1] for r in rows_for_one_record if r.sex}
    if len(sexes) > 1:
        reasons.append("one record holds more than one sex")
    names = {normalise_text(r.name_family) for r in rows_for_one_record if r.name_family}
    if len(names) > 1:
        reasons.append(f"one record holds {len(names)} different surnames")

    same_day: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows_for_one_record:
        if row.med_text and row.doc_date and row.pharmacy_id:
            same_day[(normalise_text(row.med_text), row.doc_date.isoformat())].add(row.pharmacy_id)
    doubled = [med for (med, _day), ids in same_day.items() if len(ids) > 1]
    if doubled:
        reasons.append(f"the same medicine dispensed at two pharmacies on one day "
                       f"({', '.join(sorted(doubled)[:3])})")
    return reasons
