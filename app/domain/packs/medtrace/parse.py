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

from app.domain.packs.medtrace.types import Lexicon, SourceRow, SqlResult


def dicts_from_sql(result: SqlResult) -> list[dict[str, str]]:
    """Zip `headers` with every row in `data`, with every value left a string.

    The envelope is positional, so this is the one step that turns it into
    something readable. An empty result is `data: []` with populated `headers`
    and must return `[]`, not raise -- "no rows" is an answer.
    """
    raise NotImplementedError("Arpon: parse.py")


def rows_from_sql(result: SqlResult) -> list[SourceRow]:
    """Cast a Q0/Q1/Q2/Q3 result into `SourceRow`s.

    Casts `qty` and `days_supply` to int, `doc_date` to date, and `dob_text` to
    `dob` + `dob_raw`. Unknown columns are an error rather than a silent drop:
    `SourceRow` forbids extras, so a view that grew a column fails loudly here
    instead of being ignored for the rest of the run.
    """
    raise NotImplementedError("Arpon: parse.py")


def build_lexicon(
    lexicon_rows: list[dict[str, str]],
    apinchs_rows: list[dict[str, str]],
    nickname_rows: list[dict[str, str]],
) -> Lexicon:
    """Build the in-process `Lexicon` from the three Q_REF results.

    Called once at app startup, never per run -- a reference query costs the same
    4-91 s as any other (`docs/DECISIONS.md`, 24 Oct). Builds the casefolded
    brand and generic indexes, sorts the APINCHS prefixes longest-first so the
    most specific ATC prefix wins, and makes the nickname map **symmetric and
    transitively closed within a cluster**, so Peggy -> Margaret -> Maggie all
    resolve to each other.
    """
    raise NotImplementedError("Arpon: parse.py")
