"""What we found, what we did not, and what absence is allowed to mean.

Brief section 2; PLAN 2.5. This module exists because the dangerous failure of a
medication reconciliation tool is not a wrong number -- it is a confident blank.
If the GP system was never reached and the grid shows an empty cell, a reader
concludes the patient is not taking the medicine. `EvidenceState` makes that
unrepresentable: only `ABSENT_IN_SCOPE` counts against a medicine, and it
requires that we found the source *and* can see the slice of it that would have
listed the drug.
"""

from __future__ import annotations

from datetime import date

from app.domain.packs.medtrace.types import (
    SOURCES,
    Coverage,
    EvidenceState,
    IdentityLink,
    MedStatement,
    SourceRow,
)

#: A GP list older than this is called out as stale (`docs/DATA_SPEC.md` 6).
#: It does not make the source UNKNOWN -- a stale list is still evidence -- but
#: the pharmacist is told how old it is before being asked to trust it.
STALE_DOCUMENT_DAYS = 365

#: Scope notes are prose for the UI, but `evidence_state` has to read them, so
#: the ones that change its answer start with a stable marker. A note that does
#: not start with one of these is informational only.
SCOPE_DISPENSING_INCOMPLETE = "dispensing incomplete:"
SCOPE_STALE_DOCUMENT = "stale document:"
SCOPE_SINGLE_PHARMACY = "single pharmacy:"

_ID_FIELD = {"emr": "mrn", "gp": "gp_pid", "pharmacy": "cust_no", "patient": "intake_id"}


def _accepted(links: list[IdentityLink]) -> dict[str, tuple[str, str]]:
    """source -> (record_key, band) for the best link we have per source.

    `auto-merge` beats `review`; within a band the first link wins, because
    `link_identity` returns them highest-probability first.
    """
    best: dict[str, tuple[str, str]] = {}
    for link in links:
        for key in (link.anchor_id, link.candidate_id):
            if ":" not in key:
                continue
            source = key.split(":", 1)[0]
            if source not in SOURCES or link.band == "new":
                continue
            current = best.get(source)
            if current is None or (current[1] == "review" and link.band == "auto-merge"):
                best[source] = (key, link.band)
    return best


def coverage(links: list[IdentityLink], rows: list[SourceRow]) -> dict[str, Coverage]:
    """Report, per source, whether we found this patient and how completely.

    States:
      - `found` -- an accepted link and rows (or a deliberate "known here, no
        medicines" row, PLAN 2.2).
      - `near_miss_pending` -- a `review`-band link awaiting a human. Not
        `not_found`: we probably did find them, and saying "no GP record" would
        be wrong.
      - `not_found` -- no candidate cleared the floor.

    `scope_notes` carries the honest caveats that `evidence_state` then reads:
    "pharmacy_id P2 only", "GP list updated 14 months ago". Every source is
    present in the returned dict, including the ones we missed -- a missing key
    would read as a source we never had to consider.
    """
    best = _accepted(links)
    rows_by_source: dict[str, list[SourceRow]] = {s: [] for s in SOURCES}
    for row in rows:
        if row.source in rows_by_source:
            rows_by_source[row.source].append(row)

    out: dict[str, Coverage] = {}
    for source in SOURCES:
        link = best.get(source)
        source_rows = rows_by_source[source]
        if link and link[1] == "review":
            state = "near_miss_pending"
        elif link and source_rows:
            state = "found"
        elif source_rows:
            # Rows without an accepted link can only have come from the anchor
            # itself, which is by definition this patient.
            state = "found"
        else:
            state = "not_found"

        notes: list[str] = []
        doc_date: date | None = None
        if source_rows:
            dates = [r.doc_date for r in source_rows if r.doc_date]
            doc_date = max(dates) if dates else None

        if source == "pharmacy" and source_rows:
            pharmacies = sorted({r.pharmacy_id for r in source_rows if r.pharmacy_id})
            if len(pharmacies) == 1:
                notes.append(
                    f"{SCOPE_SINGLE_PHARMACY} only {pharmacies[0]} is visible; "
                    f"anything dispensed elsewhere is not in this record"
                )
            elif len(pharmacies) > 1:
                notes.append(f"{SCOPE_SINGLE_PHARMACY} {len(pharmacies)} pharmacies visible "
                             f"({', '.join(pharmacies)})")
            if any(r.script_type and r.script_type.casefold() == "private" for r in source_rows):
                notes.append(
                    f"{SCOPE_DISPENSING_INCOMPLETE} private scripts carry no PBS code, so a "
                    f"privately dispensed medicine may not be matchable by code"
                )

        if source == "gp" and doc_date is not None:
            age = (date.today() - doc_date).days
            if age > STALE_DOCUMENT_DAYS:
                notes.append(f"{SCOPE_STALE_DOCUMENT} GP list last updated {doc_date.isoformat()}, "
                             f"about {age // 30} months ago")

        if state == "near_miss_pending":
            notes.append("a near-miss identity match is awaiting confirmation; "
                         "nothing from this source counts against a medicine yet")

        out[source] = Coverage(
            source=source,  # type: ignore[arg-type]
            state=state,    # type: ignore[arg-type]
            scope_notes=notes,
            record_key=link[0] if link else None,
            doc_date=doc_date,
        )
    return out


def _key(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def _asserts(stmt: MedStatement, wanted: str) -> bool:
    """Does this statement mention `wanted`, as itself or as an ingredient?"""
    if _key(stmt.generic) == wanted:
        return True
    return any(_key(name) == wanted for name, _mg in stmt.ingredients)


def _current_episode(emr_stmts: list[MedStatement]) -> list[MedStatement]:
    """The EMR statements on the latest document -- the current admission chart.

    `MedStatement` carries no record kind, but the admission chart is dated the
    admission day and every older EMR document (a prior discharge summary) is
    dated earlier, so the latest date identifies the current episode.
    """
    dated = [s.doc_date for s in emr_stmts if s.doc_date is not None]
    if not dated:
        return emr_stmts
    latest = max(dated)
    return [s for s in emr_stmts if s.doc_date == latest]


def evidence_state(
    generic: str,
    source: str,
    cov: Coverage,
    stmts: list[MedStatement],
) -> EvidenceState:
    """What one source says about one medicine. The three-valued core.

    - `PRESENT` -- this source asserts it.
    - `ABSENT_IN_SCOPE` -- found, in scope, and not asserted. The only value that
      counts as evidence against the medicine.
    - `UNKNOWN` -- we cannot tell. Returned when the source is `not_found` or
      `near_miss_pending`, and also when the medicine **would not appear** in
      what we can see: a privately dispensed drug is invisible to a PBS-only
      view, and calling that "absent" would manufacture an omission.

    `stmts` may be the whole run's statements; this filters to `source` itself,
    so a caller cannot accidentally credit one source with another's evidence.

    Three refinements, each of which stopped a source being shown as supporting
    a medicine it was actually evidence against:

    - **A source that asserts the medicine as stopped counts against it.** A GP
      line with status `ceased`, a patient's "no", a discharge `cease` -- all of
      these were `PRESENT`, because the medicine was mentioned. They are now
      `ABSENT_IN_SCOPE`: the source was read, and it says not current.
    - **The EMR column is the current admission chart.** EMR rows also include
      older discharge summaries; only statements on the latest EMR document
      count, so a medicine started at a discharge in June and missing from
      today's chart reads as absent from the chart -- which is what an omission
      is.
    - **A combination is present where all its components are.** "Coversyl Plus"
      on the GP list and perindopril + indapamide charted separately is the
      same therapy (brief 8, section 4), not an omission of the combination.
    """
    wanted = _key(generic)
    own = [s for s in stmts if s.source == source]
    if source == "emr":
        own = _current_episode(own)

    matched = [s for s in own if _asserts(s, wanted)]
    if not matched and "/" in wanted:
        parts = [p for p in wanted.split("/") if p]
        if parts and all(any(_asserts(s, part) for s in own) for part in parts):
            matched = [s for s in own if any(_asserts(s, part) for part in parts)]
    if matched:
        if all(s.status == "ceased" for s in matched):
            return EvidenceState.ABSENT_IN_SCOPE
        return EvidenceState.PRESENT

    if cov.state != "found":
        return EvidenceState.UNKNOWN

    # Found, but the slice we can see would not necessarily contain it.
    if any(note.startswith(SCOPE_DISPENSING_INCOMPLETE) for note in cov.scope_notes):
        return EvidenceState.UNKNOWN

    return EvidenceState.ABSENT_IN_SCOPE


def bpmh_confirmable(cov: dict[str, Coverage]) -> tuple[bool, str]:
    """Whether a BPMH can be confirmed at all, and the banner if not.

    ACSQHC Standard 4 (Action 4.5) expects **at least two independent sources**.
    Below that the output is explicitly not a confirmable history, and the UI
    shows the banner instead of implying completeness. Returns
    `(confirmable, banner_text)` with an empty banner when confirmable.

    Independence matters: the EMR admission chart and a prior discharge summary
    from the same EMR are one source, not two -- which is why this counts the
    four systems and never the records inside one.
    """
    found = sorted(s for s in SOURCES if cov.get(s) and cov[s].state == "found")
    pending = sorted(s for s in SOURCES if cov.get(s) and cov[s].state == "near_miss_pending")
    if len(found) >= 2:
        return True, ""

    missing = sorted(set(SOURCES) - set(found) - set(pending))
    parts = [
        f"Only {len(found)} of {len(SOURCES)} sources found"
        f"{' (' + ', '.join(found) + ')' if found else ''}.",
        "ACSQHC Standard 4 expects at least two independent sources, so this is a draft "
        "medication history and is not confirmable.",
    ]
    if pending:
        parts.append(
            f"Awaiting an identity decision for: {', '.join(pending)} — confirming it may "
            f"make this confirmable."
        )
    if missing:
        parts.append(f"No record found in: {', '.join(missing)}.")
    return False, " ".join(parts)


def possible_second_pharmacy(
    stmts: list[MedStatement],
    cov: dict[str, Coverage],
    as_of: date,
) -> list[str]:
    """Signs that dispensing is split across a pharmacy we cannot see.

    10% of generated patients have exactly this (PLAN 4.4). Signals: a chronic
    medicine with no dispensing at all, gaps far longer than `days_supply`, or
    more than one `pharmacy_id` already visible. Returns task-shaped reasons for
    the notice; it never concludes that a medicine was stopped.
    """
    pharmacy_cov = cov.get("pharmacy")
    if pharmacy_cov is None or pharmacy_cov.state != "found":
        return []

    reasons: list[str] = []

    pharmacy_ids = {s.pharmacy_id for s in stmts if s.source == "pharmacy" and s.pharmacy_id}
    if len(pharmacy_ids) > 1:
        reasons.append(
            f"Dispensing already spans {len(pharmacy_ids)} pharmacies "
            f"({', '.join(sorted(pharmacy_ids))}), so there may be others we cannot see."
        )

    dispensed = {
        (s.generic or "").strip().casefold()
        for s in stmts if s.source == "pharmacy" and s.generic
    }
    # A medicine another source calls current, with no dispensing at all.
    undispensed = sorted({
        s.generic for s in stmts
        if s.source in ("gp", "emr") and s.status == "active" and s.generic
        and (s.generic or "").strip().casefold() not in dispensed
    })
    if undispensed:
        shown = ", ".join(undispensed[:4]) + ("..." if len(undispensed) > 4 else "")
        reasons.append(
            f"{len(undispensed)} medicine(s) listed as current have no dispensing in this "
            f"pharmacy record ({shown}). That is also what a second pharmacy, a private "
            f"script or a sample pack looks like — it is not evidence of cessation."
        )

    if reasons:
        reasons.append("Ask the patient whether they use more than one pharmacy.")
    return reasons
