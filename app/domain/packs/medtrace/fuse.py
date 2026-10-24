"""Trust-weighted resolution into the BPMH grid (brief section 8; PLAN 2.5).

Four sources disagree, and the question is which to believe about *which
attribute*. The pharmacy knows what was dispensed; the GP knows what was
intended; the patient knows what they actually swallow. That is why trust is
keyed `(source, attribute)` and not per source -- and why those weights are
H-MEM records that move with pharmacist feedback rather than constants.

The margin rule is the honest part. When the top two candidate values are within
`margin`, the attribute **abstains** and the UI shows "Conflict: ask patient".
A 0.02 margin is not a winner, and presenting it as one is how a tool teaches
its users to stop reading it.
"""

from __future__ import annotations

import math
from datetime import date

from app.domain.packs.medtrace.normalise import parse_frequency
from app.domain.packs.medtrace.supply import supply_status
from app.domain.packs.medtrace.trust import DEFAULT_TRUST
from app.domain.packs.medtrace.types import (
    FUSED_ATTRIBUTES,
    SOURCES,
    EvidenceState,
    FusedMed,
    FusedValue,
    MedStatement,
)

#: Recency time constant per source, in days: `recency = exp(-age / tau)`.
#: A dispensing record ages quickly, a GP list slowly, and the admission chart
#: and the patient interview are taken at admission, so barely at all.
TAU_DAYS: dict[str, float] = {"emr": 3650.0, "gp": 730.0, "pharmacy": 180.0, "patient": 3650.0}

PRESENT = "present"
ABSENT = "absent"


def fuse(
    stmts: list[MedStatement],
    evidence: dict[str, dict[str, EvidenceState]],
    trust: dict[tuple[str, str], float],
    as_of: date,
    margin: float = 0.2,
) -> list[FusedMed]:
    """Resolve every attribute of every medicine into one grid row.

    `score(v) = sum over sources of trust[s, attr] x recency(s) x scope_ok(s) x [s asserts v]`,
    with `recency(s) = exp(-dt / tau)` and `tau` per source type: a dispensing
    record ages quickly, a GP list slowly, an admission chart hardly at all.

    `evidence` is `generic -> source -> EvidenceState` from `coverage`, and an
    `UNKNOWN` source contributes **nothing in either direction** -- it neither
    supports a value nor counts against one. Weighting a source we never read
    would be inventing evidence.

    Attributes resolved: `existence`, `daily_dose`, `frequency`, `release`,
    `route` (`types.FUSED_ATTRIBUTES`). Any whose margin is too narrow lands in
    `FusedMed.abstained` with both candidates kept in `FusedValue.dissenting`,
    so the grid shows the disagreement rather than a false consensus.

    `trust` is passed in rather than read here, because this module is pure and
    the weights live in H-MEM. `trust.SOURCE_TRUST_PRIORS` is the seed.

    **The current admission chart does not vote.** The grid is a BPMH -- the
    best possible history of what the patient took *before* admission -- and
    the chart is the set of hospital orders being reconciled against it (ACSQHC
    Action 4.06). Letting the chart vote made it judge itself: with the GP
    record awaiting identity review, a chart error of 2.5 mg against a pharmacy
    supply of 5 mg resolved to 2.5 mg, because the chart's weight beat a
    six-week-old dispensing, and the dose error vanished. The chart is still in
    `per_source` (via `evidence`), so the grid shows what it says; it just does
    not get a vote on what is true. Older EMR documents -- a prior discharge
    summary -- are history, and do vote.

    How the votes are counted:

    - **One vote per source per attribute**, from that source's most recent
      statement of this medicine. Fourteen dispensings are one pharmacy's
      opinion, not fourteen.
    - **Existence** comes from `evidence` -- `ABSENT_IN_SCOPE` votes absent,
      `UNKNOWN` abstains. The pharmacy vote is `supply_status` instead: a supply
      that ran out months ago is evidence the medicine stopped, even though the
      pharmacy did dispense it once. Supply status already accounts for time,
      so that vote is not decayed again.
    - **Only sources voting "present" vote on dose, frequency, release and
      route.** A GP line marked ceased has no say over the current dose.
    - **Margin** is the winner's share of the two-way contest,
      `(top - second) / (top + second)`, so 0.2 means the winner needs about
      60/40 or better. Uncontested attributes have a margin of 1.

    `high_risk_class` is left `None`: it needs the lexicon, which this pure
    function is not given. `safety.high_risk_class(med.atc, lex)` fills it.
    """
    by_generic: dict[str, list[MedStatement]] = {}
    for stmt in stmts:
        if stmt.generic:
            by_generic.setdefault(stmt.generic, []).append(stmt)

    chart_date = _latest_date([s for s in stmts if s.source == "emr"])
    fused: list[FusedMed] = []
    for generic in sorted(by_generic):
        mine = by_generic[generic]
        states = evidence.get(generic, {})
        voters = _voting_statements(mine, chart_date)
        existence = _existence_votes(generic, voters, states, stmts, as_of)

        attributes: dict[str, FusedValue] = {}
        tallies: dict[str, dict[str, tuple[object, float, str]]] = {"existence": existence}
        present = {source for source, (value, _w, _r) in existence.items() if value == PRESENT}
        for attribute in FUSED_ATTRIBUTES:
            if attribute == "existence":
                continue
            tallies[attribute] = {}
            for source, stmt in voters.items():
                if source not in present:
                    continue
                value = _value_of(attribute, stmt)
                if value is None:
                    continue
                weight = trust.get((source, attribute), DEFAULT_TRUST) * _recency(
                    source, stmt.doc_date, as_of)
                tallies[attribute][source] = (value, weight, stmt.row_id)

        for attribute in FUSED_ATTRIBUTES:
            votes = tallies.get(attribute) or {}
            if attribute == "existence":
                votes = {src: (val, trust.get((src, "existence"), DEFAULT_TRUST) * w, rid)
                         for src, (val, w, rid) in votes.items()}
            resolved = _resolve(attribute, votes, margin)
            if resolved is not None:
                attributes[attribute] = resolved

        fused.append(FusedMed(
            generic=generic,
            atc=next((s.atc for s in mine if s.atc), None),
            per_source={src: states[src] for src in SOURCES if src in states},
            attributes=attributes,
            abstained=[a for a in FUSED_ATTRIBUTES if a in attributes and attributes[a].abstained],
            row_ids=sorted({s.row_id for s in mine}),
        ))
    return fused


def _latest_date(stmts: list[MedStatement]) -> date | None:
    dated = [s.doc_date for s in stmts if s.doc_date is not None]
    return max(dated) if dated else None


def _recency(source: str, doc_date: date | None, as_of: date) -> float:
    if doc_date is None:
        return 1.0
    age = max(0, (as_of - doc_date).days)
    return math.exp(-age / TAU_DAYS.get(source, 365.0))


def _voting_statements(mine: list[MedStatement], chart_date: date | None) -> dict[str, MedStatement]:
    """Each source's most recent statement of this medicine.

    For the EMR, only documents **older** than the current admission chart are
    eligible -- a prior discharge summary is history; the chart is what is being
    checked against history.
    """
    voters: dict[str, MedStatement] = {}
    for stmt in mine:
        if stmt.source == "emr" and (chart_date is None or stmt.doc_date == chart_date):
            continue
        held = voters.get(stmt.source)
        if held is None or (stmt.doc_date or date.min) > (held.doc_date or date.min):
            voters[stmt.source] = stmt
    return voters


def _existence_votes(
    generic: str,
    voters: dict[str, MedStatement],
    states: dict[str, EvidenceState],
    stmts: list[MedStatement],
    as_of: date,
) -> dict[str, tuple[object, float, str]]:
    """`source -> (present|absent, recency, row_id)`. Trust is applied by the caller."""
    votes: dict[str, tuple[object, float, str]] = {}
    for source in SOURCES:
        state = states.get(source, EvidenceState.UNKNOWN)
        if state is EvidenceState.UNKNOWN:
            continue
        if source == "pharmacy":
            fills = [s for s in stmts if s.source == "pharmacy" and s.generic == generic]
            if fills:
                status = supply_status(fills, as_of)
                latest = max(fills, key=lambda s: s.doc_date or date.min)
                votes[source] = (ABSENT if status == "POSSIBLY_CEASED" else PRESENT,
                                 1.0, latest.row_id)
                continue
        stmt = voters.get(source)
        if source == "emr":
            # The chart's presence is what `evidence` reports for the EMR, and
            # the chart does not vote. Only an older EMR document does: a
            # discharge "cease" counts against, a "start" for.
            if stmt is None:
                continue
            votes[source] = (ABSENT if stmt.status == "ceased" else PRESENT,
                             _recency(source, stmt.doc_date, as_of), stmt.row_id)
            continue
        value = PRESENT if state is EvidenceState.PRESENT else ABSENT
        row_id = stmt.row_id if stmt is not None else ""
        recency = _recency(source, stmt.doc_date, as_of) if stmt is not None else 1.0
        votes[source] = (value, recency, row_id)
    return votes


def _value_of(attribute: str, stmt: MedStatement) -> object:
    if attribute == "daily_dose":
        return round(stmt.daily_dose_mg, 4) if stmt.daily_dose_mg is not None else None
    if attribute == "frequency":
        if stmt.prn:
            return "prn"
        per_day, prn = parse_frequency(stmt.frequency)
        if prn:
            return "prn"
        return f"{per_day:g}/day" if per_day else None
    if attribute == "release":
        return stmt.release if stmt.release in ("IR", "MR") else None
    if attribute == "route":
        return stmt.route or None
    return None


def _resolve(attribute: str, votes: dict[str, tuple[object, float, str]],
             margin: float) -> FusedValue | None:
    """Turn one attribute's votes into a `FusedValue`, abstaining on a close call."""
    if not votes:
        return None
    scores: dict[object, float] = {}
    for value, weight, _row in votes.values():
        scores[value] = scores.get(value, 0.0) + weight
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
    top_value, top = ranked[0]
    second_value, second = ranked[1] if len(ranked) > 1 else (None, 0.0)
    share = (top - second) / (top + second) if second > 0 else 1.0
    abstained = second > 0 and share < margin

    winner = None if abstained else top_value
    return FusedValue(
        attribute=attribute,
        value=winner,  # type: ignore[arg-type]
        score=round(top, 4),
        runner_up=second_value,  # type: ignore[arg-type]
        runner_up_score=round(second, 4),
        margin=round(share, 4),
        abstained=abstained,
        supporting=sorted(src for src, (v, _w, _r) in votes.items()
                          if not abstained and v == top_value),
        # Every voter that is not behind the winner -- and, on an abstention,
        # every voter, so the grid shows both sides rather than a false winner.
        dissenting={src: str(v) for src, (v, _w, _r) in votes.items()
                    if abstained or v != top_value},
        row_ids=sorted({rid for _v, _w, rid in votes.values() if rid}),
    )
