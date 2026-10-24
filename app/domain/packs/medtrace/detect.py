"""Discrepancy detection (PLAN 2.6).

Deterministic and tested against `data/synthetic/ground_truth.json`. No model
call reaches this module: a finding a pharmacist acts on has to be reproducible,
and the agents' job is to plan, fetch, verify, rank and explain -- not to decide
what counts as a discrepancy.

The hardest requirement here is restraint. Every type in `DiscrepancyType` is a
real finding; `triage.SUPPRESS` lists the differences that are never findings.
An alert list padded with brand-vs-generic noise is worse than no list, because
the one that matters is the one scrolled past.
"""

from __future__ import annotations

from datetime import date

from app.domain.packs.medtrace.fuse import _irregular_anywhere
from app.domain.packs.medtrace.normalise import parse_frequency
from app.domain.packs.medtrace.safety import (
    DOSE_CHANGES_WITHOUT_A_SCRIPT,
    STEROID_TAPER_CLASS,
    STEROID_TAPER_PREFIX,
    forced_confirm,
    high_risk_class,
)
from app.domain.packs.medtrace.supply import supply_status
from app.domain.packs.medtrace.types import (
    Coverage,
    DiscrepancyCandidate,
    DiscrepancyType,
    EvidenceState,
    FusedMed,
    Lexicon,
    MedStatement,
)

#: Two daily doses closer than this, relatively, are the same dose. "2.5 mg"
#: written two ways must never become a dose discrepancy.
DOSE_TOLERANCE = 0.01

#: Base severity per type. Raised to "high" when the medicine is high-risk.
SEVERITY: dict[DiscrepancyType, str] = {
    DiscrepancyType.OMISSION: "medium",
    DiscrepancyType.COMMISSION: "medium",
    DiscrepancyType.DOSE: "medium",
    DiscrepancyType.FREQUENCY: "medium",
    DiscrepancyType.FORMULATION: "medium",
    DiscrepancyType.ROUTE: "medium",
    DiscrepancyType.DUPLICATION: "medium",
    DiscrepancyType.STALE_LISTING: "low",
    DiscrepancyType.DOSE_UNCONFIRMABLE: "high",
}

#: The task each type hands the pharmacist, before any forced confirmation.
TASKS: dict[DiscrepancyType, str] = {
    DiscrepancyType.OMISSION: "Confirm whether {g} should be charted",
    DiscrepancyType.COMMISSION: "Confirm the patient is still taking {g} before giving it",
    DiscrepancyType.DOSE: "Confirm the correct {g} dose",
    DiscrepancyType.FREQUENCY: "Confirm how often {g} is taken",
    DiscrepancyType.FORMULATION: "Confirm whether {g} is immediate or modified release",
    DiscrepancyType.ROUTE: "Confirm the route for {g}",
    DiscrepancyType.DUPLICATION: "Review {g}: it duplicates an ingredient of another medicine",
    DiscrepancyType.STALE_LISTING: "Ask the GP practice whether {g} is still current",
    DiscrepancyType.DOSE_UNCONFIRMABLE: "Confirm the current {g} dose",
}


def detect_discrepancies(
    fused: list[FusedMed],
    stmts: list[MedStatement],
    cov: dict[str, Coverage],
    as_of: date,
    lex: Lexicon,
) -> list[DiscrepancyCandidate]:
    """Produce every candidate finding, unranked, each citing its rows.

    The reference is the **BPMH** in `fused` -- pre-admission history, which
    the admission chart does not vote on (`fuse`). Each type below compares the
    chart against it, or reads the sources directly where the BPMH cannot say.

    - `omission` -- not on the chart (`ABSENT_IN_SCOPE`, never `UNKNOWN`), and
      the BPMH resolves present with the GP or pharmacy behind it. Something
      only the patient mentions is a `patient_only_item` notice, not an
      omission.
    - `commission` -- on the chart, and the BPMH resolves **absent**. When the
      BPMH is too close to call, this is a conflict to resolve, not a finding.
    - `dose` / `frequency` -- the chart's total daily dose differs from the
      resolved BPMH dose. Classified by what changed: the **same strength per
      unit at a different number of doses a day** is `frequency` (clopidogrel
      charted bd instead of daily); anything else is `dose`. An equal total
      daily dose is never a finding however it is split (brief 8, section 2).
      A charted PRN against a regular BPMH, or the reverse, is `frequency`.
    - `formulation` / `route` -- the chart and the resolved BPMH both state a
      release or a route, and they differ.
    - `stale_listing` -- the GP lists it active, the dispensed supply ran out
      more than 90 days ago, and the patient does not say they still take it.
      Never asserts cessation; it asks the GP. Not raised for a medicine that
      was itself dispensed privately, since it may have continued out of
      sight.
    - `duplication` -- a combination and another current medicine share an
      ingredient, **and one source asserts both at once**. That condition is
      what separates a real duplicate (Caduet and Lipitor on the same GP list)
      from the same therapy written two ways in two places, which brief 8
      section 4 says is never a finding.
    - `dose_unconfirmable` -- every current medicine whose dose changes without
      a new script (`safety.DOSE_CHANGES_WITHOUT_A_SCRIPT`). Agreement between
      sources that cannot see a phone instruction is not confirmation, so it is
      raised whether or not they visibly disagree, and severity is high either
      way (DATA_SPEC 9.5: "never auto-resolved to one source"). These medicines
      never also get a plain `dose` finding.

    **Not emitted yet, deliberately:**

    - `unpropagated_discharge_change` -- the synthetic prior discharge actions
      are drawn independently of what each source later shows, so a detector
      would mostly be flagging generator noise, and the type is not planted.
    - `identity_uncertain` -- rows from a `review`-band link are not read until
      a human confirms the link (`queries.q_meds_for`), so no finding can rest
      on one.
    - `route` fires only on stated routes; most pharmacy rows state a dosage
      form, which `normalise` maps to a route only when it implies one.

    `intent_status` is `documented_intentional` when the chart line carries a
    note ("withheld: AKI"). Such items stay in the list, collapsed -- a
    documented reason can still be a mistake.

    Every candidate carries the `row_ids` it came from. `safety.safety_gate`
    blocks any that cannot, because an unciteable finding is indistinguishable
    from an invented one. Output order is deterministic: by generic, then type.
    """
    chart_date = max((s.doc_date for s in stmts if s.source == "emr" and s.doc_date),
                     default=None)
    by_source: dict[tuple[str, str], list[MedStatement]] = {}
    for stmt in stmts:
        if stmt.generic:
            by_source.setdefault((stmt.source, stmt.generic), []).append(stmt)

    def chart_rows(generic: str) -> list[MedStatement]:
        return [s for s in by_source.get(("emr", generic), [])
                if chart_date is None or s.doc_date == chart_date]

    found: list[DiscrepancyCandidate] = []

    def emit(kind: DiscrepancyType, med: FusedMed, sources: list[str], rows: list[str],
             detail: dict, intent: str = "likely_unintentional") -> None:
        rows = list(dict.fromkeys(r for r in rows if r))
        if not rows:
            return
        risk = high_risk_class(med.atc, lex)
        if (kind is DiscrepancyType.DOSE_UNCONFIRMABLE and risk is None
                and (med.atc or "").startswith(STEROID_TAPER_PREFIX)):
            risk = STEROID_TAPER_CLASS
        severity = SEVERITY[kind]
        if risk is not None and kind is not DiscrepancyType.STALE_LISTING:
            severity = "high"
        tasks = [TASKS[kind].format(g=med.generic)]
        forced = forced_confirm(med.generic, med.atc)
        if forced and forced not in tasks:
            tasks.append(forced)
        found.append(DiscrepancyCandidate(
            id=f"{kind.value}:{med.generic}", type=kind, generic=med.generic,
            sources_involved=sorted(dict.fromkeys(sources)), row_ids=rows, detail=detail,
            high_risk_class=risk, severity=severity,  # type: ignore[arg-type]
            intent_status=intent,  # type: ignore[arg-type]
            tasks=tasks,
        ))

    def rows_of(source: str, generic: str) -> list[str]:
        if source == "emr":
            return [s.row_id for s in chart_rows(generic)] or [
                s.row_id for s in by_source.get(("emr", generic), [])]
        return [s.row_id for s in by_source.get((source, generic), [])]

    for med in sorted(fused, key=lambda m: m.generic):
        g = med.generic
        on_chart = med.per_source.get("emr") is EvidenceState.PRESENT
        charted = chart_rows(g)
        existence = med.attributes.get("existence")
        present_now = (None if existence is None or existence.abstained
                       else existence.value == "present")
        noted = next((c.note_text for c in charted if c.note_text), None)
        intent = "documented_intentional" if noted else "likely_unintentional"

        # -- dose_unconfirmable: the dose cannot be confirmed, by construction
        if g in DOSE_CHANGES_WITHOUT_A_SCRIPT and (present_now or (on_chart and present_now is not False)):
            sources = [s for s in ("gp", "pharmacy", "patient", "emr") if rows_of(s, g)]
            doses = sorted({str(s.daily_dose_mg) for src in sources
                            for s in by_source.get((src, g), []) if s.daily_dose_mg})
            emit(DiscrepancyType.DOSE_UNCONFIRMABLE, med, sources,
                 [r for src in sources for r in rows_of(src, g)],
                 {"mechanism": "dose changes without a new script",
                  "doses_seen": doses, "sources_disagree": len(doses) > 1},
                 "possibly_intentional")

        # -- omission
        if (not on_chart and med.per_source.get("emr") is EvidenceState.ABSENT_IN_SCOPE
                and present_now and existence is not None):
            # Not on a GP listing alone: GP summaries keep about 30% of stopped
            # medicines as active (Elliott 2023; DATA_SPEC 8), so a listing with
            # nothing behind it -- no current supply, no patient saying yes -- is
            # a stale-listing question, not an omission.
            backers = [s for s in existence.supporting if s in ("gp", "pharmacy", "emr")]
            if backers == ["gp"] and "patient" not in existence.supporting:
                backers = []
            if backers:
                support = [s for s in existence.supporting]
                emit(DiscrepancyType.OMISSION, med, support,
                     [r for src in support for r in rows_of(src, g)],
                     {"reason": "supported before admission, not on the admission chart",
                      "supported_by": support})

        # -- commission: needs someone to have SAID it stopped
        if charted and present_now is False and existence is not None:
            against = [src for src in existence.supporting
                       if _asserts_stopped(src, g, by_source, stmts, as_of)]
        else:
            against = []
        if against:
            emit(DiscrepancyType.COMMISSION, med, ["emr"] + against,
                 [c.row_id for c in charted] + [r for src in against for r in rows_of(src, g)],
                 {"reason": "on the admission chart, but not current before admission",
                  "contradicted_by": against})

        # -- dose / frequency / formulation / route: chart against the BPMH
        if charted and present_now is not False and g not in DOSE_CHANGES_WITHOUT_A_SCRIPT:
            _compare_chart(med, charted[0], by_source, emit, intent, rows_of)

        # -- stale_listing
        gp_active = [s for s in by_source.get(("gp", g), []) if s.status == "active"]
        fills = by_source.get(("pharmacy", g), [])
        patient_says_yes = any(s.status == "active" for s in by_source.get(("patient", g), []))
        # Private scripts carry no PBS code, so a medicine that has been
        # dispensed privately may have carried on out of sight. That is a
        # reason to doubt THIS medicine's lapse -- not every medicine's. It
        # used to be applied to the whole record whenever any one item was
        # private, which hid real stale listings.
        private_here = any((f.script_type or "").casefold() == "private" for f in fills)
        if (gp_active and fills and not private_here and not patient_says_yes
                and not _irregular_anywhere(g, stmts)
                and supply_status(fills, as_of) == "POSSIBLY_CEASED"):
            last = max(fills, key=lambda s: s.doc_date or date.min)
            emit(DiscrepancyType.STALE_LISTING, med, ["gp", "pharmacy"],
                 [s.row_id for s in gp_active] + [last.row_id],
                 {"last_dispensed": last.doc_date.isoformat() if last.doc_date else None})

    found.extend(_duplications(fused, by_source, chart_rows, as_of, lex, emit_into=[]))
    return _dedupe(found)


def _asserts_stopped(source: str, generic: str, by_source, stmts, as_of: date) -> bool:
    """Did this source positively say the medicine stopped, rather than just not
    mention it? A ceased listing, a patient's "no", a discharge "cease", or a
    regular supply that ran out. Silence alone never makes a commission."""
    own = by_source.get((source, generic), [])
    if source == "pharmacy":
        return bool(own) and not _irregular_anywhere(generic, stmts) and \
            supply_status(own, as_of) == "POSSIBLY_CEASED"
    return any(s.status == "ceased" for s in own)


def _per_day(stmt: MedStatement) -> float | None:
    """Doses a day from the written direction, or -- for a dispensing, which has
    no directions -- from quantity over days supplied."""
    per_day, prn = parse_frequency(stmt.frequency)
    if per_day:
        return per_day
    if stmt.source == "pharmacy" and stmt.qty and stmt.days_supply:
        return stmt.qty / stmt.days_supply
    return None


def _differ(a: float, b: float) -> bool:
    return abs(a - b) > DOSE_TOLERANCE * max(abs(a), abs(b), 1e-9)


def _compare_chart(med, chart, by_source, emit, intent, rows_of) -> None:
    """Chart line versus the resolved BPMH, for dose, frequency, release, route."""
    g = med.generic

    def backed(attribute: str):
        value = med.attributes.get(attribute)
        if value is None or value.abstained or value.value is None:
            return None, []
        return value.value, list(value.supporting)

    ref_dose, dose_backers = backed("daily_dose")
    ref_freq, freq_backers = backed("frequency")
    chart_prn = chart.prn or parse_frequency(chart.frequency)[1]

    if ref_freq is not None and (chart_prn != (ref_freq == "prn")):
        emit(DiscrepancyType.FREQUENCY, med, ["emr"] + freq_backers,
             [chart.row_id] + [r for s in freq_backers for r in rows_of(s, g)],
             {"charted": chart.frequency, "bpmh": ref_freq, "why": "PRN against regular"},
             intent)
    elif (ref_dose is not None and chart.daily_dose_mg
          and _differ(float(chart.daily_dose_mg), float(ref_dose))):
        chart_per_day = _per_day(chart)
        ref_stmt = next((s for src in ("gp", "patient", "pharmacy", "emr") if src in dose_backers
                         for s in by_source.get((src, g), []) if s.daily_dose_mg), None)
        ref_per_day = _per_day(ref_stmt) if ref_stmt is not None else None
        kind = DiscrepancyType.DOSE
        if chart_per_day and ref_per_day and _differ(chart_per_day, ref_per_day):
            chart_unit = float(chart.daily_dose_mg) / chart_per_day
            ref_unit = float(ref_dose) / ref_per_day
            if not _differ(chart_unit, ref_unit):
                kind = DiscrepancyType.FREQUENCY
        emit(kind, med, ["emr"] + dose_backers,
             [chart.row_id] + [r for s in dose_backers for r in rows_of(s, g)],
             {"charted_daily_mg": chart.daily_dose_mg, "bpmh_daily_mg": ref_dose,
              "charted_frequency": chart.frequency}, intent)
    elif ref_dose is None and ref_freq not in (None, "prn") and not chart_prn:
        # No dose to compare (strength unstated on both sides): fall back to the
        # number of doses a day.
        chart_per_day = _per_day(chart)
        ref_per_day = float(str(ref_freq).split("/")[0])
        if chart_per_day and _differ(chart_per_day, ref_per_day):
            emit(DiscrepancyType.FREQUENCY, med, ["emr"] + freq_backers,
                 [chart.row_id] + [r for s in freq_backers for r in rows_of(s, g)],
                 {"charted": chart.frequency, "bpmh": ref_freq}, intent)

    ref_release, release_backers = backed("release")
    if ref_release and chart.release in ("IR", "MR") and chart.release != ref_release:
        emit(DiscrepancyType.FORMULATION, med, ["emr"] + release_backers,
             [chart.row_id] + [r for s in release_backers for r in rows_of(s, g)],
             {"charted": chart.release, "bpmh": ref_release}, intent)

    ref_route, route_backers = backed("route")
    if ref_route and chart.route and chart.route != ref_route:
        emit(DiscrepancyType.ROUTE, med, ["emr"] + route_backers,
             [chart.row_id] + [r for s in route_backers for r in rows_of(s, g)],
             {"charted": chart.route, "bpmh": ref_route}, intent)


def _duplications(fused, by_source, chart_rows, as_of, lex, emit_into) -> list[DiscrepancyCandidate]:
    """A combination and another current medicine sharing an ingredient, both
    asserted as current by the same source."""
    def current_in(source: str, generic: str) -> list[MedStatement]:
        if source == "emr":
            return chart_rows(generic)
        own = by_source.get((source, generic), [])
        if source == "pharmacy":
            return own if own and supply_status(own, as_of) == "ACTIVE_BY_SUPPLY" else []
        if source == "gp":
            # A GP line for a medicine whose supply has lapsed is a stale listing,
            # not a second current product to duplicate against.
            fills = by_source.get(("pharmacy", generic), [])
            if fills and supply_status(fills, as_of) == "POSSIBLY_CEASED":
                return []
        return [s for s in own if s.status != "ceased"]

    ingredients: dict[str, set[str]] = {}
    for (_source, generic), stmts in by_source.items():
        for stmt in stmts:
            names = {n for n, _mg in stmt.ingredients if n} or {generic}
            ingredients.setdefault(generic, set()).update(names)

    meds = {m.generic: m for m in fused}
    out: list[DiscrepancyCandidate] = []
    for g in sorted(meds):
        mine = ingredients.get(g, set())
        if len(mine) < 2:
            continue
        for h in sorted(meds):
            if h == g or not (mine & ingredients.get(h, set())):
                continue
            for source in ("gp", "emr", "pharmacy", "patient"):
                both_g, both_h = current_in(source, g), current_in(source, h)
                if both_g and both_h:
                    med = meds[g]
                    out.append(DiscrepancyCandidate(
                        id=f"duplication:{g}", type=DiscrepancyType.DUPLICATION, generic=g,
                        sources_involved=[source],
                        row_ids=[s.row_id for s in both_g] + [s.row_id for s in both_h],
                        detail={"overlaps_with": h, "shared": sorted(mine & ingredients[h]),
                                "listed_together_in": source},
                        high_risk_class=high_risk_class(med.atc, lex),
                        severity="high" if high_risk_class(med.atc, lex) else "medium",
                        tasks=[TASKS[DiscrepancyType.DUPLICATION].format(g=g)],
                    ))
                    break
            else:
                continue
            break
    return out


def _dedupe(found: list[DiscrepancyCandidate]) -> list[DiscrepancyCandidate]:
    """One candidate per (type, generic), in a deterministic order."""
    seen: dict[str, DiscrepancyCandidate] = {}
    for cand in found:
        seen.setdefault(cand.id, cand)
    return sorted(seen.values(), key=lambda c: (c.generic, c.type.value))
