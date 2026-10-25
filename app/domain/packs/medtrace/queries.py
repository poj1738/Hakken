"""The vetted Lightning SQL templates (PLAN 2.4). Real SQL, not a skeleton.

Agents **pick from these templates**; free SQL is a budgeted fallback
(`PLAN` 0). Every function returns exactly one statement with no trailing
semicolon, because that is what the REST endpoint accepts
(`REFERENCE_NOTES` 1.2), and every value escaped **with a backslash, not a
doubled quote** -- see `sql_literal`, where the doubled form was measured to
silently delete the apostrophe rather than escape it.

**The governing rule of this module: no `DISTINCT`, no window functions, no
`JOIN`s and no subqueries.** Three separate findings forced that, and each one
was a live measurement rather than a guess:

- A 2-table `JOIN` with `GROUP BY` over the sample tables **timed out once, then
  took 91.2 s** (`docs/DECISIONS.md`, 24 Oct). Joins are pre-computed in the
  registered views instead. (That join scanned ~11 MB of multipolygon geometry;
  latency tracks **bytes scanned**, ~1 s + 2-3 s/MB, so at our data size a query
  is 1-3 s. See the 24 Oct correction. The rule stands on point 2 below
  regardless: the union view cannot be referenced twice at all.)
- Referencing the same `UNION ALL`-of-`explode()` view twice in one query fails
  with `MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION`
  (`REFERENCE_NOTES` 1.2). `medtrace.all_sources` is exactly that shape.
- Whether `DISTINCT` survives a union-of-explode views is **unproven** on our
  catalogue (PLAN 2.1 lists it as a spike).

So these templates do one flat scan each and **deduplicate in Python**, where it
is tested and costs nothing. Returning 60 rows instead of 8 is free; a second
query is 4-91 s. That is a deliberate trade and it refines PLAN 2.4, which
assumed one record per row for Q0 and Q1.

Per-source views (`medtrace.emr`, `medtrace.gp`, ...) already expose the
harmonised columns of PLAN 2.3, and `medtrace.all_sources` is a plain
`UNION ALL` over them. That ordering matters: it is what makes PLAN 2.1's
fallback ("if the union view fails, query the 4 views separately") a one-line
change rather than a rewrite.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.domain.packs.medtrace.types import IdentityLink, SourceRow

# --------------------------------------------------------------------------- #
# Catalogue (PLAN 2.1)
# --------------------------------------------------------------------------- #

CONTAINER = "medtrace"

#: source -> its harmonised per-source view.
SOURCE_VIEWS: dict[str, str] = {
    "emr": "medtrace.emr",
    "gp": "medtrace.gp",
    "pharmacy": "medtrace.pharmacy",
    "patient": "medtrace.patient_report",
}

ALL_SOURCES_VIEW = "medtrace.all_sources"

#: Q4's view (PLAN 2.1) over `scripts/load_tga_shortages.py`'s output. Registered
#: only with `register_sources.py --with-tga`, which is off until the TGA licence
#: is recorded in `docs/DATA_LICENCES.md`.
TGA_VIEW = "medtrace.tga_shortages"

#: The columns of `TGA_VIEW`, exactly as the loader writes them. `ingredients` is
#: the export's active ingredients as salt names, sorted and joined with `|`.
TGA_COLUMNS: tuple[str, ...] = (
    "artg_id", "medicine_name", "sponsor", "ingredients", "salt_quantity", "dosage_form",
    "status", "shortage_start", "expected_resolution", "impact_rating", "availability",
    "reason",
)

#: Only these statuses mean a pharmacist might care now (the loader's docstring).
TGA_NOTIFIABLE_STATUSES = ("Current", "Anticipated")

#: Q_REF name -> its reference view.
REFERENCE_VIEWS: dict[str, str] = {
    "lexicon": "medtrace.med_lexicon",
    "apinchs": "medtrace.apinchs",
    "nicknames": "medtrace.nicknames",
}

#: Every harmonised column, in the order the views declare them (PLAN 2.3).
HARMONISED_COLUMNS: tuple[str, ...] = (
    "source",
    "row_id",
    "source_patient_id",
    "ihi_syn",
    "name_given",
    "name_family",
    "name_previous",
    "dob_text",
    "sex",
    "postcode",
    "record_kind",
    "doc_date",
    "med_text",
    "med_code",
    "code_system",
    "strength_text",
    "dose_text",
    "route_text",
    "freq_text",
    "status_text",
    "note_text",
    "qty",
    "days_supply",
    "pharmacy_id",
    "script_type",
)

#: The identity subset. Q0 and Q1 never need medication columns.
#: Measured caveat: a narrow projection on an 11 MB table took 15.3 s against
#: 17.0 s for a full count, so trimming columns saves the **payload**, not the
#: scan (`docs/DECISIONS.md`, 24 Oct correction). Generating less data is the
#: lever; this is tidiness and transfer size.
IDENTITY_COLUMNS: tuple[str, ...] = (
    "source",
    "row_id",
    "source_patient_id",
    "ihi_syn",
    "name_given",
    "name_family",
    "name_previous",
    "dob_text",
    "sex",
    "postcode",
    "record_kind",
    "doc_date",
)

#: Template id -> the function that builds it. Goes into `Evidence.sql_template_id`
#: and every `TraceEvent`, so a judge can tie a number on screen to a template.
TEMPLATE_IDS: tuple[str, ...] = ("Q_REF", "Q0", "Q1", "Q2", "Q3", "Q4")

#: PLAN 2.4. Q1 + Q2 (<=2) + Q3 (<=2) + Q4 + one free-SQL step.
MAX_ZETARIS_QUERIES_PER_RUN = 8

#: How many rows a template may ask for. Well above any real result, and present
#: only because the REST body requires a `limit` (`REFERENCE_NOTES` 1.1).
DEFAULT_ROW_LIMIT = 10_000

_RECORD_KEY = re.compile(r"^(emr|gp|pharmacy|patient):([A-Za-z0-9_\-]{1,64})$")
_ROW_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_YEAR = re.compile(r"(?:19|20)\d{2}")


class QueryBuildError(ValueError):
    """A template was asked to embed something it refuses to embed.

    Raised instead of quietly sanitising. A value that needs sanitising is a bug
    upstream -- most likely an unvalidated string from a free-text silo reaching
    SQL -- and silently stripping it would hide that.
    """


# --------------------------------------------------------------------------- #
# Literals
# --------------------------------------------------------------------------- #


def sql_literal(value: str | int | float | None) -> str:
    """Render one value as a Lightning SQL literal.

    `None` becomes `NULL`; numbers are rendered bare; strings are single-quoted
    with **backslash escaping**: a backslash is doubled, then `'` becomes `\'`.

    **The standard SQL doubled quote is wrong in this dialect, and it fails
    silently.** Measured `[live -- Arpon's machine, 24 Oct]`:

        SELECT 'O''Brien'      ->  OBrien       (length 6, not 7)
        SELECT 'AB' 'CD'       ->  ABCD
        SELECT 'O\'Brien'      ->  O'Brien      (correct)

    `''` is not an escaped apostrophe here -- it closes one literal and opens
    another, and **adjacent literals concatenate**, so the apostrophe is deleted.
    Quotes stay balanced, nothing raises, and the value is quietly corrupted. On
    this instance `WHERE zone LIKE '%''%'` matched **789 of 789** rows, because
    the pattern had collapsed to `%%`; the backslash form matched the true 12.

    For MedTrace that is a patient-safety bug rather than a cosmetic one.
    `O'Brien` would reach Zetaris as `OBrien`, match nothing, and the pharmacist
    would be told "GP: no record found" for a record that exists -- a fabricated
    coverage gap, caused by a surname that is ordinary in Australia.

    Backslash escaping was verified to round-trip every value these templates
    embed, and hostile input (`x' OR 1=1 --`) comes back as an inert string.

    Semicolons and control characters are still **refused rather than escaped**.
    These templates only ever embed identifiers, codes, dates and names, never
    free text from a silo, so refusing costs nothing real and keeps
    `_one_statement`'s blanket semicolon check sound.

    Raises:
        QueryBuildError: on a semicolon, a control character, or a value longer
            than 256 characters.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):  # bool is an int subclass; catch it first.
        raise QueryBuildError("booleans have no literal form in these templates")
    if isinstance(value, (int, float)):
        return repr(value)
    if not isinstance(value, str):
        raise QueryBuildError(f"cannot render {type(value).__name__} as a SQL literal")
    if len(value) > 256:
        raise QueryBuildError(f"literal too long ({len(value)} chars); this is not real data")
    if ";" in value:
        raise QueryBuildError(f"refusing to embed a semicolon: {value!r}")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise QueryBuildError(f"refusing to embed a control character: {value!r}")
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _in_list(values: list[str]) -> str:
    return ", ".join(sql_literal(v) for v in values)


def _one_statement(sql: str) -> str:
    """Collapse whitespace and assert the shape the REST endpoint requires."""
    collapsed = " ".join(sql.split())
    if ";" in collapsed:
        raise QueryBuildError("one statement per call, no trailing semicolon")
    return collapsed


# --------------------------------------------------------------------------- #
# Identity blocking helpers
# --------------------------------------------------------------------------- #


def _parse_dob(text: str) -> date | None:
    """Parse the two formats our silos emit (PLAN 2.2): ISO and `DD/MM/YYYY`."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def dob_match_literals(dob_text: str | None) -> list[str]:
    """Every spelling of a date of birth that Q1 should block on.

    Covers two of the planted corruptions at once (PLAN 4.4): sources store the
    same birthday in different formats, and the patient-report silo swaps day and
    month. Comparing `dob_text` as a string means both have to be enumerated
    here, as literals, rather than parsed in SQL -- which also keeps the template
    free of date functions whose Lightning behaviour we have not verified.

    The swap is only emitted when it is a real date: swapping 03/07 gives 07/03,
    but 25/07 has no swap because there is no month 25.
    """
    text = (dob_text or "").strip()
    if not text:
        return []
    out = {text}
    parsed = _parse_dob(text)
    if parsed is not None:
        out.add(parsed.isoformat())
        out.add(parsed.strftime("%d/%m/%Y"))
        if parsed.day <= 12 and parsed.day != parsed.month:
            try:
                swapped = date(parsed.year, parsed.day, parsed.month)
            except ValueError:
                pass
            else:
                out.add(swapped.isoformat())
                out.add(swapped.strftime("%d/%m/%Y"))
    return sorted(out)


def _birth_year(dob_text: str | None) -> str | None:
    text = (dob_text or "").strip()
    if not text:
        return None
    parsed = _parse_dob(text)
    if parsed is not None:
        return str(parsed.year)
    found = _YEAR.search(text)
    return found.group(0) if found else None


def _name_prefix(name: str | None, length: int = 4) -> str | None:
    """Uppercase prefix of a surname, for the year+name block in Q1.

    The prefix is compared with `LIKE` against the **unmodified** column, so it
    must keep the characters a surname really contains: `O'Brien` has to yield
    `O'BR`, not `OBRI`, or the predicate never matches `O'BRIEN` and every
    apostrophe and hyphen surname silently drops out of the candidate set.

    Scanning stops at the first character outside `A-Z ' - space`, which also
    trims a trailing `,` in a combined `"SMITH, Margaret"` field. `%` and `_`
    can therefore never reach the `LIKE` pattern as wildcards.
    """
    text = (name or "").strip().upper()
    prefix: list[str] = []
    for char in text:
        if not (char.isalpha() or char in "'- "):
            break
        prefix.append(char)
        if len(prefix) == length:
            break
    return "".join(prefix) or None


# --------------------------------------------------------------------------- #
# Q_REF -- reference data, read once at startup
# --------------------------------------------------------------------------- #


def q_reference(name: str) -> str:
    """Q_REF: one reference view, read once per process and cached in `Lexicon`.

    Three calls at startup (lexicon, apinchs, nicknames). Columns are listed
    explicitly rather than `SELECT *` because `parse.build_lexicon` depends on
    them, so this list doubles as the output contract for
    `scripts/build_lexicon.py`.

    Args:
        name: one of `lexicon`, `apinchs`, `nicknames`.

    Raises:
        QueryBuildError: on any other name.
    """
    columns: dict[str, tuple[str, ...]] = {
        "lexicon": (
            "pbs_code",
            "brand",
            "generic",
            "amt_mp",
            "amt_mpp",
            "amt_tpp",
            "atc_primary",
            "strength",
            "form",
            "release",
            "pack_qty",
            "repeats",
            "is_combination",
            "ingredients",
            "dos_weight",
        ),
        "apinchs": ("atc_prefix", "apinchs_class", "label"),
        "nicknames": ("canonical", "variant", "sex"),
    }
    if name not in REFERENCE_VIEWS:
        raise QueryBuildError(f"unknown reference view {name!r}; expected one of {sorted(REFERENCE_VIEWS)}")
    return _one_statement(f"SELECT {', '.join(columns[name])} FROM {REFERENCE_VIEWS[name]}")


# --------------------------------------------------------------------------- #
# Q0 -- the patient picker
# --------------------------------------------------------------------------- #


def q_admissions() -> str:
    """Q0: the admitted-patient list for the UI picker, from the EMR view.

    One row per admission-chart *line*, so the same patient repeats once per
    charted medicine. Deduplicate on `source_patient_id` in Python -- see the
    module docstring for why there is no `DISTINCT` here.
    """
    return _one_statement(
        f"SELECT {', '.join(IDENTITY_COLUMNS)} FROM {SOURCE_VIEWS['emr']} "
        "WHERE record_kind = 'admission_chart'"
    )


# --------------------------------------------------------------------------- #
# Q1 -- identity blocking
# --------------------------------------------------------------------------- #


def q_identity_candidates(anchor: SourceRow) -> str:
    """Q1: every row across all four sources that could be the same person.

    This is the one federated query in the demo, and the blocking predicate is
    what decides whether the planted corruptions are findable at all. A record
    is a candidate when **any** of these holds (PLAN 2.4):

    - the same `ihi_syn` (and the anchor has one);
    - the same date of birth in **any** spelling, including the day/month swap
      (`dob_match_literals`);
    - the same birth year **and** a matching surname prefix, against the current
      surname, the previous surname, or the start of `name_given` -- the
      pharmacy silo stores `"SMITH, Margaret"` in one field (PLAN 2.3), so its
      surname lives at the front of the given-name column.

    Recall is the whole job here: a record that does not come back cannot be
    linked, scored or shown as a near-miss, and the pharmacist is never told it
    existed. Precision costs nothing, because `identity.score_pair` re-scores
    every candidate properly.

    The anchor's own rows come back too. That is intentional: `coverage` needs
    them, and excluding them would cost a second query.
    """
    clauses: list[str] = []

    if anchor.ihi_syn:
        clauses.append(f"ihi_syn = {sql_literal(anchor.ihi_syn)}")

    dobs = dob_match_literals(anchor.dob_raw or (anchor.dob.isoformat() if anchor.dob else None))
    if dobs:
        clauses.append(f"dob_text IN ({_in_list(dobs)})")

    year = _birth_year(anchor.dob_raw or (anchor.dob.isoformat() if anchor.dob else None))
    prefix = _name_prefix(anchor.name_family) or _name_prefix(anchor.name_given)
    if year and prefix:
        like = sql_literal(f"{prefix}%")
        clauses.append(
            f"(dob_text LIKE {sql_literal('%' + year + '%')} AND ("
            f"UPPER(name_family) LIKE {like} "
            f"OR UPPER(name_previous) LIKE {like} "
            f"OR UPPER(name_given) LIKE {like}))"
        )

    # Always keep the anchor's own record, even for a row with no name and no DOB.
    clauses.append(
        f"(source = {sql_literal(anchor.source)} "
        f"AND source_patient_id = {sql_literal(anchor.source_patient_id)})"
    )

    return _one_statement(
        f"SELECT {', '.join(IDENTITY_COLUMNS)} FROM {ALL_SOURCES_VIEW} "
        f"WHERE {' OR '.join(clauses)}"
    )


# --------------------------------------------------------------------------- #
# Q2 -- the medication rows
# --------------------------------------------------------------------------- #


def q_meds_for(links: list[IdentityLink]) -> str:
    """Q2: every row for the records we have decided belong to this patient.

    Takes `IdentityLink`s and reads both ends of each one, so the anchor's own
    rows arrive in the same query. **This function trusts its input**: filtering
    by band is the orchestrator's decision, not the template's, because a
    `review`-band link is included only after a human says so
    (`POST /run/{id}/identity`).

    Called at most twice per run -- once on the auto-merge set, and again only if
    a human resolves a near-miss (PLAN 2.4).

    Raises:
        QueryBuildError: on an empty list, or a record key that is not
            `<source>:<id>`. An empty `IN` list is a silently empty result, which
            would read as "this patient has no medicines".
    """
    keys: list[str] = []
    for link in links:
        for key in (link.anchor_id, link.candidate_id):
            if key not in keys:
                keys.append(key)
    if not keys:
        raise QueryBuildError("q_meds_for needs at least one link; an empty IN list reads as 'no medicines'")

    clauses: list[str] = []
    for key in keys:
        match = _RECORD_KEY.match(key)
        if match is None:
            raise QueryBuildError(f"not a record key: {key!r}; expected '<source>:<id>'")
        source, patient_id = match.groups()
        clauses.append(
            f"(source = {sql_literal(source)} AND source_patient_id = {sql_literal(patient_id)})"
        )

    return _one_statement(
        f"SELECT {', '.join(HARMONISED_COLUMNS)} FROM {ALL_SOURCES_VIEW} "
        f"WHERE {' OR '.join(clauses)}"
    )


# --------------------------------------------------------------------------- #
# Q3 -- verification
# --------------------------------------------------------------------------- #


def q_verify_rows(row_ids: list[str]) -> str:
    """Q3: re-fetch every row the draft cites, in **one** query.

    The Evaluator re-derives every number, date and status from this result
    rather than trusting what an earlier step put in memory. One query for all
    cited rows is not an optimisation -- at 4-91 s each, one query per claim is
    the difference between a 2-minute run and a timeout
    (`docs/DECISIONS.md`, 24 Oct).

    Raises:
        QueryBuildError: on an empty list, or a `row_id` outside
            `[A-Za-z0-9_-]{1,64}`.
    """
    unique = list(dict.fromkeys(row_ids))
    if not unique:
        raise QueryBuildError("q_verify_rows needs at least one row_id; nothing to verify is a bug, not a query")
    for row_id in unique:
        if not _ROW_ID.match(row_id):
            raise QueryBuildError(f"not a row_id: {row_id!r}")
    return _one_statement(
        f"SELECT {', '.join(HARMONISED_COLUMNS)} FROM {ALL_SOURCES_VIEW} "
        f"WHERE row_id IN ({_in_list(unique)})"
    )


# --------------------------------------------------------------------------- #
# Q4 -- the TGA overlay (optional, Monday)
# --------------------------------------------------------------------------- #


def q_shortages(generics: list[str]) -> str:
    """Q4: known TGA shortages for the drafted medicines. Optional overlay.

    Returns the `Current` and `Anticipated` reports whose active ingredients are
    **exactly** one of `generics`, with a computed `generic` column naming which,
    so the caller can attach each row to a grid line without matching again.

    **Exactly** is the point. The export lists salts ("amlodipine besilate"), so a
    single-ingredient medicine matches by prefix -- but only a report with one
    ingredient. A shortage of Caduet (amlodipine + atorvastatin) says nothing
    about plain amlodipine, and calling it one would send a pharmacist hunting
    for a substitute the patient does not need. A combination such as
    `perindopril/amlodipine` matches only a report with exactly those
    ingredients, in any order. The count is checked by `|` separators, so the
    SQL needs nothing beyond `LIKE`, `lower` and `CASE`.

    **The shortage database is incomplete, so it is never ground truth.** A row
    here becomes `NoticeType.KNOWN_SHORTAGE` -- "known shortage" -- never
    "unavailable", and a medicine absent from the result says nothing at all.
    `salt_quantity` is salt mass, not strength: never compare it with a dose.

    Raises:
        QueryBuildError: on an empty list. An empty result must mean "no known
            shortage", never "we asked about nothing".
    """
    wanted = list(dict.fromkeys(g.strip().casefold() for g in generics if g and g.strip()))
    if not wanted:
        raise QueryBuildError("q_shortages needs at least one generic")

    def exactly(generic: str) -> str:
        parts = [p.strip() for p in generic.split("/") if p.strip()]
        each = [
            f"(lower(ingredients) LIKE {sql_literal(p + '%')} "
            f"OR lower(ingredients) LIKE {sql_literal('%|' + p + '%')})"
            for p in parts
        ]
        separators = "%" + "|%" * (len(parts) - 1)
        count = (f"lower(ingredients) LIKE {sql_literal(separators)} AND "
                 if len(parts) > 1 else "")
        count += f"lower(ingredients) NOT LIKE {sql_literal(separators + '|%')}"
        return "(" + " AND ".join(each + [count]) + ")"

    conditions = {g: exactly(g) for g in wanted}
    case = " ".join(f"WHEN {cond} THEN {sql_literal(g)}" for g, cond in conditions.items())
    columns = ", ".join(c for c in TGA_COLUMNS if c != "sponsor")
    return _one_statement(
        f"SELECT CASE {case} END AS generic, {columns} FROM {TGA_VIEW} "
        f"WHERE status IN ({_in_list(list(TGA_NOTIFIABLE_STATUSES))}) "
        f"AND ({' OR '.join(conditions.values())})"
    )