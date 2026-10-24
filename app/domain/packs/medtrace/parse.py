"""Zetaris envelope -> typed rows. **The only place in the codebase that casts.**

Every value out of Zetaris is a string (`REFERENCE_NOTES` 1.2), and decimals can
arrive in exponent notation. Casting in one tested module instead of at each use
site is what stops the Evaluator comparing `"2.5"` with `2.5` and reporting a
dose discrepancy that does not exist.

Dates are the delicate part. A row's `dob_text` is evidence about *how a source
spells a birthday*, so `SourceRow` keeps both the parsed `dob` and the original
`dob_raw`, and a value we cannot parse sets `dob` to `None` without discarding
anything or raising. An unparseable DOB is data about the silo, not a failure.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from app.domain.packs.medtrace.types import (
    Lexicon,
    LexiconEntry,
    SourceRow,
    SqlResult,
)

#: The date spellings our silos actually emit (`docs/DATA_SPEC.md` 2.1 to 2.4).
#: Order matters only for ambiguity, and there is none: ISO is unmistakable, and
#: the other two are day-first because every Australian source here is.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")

_INT = re.compile(r"^-?\d+$")


def normalise_text(value: str | None) -> str:
    """Casefold, strip accents, collapse whitespace. For lookup keys only.

    Never used on a value we store: `name_given` keeps its accents and its case
    because they are evidence. This exists so `"Atorvastatin Calcium "` and
    `"atorvastatin calcium"` reach the same lexicon entry.
    """
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).casefold()


def parse_date(value: str | None) -> date | None:
    """One of our silos' date spellings, or `None`.

    Returns `None` rather than raising, and rather than guessing. A birthday we
    cannot parse is a fact about that source's data quality -- the identity
    comparator still has `dob_raw` to work with, and discarding the row would
    lose a record the pharmacist needs to see.
    """
    text = (value or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value: str | None) -> int | None:
    """Cast an integer column. `"60"` -> 60; `""`, `None` and junk -> `None`.

    Also accepts `"60.0"`, because a numeric column can come back with a decimal
    point, and exponent notation for the same reason (`REFERENCE_NOTES` 1.2).
    """
    text = (value or "").strip()
    if not text:
        return None
    if _INT.match(text):
        return int(text)
    try:
        return int(float(text))
    except ValueError:
        return None


def dicts_from_sql(result: SqlResult) -> list[dict[str, str]]:
    """Zip `headers` with every row in `data`, with every value left a string.

    The envelope is positional, so this is the one step that turns it into
    something readable. An empty result is `data: []` with populated `headers`
    and must return `[]`, not raise -- "no rows" is an answer.

    A JSON `null` becomes `""`. Live Zetaris distinguishes the two -- a column
    the source does not have comes back as `null`, a column it has whose value
    is blank comes back as `""` (`docs/DECISIONS.md`, 24 Oct) -- but that
    distinction is a wire-level fact that matters for *fixture fidelity*, not
    for interpretation: both mean "absent" to everything downstream. Collapsing
    them here is what lets the rest of the pack take `str` rather than
    `str | None` everywhere.

    Raises:
        ValueError: if a row is not the same width as `headers`. That means the
            envelope is malformed, and silently zipping the short version would
            shift every later column.
    """
    headers = list(result.get("headers") or [])
    rows = result.get("data") or []
    out: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if len(row) != len(headers):
            raise ValueError(
                f"row {index} has {len(row)} values for {len(headers)} headers; "
                f"the envelope is malformed and zipping it would shift every column"
            )
        out.append({h: ("" if v is None else str(v)) for h, v in zip(headers, row)})
    return out


def rows_from_sql(result: SqlResult) -> list[SourceRow]:
    """Cast a Q0/Q1/Q2/Q3 result into `SourceRow`s.

    Casts `qty` and `days_supply` to int, `doc_date` to date, and `dob_text` to
    `dob` + `dob_raw`. Unknown columns are an error rather than a silent drop:
    `SourceRow` forbids extras, so a view that grew a column fails loudly here
    instead of being ignored for the rest of the run.

    Rows whose `source` is not one of the four are skipped rather than raising,
    so one malformed row cannot lose a whole patient -- but the count is not
    hidden: anything skipped would have to come from a view we did not write.
    """
    out: list[SourceRow] = []
    for raw in dicts_from_sql(result):
        fields = dict(raw)
        dob_text = fields.pop("dob_text", "")
        fields["dob_raw"] = dob_text or None
        fields["dob"] = parse_date(dob_text)
        fields["doc_date"] = parse_date(fields.get("doc_date"))
        for column in ("qty", "days_supply"):
            fields[column] = parse_int(fields.get(column))
        # Empty strings become None so `str | None` fields read as absent.
        for key, value in list(fields.items()):
            if value == "":
                fields[key] = None
        if fields.get("source") not in ("emr", "gp", "pharmacy", "patient"):
            continue
        out.append(SourceRow(**fields))
    return out


def _pair_ingredients(names: str, strength: str) -> list[tuple[str, float | None]]:
    """`"perindopril;indapamide"` + `"5/1.25 mg"` -> `[(..., 5.0), (..., 1.25)]`.

    A combination's per-ingredient strengths are written as `a/b` in the strength
    column, positionally matched to the ingredient list. When the counts do not
    line up the strengths are dropped rather than guessed, because mispairing
    them would attach the wrong milligrams to the wrong drug -- and this is the
    data `detect.duplication` and the dose comparison both rest on.
    """
    parts = [n.strip() for n in (names or "").split(";") if n.strip()]
    if not parts:
        return []
    numbers = re.findall(r"[\d.]+", (strength or "").split()[0] if strength else "")
    if len(numbers) != len(parts):
        return [(name, None) for name in parts]
    paired: list[tuple[str, float | None]] = []
    for name, number in zip(parts, numbers):
        try:
            paired.append((name, float(number)))
        except ValueError:
            paired.append((name, None))
    return paired


def build_lexicon(
    lexicon_rows: list[dict[str, str]],
    apinchs_rows: list[dict[str, str]],
    nickname_rows: list[dict[str, str]],
) -> Lexicon:
    """Build the in-process `Lexicon` from the three Q_REF results.

    Called once at app startup, never per run (`docs/DECISIONS.md`, 24 Oct).
    Builds the casefolded brand and generic indexes, and sorts the APINCHS
    prefixes longest-first so the most specific ATC prefix wins: `A10AB`
    (fast-acting insulin) must beat `A10` before it.

    The nickname map is **symmetric, and closed only within one canonical
    name** -- deliberately *not* transitively closed across a shared variant.
    Peggy, Peg, Maggie and Marg all resolve to each other because they are all
    Margaret. But `Chris` is a variant of both Christine and Christopher, and
    closing through it would make **Christine equivalent to Christopher**. With
    a shared surname and date of birth that is a false merge across two people
    of different sexes, and false-merge rate has a target of zero. Nine variants
    in `data/reference_src/nicknames.csv` are ambiguous this way (`Chris`,
    `Pat`, `Jan`, `Harry`, `Terry`, `Kath`, `Kathy`, `Gerry`, `Ronnie`), so this
    is the common case, not a corner.

    A match made *through* an ambiguous variant is therefore weaker evidence
    than one through an unambiguous one, and `identity.score_pair` weights it
    accordingly.
    """
    entries: list[LexiconEntry] = []
    by_pbs_code: dict[str, LexiconEntry] = {}
    by_amt_code: dict[str, LexiconEntry] = {}
    by_brand: dict[str, LexiconEntry] = {}
    by_generic: dict[str, LexiconEntry] = {}

    for row in lexicon_rows:
        entry = LexiconEntry(
            pbs_code=row.get("pbs_code") or None,
            brand=row.get("brand") or None,
            generic=row.get("generic") or None,
            amt_mp=row.get("amt_mp") or None,
            amt_mpp=row.get("amt_mpp") or None,
            amt_tpp=row.get("amt_tpp") or None,
            atc_primary=row.get("atc_primary") or None,
            strength=row.get("strength") or None,
            form=row.get("form") or None,
            release=row.get("release") if row.get("release") in ("IR", "MR") else "unknown",
            pack_qty=parse_int(row.get("pack_qty")),
            repeats=parse_int(row.get("repeats")),
            is_combination=(row.get("is_combination") or "").strip().lower() in ("true", "1", "yes"),
            ingredients=_pair_ingredients(row.get("ingredients", ""), row.get("strength", "")),
            dos_weight=(lambda v: float(v) if v else None)(row.get("dos_weight") or ""),
        )
        entries.append(entry)
        for code in (entry.pbs_code,):
            if code:
                by_pbs_code.setdefault(code, entry)
        for code in (entry.amt_mp, entry.amt_mpp, entry.amt_tpp):
            if code:
                by_amt_code.setdefault(code, entry)
        # First entry wins for a name: the lexicon is ordered by product, so the
        # first strength of a brand is a reasonable representative. Code lookups
        # are the precise path; these are the fallback.
        if entry.brand:
            by_brand.setdefault(normalise_text(entry.brand), entry)
        if entry.generic:
            by_generic.setdefault(normalise_text(entry.generic), entry)

    apinchs: list[tuple[str, str]] = []
    for row in apinchs_rows:
        prefix = (row.get("atc_prefix") or "").strip().upper()
        klass = (row.get("apinchs_class") or "").strip()
        if prefix and klass:
            apinchs.append((prefix, klass))
    # Longest prefix first, so A10AB beats A10 and the specific rule wins.
    apinchs.sort(key=lambda pair: (-len(pair[0]), pair[0]))

    # canonical -> its variants, built first so closure stays inside one family.
    families: dict[str, set[str]] = {}
    for row in nickname_rows:
        canonical = (row.get("canonical") or "").strip()
        variant = (row.get("variant") or "").strip()
        if not canonical or not variant:
            continue
        families.setdefault(normalise_text(canonical), set()).add(normalise_text(variant))

    nicknames: dict[str, set[str]] = {}
    for canonical, variants in families.items():
        family = {canonical} | variants
        for name in family:
            # Union across families a name belongs to, but never merge the
            # families themselves -- that is the non-transitivity above.
            nicknames.setdefault(name, set()).update(family)

    return Lexicon(
        entries=tuple(entries),
        by_pbs_code=by_pbs_code,
        by_amt_code=by_amt_code,
        by_brand=by_brand,
        by_generic=by_generic,
        apinchs=tuple(apinchs),
        nicknames={name: frozenset(family) for name, family in nicknames.items()},
    )
