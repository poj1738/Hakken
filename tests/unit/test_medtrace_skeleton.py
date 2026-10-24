"""The MedTrace domain pack is a **frozen contract**. This test freezes it.

Arnav's pipeline imports these functions before their bodies exist (PLAN 2.5),
so a renamed parameter or a changed return type breaks his code at a point where
he cannot tell whether the fault is his. That makes the signature table below the
actual deliverable of the 12pm skeleton, and this file the thing that defends it.

It checks four separate properties:

1. Every module imports. A pack that cannot be imported blocks the whole
   pipeline, and `NotImplementedError` in a body does not stop an import.
2. Every public signature matches the agreed one, **character for character**.
3. Every unimplemented body raises `NotImplementedError("Arpon: <file>")`, so a
   missing piece names its owner instead of surfacing as an `AttributeError` or
   a `None`.
4. `queries.py` and the two real implementations (`identity.decide`,
   `trust.SOURCE_TRUST_PRIORS`) actually work, because those three are the parts
   Arnav can use today.
"""

from __future__ import annotations

import importlib
import inspect
from datetime import date
from typing import Any, get_args

import pytest

from app.domain.packs.medtrace import queries
from app.domain.packs.medtrace.types import (
    FUSED_ATTRIBUTES,
    SOURCES,
    Coverage,
    DiscrepancyCandidate,
    DiscrepancyType,
    EvidenceState,
    IdentityLink,
    Lexicon,
    NoticeType,
    SourceRow,
    TrustAttribute,
)

PACKAGE = "app.domain.packs.medtrace"

MODULES = (
    "types",
    "queries",
    "parse",
    "identity",
    "normalise",
    "coverage",
    "supply",
    "fuse",
    "detect",
    "safety",
    "triage",
    "trust",
)

#: Functions with real bodies. PLAN step 7 fills the pack in module by module,
#: so this grows and `STUB_CALLS` shrinks; the tests below derive from it rather
#: than listing the same names twice. Everything declared must be in exactly one
#: of the two, and a test asserts that.
IMPLEMENTED: set[tuple[str, str]] = {
    ("identity", "decide"),
    ("queries", "q_reference"),
    ("queries", "q_admissions"),
    ("queries", "q_identity_candidates"),
    ("queries", "q_meds_for"),
    ("queries", "q_verify_rows"),
    ("queries", "sql_literal"),
    ("queries", "dob_match_literals"),
    ("parse", "normalise_text"),
    ("parse", "parse_date"),
    ("parse", "parse_int"),
    ("parse", "dicts_from_sql"),
    ("parse", "rows_from_sql"),
    ("parse", "build_lexicon"),
    ("safety", "high_risk_class"),
    ("safety", "forced_confirm"),
    ("safety", "safety_gate"),
    ("coverage", "coverage"),
    ("coverage", "evidence_state"),
    ("coverage", "bpmh_confirmable"),
    ("coverage", "possible_second_pharmacy"),
    ("identity", "score_pair"),
    ("identity", "link_identity"),
    ("identity", "detect_overlay"),
    ("normalise", "normalise_med"),
    ("normalise", "llm_candidates"),
    ("normalise", "strip_salt"),
    ("normalise", "parse_strength_mg"),
    ("normalise", "parse_frequency"),
    ("normalise", "parse_release"),
    ("supply", "supply_status"),
    ("supply", "pdc"),
    ("fuse", "fuse"),
    ("detect", "detect_discrepancies"),
    ("triage", "prioritise"),
}

#: `(module, function) -> the exact signature`, with the quotes that
#: `from __future__ import annotations` puts around each annotation stripped.
#:
#: **Do not edit a line here to make a test pass.** Changing a signature changes
#: a shared file: it needs Arpon's sign-off, a `docs/HANDOFF.md` entry and a line
#: in the PR, because somebody else is already calling it.
EXPECTED_SIGNATURES: dict[tuple[str, str], str] = {
    # -- queries.py: real SQL, usable today ----------------------------------
    ("queries", "q_reference"): "(name: str) -> str",
    ("queries", "q_admissions"): "() -> str",
    ("queries", "q_identity_candidates"): "(anchor: SourceRow) -> str",
    ("queries", "q_meds_for"): "(links: list[IdentityLink]) -> str",
    ("queries", "q_verify_rows"): "(row_ids: list[str]) -> str",
    ("queries", "q_shortages"): "(generics: list[str]) -> str",
    ("queries", "sql_literal"): "(value: str | int | float | None) -> str",
    ("queries", "dob_match_literals"): "(dob_text: str | None) -> list[str]",
    # -- parse.py -------------------------------------------------------------
    ("parse", "normalise_text"): "(value: str | None) -> str",
    ("parse", "parse_date"): "(value: str | None) -> date | None",
    ("parse", "parse_int"): "(value: str | None) -> int | None",
    ("parse", "dicts_from_sql"): "(result: SqlResult) -> list[dict[str, str]]",
    ("parse", "rows_from_sql"): "(result: SqlResult) -> list[SourceRow]",
    ("parse", "build_lexicon"): (
        "(lexicon_rows: list[dict[str, str]], apinchs_rows: list[dict[str, str]], "
        "nickname_rows: list[dict[str, str]]) -> Lexicon"
    ),
    # -- identity.py ----------------------------------------------------------
    ("identity", "decide"): "(probability: float) -> IdentityBand",
    ("identity", "score_pair"): "(a: SourceRow, b: SourceRow, lex: Lexicon) -> IdentityLink",
    ("identity", "link_identity"): (
        "(anchor: SourceRow, candidates: list[SourceRow], lex: Lexicon) -> list[IdentityLink]"
    ),
    ("identity", "detect_overlay"): "(rows_for_one_record: list[SourceRow]) -> list[str]",
    # -- normalise.py ---------------------------------------------------------
    ("normalise", "strip_salt"): "(name: str) -> str",
    ("normalise", "parse_strength_mg"): "(text: str | None) -> float | None",
    ("normalise", "parse_frequency"): "(text: str | None) -> tuple[float | None, bool]",
    ("normalise", "parse_release"): "(*texts: str | None) -> str",
    ("normalise", "normalise_med"): "(row: SourceRow, lex: Lexicon) -> MedStatement",
    ("normalise", "llm_candidates"): "(text: str, lex: Lexicon, k: int = 5) -> dict",
    # -- coverage.py ----------------------------------------------------------
    ("coverage", "coverage"): "(links: list[IdentityLink], rows: list[SourceRow]) -> dict[str, Coverage]",
    ("coverage", "evidence_state"): (
        "(generic: str, source: str, cov: Coverage, stmts: list[MedStatement]) -> EvidenceState"
    ),
    ("coverage", "bpmh_confirmable"): "(cov: dict[str, Coverage]) -> tuple[bool, str]",
    ("coverage", "possible_second_pharmacy"): (
        "(stmts: list[MedStatement], cov: dict[str, Coverage], as_of: date) -> list[str]"
    ),
    # -- supply.py ------------------------------------------------------------
    ("supply", "supply_status"): (
        "(dispensings: list[MedStatement], as_of: date) -> "
        "Literal[ACTIVE_BY_SUPPLY, POSSIBLY_CEASED, NO_DISPENSING]"
    ),
    ("supply", "pdc"): "(dispensings: list[MedStatement], as_of: date, window_days: int = 180) -> float | None",
    # -- fuse.py --------------------------------------------------------------
    ("fuse", "fuse"): (
        "(stmts: list[MedStatement], evidence: dict[str, dict[str, EvidenceState]], "
        "trust: dict[tuple[str, str], float], as_of: date, margin: float = 0.2) -> list[FusedMed]"
    ),
    # -- detect.py ------------------------------------------------------------
    ("detect", "detect_discrepancies"): (
        "(fused: list[FusedMed], stmts: list[MedStatement], cov: dict[str, Coverage], "
        "as_of: date, lex: Lexicon) -> list[DiscrepancyCandidate]"
    ),
    # -- safety.py ------------------------------------------------------------
    ("safety", "high_risk_class"): "(atc: str | None, lex: Lexicon) -> str | None",
    ("safety", "forced_confirm"): "(generic: str, atc: str | None) -> str | None",
    ("safety", "safety_gate"): "(c: DiscrepancyCandidate) -> GateResult",
    # -- triage.py ------------------------------------------------------------
    ("triage", "prioritise"): (
        "(cands: list[DiscrepancyCandidate], acceptance: dict[tuple[str, str], float]) "
        "-> list[DiscrepancyCandidate]"
    ),
}


def _module(name: str) -> Any:
    return importlib.import_module(f"{PACKAGE}.{name}")


def _signature(fn: Any) -> str:
    return str(inspect.signature(fn)).replace("'", "").replace('"', "")


def _row(**kwargs: Any) -> SourceRow:
    base: dict[str, Any] = {"source": "emr", "row_id": "EMR-000001", "source_patient_id": "MRN000123"}
    return SourceRow(**(base | kwargs))


# --------------------------------------------------------------------------- #
# 1. Everything imports
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert _module(name) is not None


def test_package_imports() -> None:
    assert importlib.import_module(PACKAGE) is not None


# --------------------------------------------------------------------------- #
# 2. The frozen signatures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("module", "function"), sorted(EXPECTED_SIGNATURES))
def test_signature_is_frozen(module: str, function: str) -> None:
    fn = getattr(_module(module), function, None)
    assert fn is not None, f"{module}.{function} is missing; Arnav imports it"
    assert _signature(fn) == EXPECTED_SIGNATURES[(module, function)]


def test_no_undeclared_public_functions() -> None:
    """Catch a function added to the pack without being added to the contract.

    The table above is what Arnav codes against, so a public function that is not
    in it is invisible to him and will drift.
    """
    found: set[tuple[str, str]] = set()
    for name in MODULES:
        mod = _module(name)
        for fn_name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ == mod.__name__ and not fn_name.startswith("_"):
                found.add((name, fn_name))
    assert found == set(EXPECTED_SIGNATURES)


# --------------------------------------------------------------------------- #
# 3. Unimplemented bodies name their owner
# --------------------------------------------------------------------------- #

_COV = Coverage(source="gp", state="not_found")
_LINK = IdentityLink(
    anchor_id="emr:MRN000123",
    candidate_id="gp:GP004411",
    match_weight=9.1,
    probability=0.91,
    band="auto-merge",
    tier="probabilistic",
)
_CAND = DiscrepancyCandidate(id="D0001", type=DiscrepancyType.OMISSION, generic="apixaban")
_EMPTY_RESULT: Any = {"headers": [], "data": [], "total": 0, "timeUsed": 1}
_AS_OF = date(2026, 10, 24)

STUB_CALLS: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    ("parse", "normalise_text", ("  Atorvastatin  Calcium ",)),
    ("parse", "parse_date", ("1948-07-03",)),
    ("parse", "parse_int", ("60",)),
    ("identity", "decide", (0.9,)),
    ("queries", "q_reference", ("lexicon",)),
    ("queries", "q_admissions", ()),
    ("queries", "q_identity_candidates", (_row(dob_raw="1948-07-03"),)),
    ("queries", "q_meds_for", ([_LINK],)),
    ("queries", "q_verify_rows", (["GP-000001"],)),
    ("queries", "sql_literal", ("O'Brien",)),
    ("queries", "dob_match_literals", ("1948-07-03",)),
    ("parse", "dicts_from_sql", (_EMPTY_RESULT,)),
    ("parse", "rows_from_sql", (_EMPTY_RESULT,)),
    ("parse", "build_lexicon", ([], [], [])),
    ("identity", "score_pair", (_row(), _row(), Lexicon())),
    ("identity", "link_identity", (_row(), [], Lexicon())),
    ("identity", "detect_overlay", ([],)),
    ("normalise", "strip_salt", ("atorvastatin calcium",)),
    ("normalise", "parse_strength_mg", ("40 mg",)),
    ("normalise", "parse_frequency", ("1 tab bd",)),
    ("normalise", "parse_release", ("modified release tablet",)),
    ("normalise", "normalise_med", (_row(), Lexicon())),
    ("normalise", "llm_candidates", ("my blood thinner", Lexicon())),
    ("coverage", "coverage", ([_LINK], [])),
    ("coverage", "evidence_state", ("warfarin", "gp", _COV, [])),
    ("coverage", "bpmh_confirmable", ({},)),
    ("coverage", "possible_second_pharmacy", ([], {}, _AS_OF)),
    ("supply", "supply_status", ([], _AS_OF)),
    ("supply", "pdc", ([], _AS_OF)),
    ("fuse", "fuse", ([], {}, {}, _AS_OF)),
    ("detect", "detect_discrepancies", ([], [], {}, _AS_OF, Lexicon())),
    ("safety", "high_risk_class", ("B01AA03", Lexicon())),
    ("safety", "forced_confirm", ("warfarin", "B01AA03")),
    ("safety", "safety_gate", (_CAND,)),
    ("triage", "prioritise", ([], {})),
    ("queries", "q_shortages", (["warfarin"],)),
)


@pytest.mark.parametrize(
    ("module", "function", "args"),
    [call for call in STUB_CALLS if (call[0], call[1]) not in IMPLEMENTED],
)
def test_stub_names_its_owner_and_file(module: str, function: str, args: tuple[Any, ...]) -> None:
    with pytest.raises(NotImplementedError) as excinfo:
        getattr(_module(module), function)(*args)
    assert str(excinfo.value).startswith(f"Arpon: {module}.py")


@pytest.mark.parametrize(
    ("module", "function", "args"),
    [call for call in STUB_CALLS if (call[0], call[1]) in IMPLEMENTED],
)
def test_an_implemented_function_no_longer_raises(module: str, function: str,
                                                  args: tuple[Any, ...]) -> None:
    """Once a body lands it must handle the empty case rather than raise.

    Every one of these is called with empty or minimal input, which is exactly
    what a run with a missing source hands it. Raising there would turn a
    coverage gap into a crashed run.
    """
    getattr(_module(module), function)(*args)


def test_every_declared_function_is_either_implemented_or_a_named_stub() -> None:
    """No third state: nothing in the pack may silently return `None`.

    Every declared function is either in `IMPLEMENTED` or has an entry in
    `STUB_CALLS`, and `STUB_CALLS` covers both so an implemented function is
    still exercised on empty input.
    """
    declared = set(EXPECTED_SIGNATURES)
    callable_entries = {(m, f) for m, f, _ in STUB_CALLS}
    assert IMPLEMENTED <= declared, IMPLEMENTED - declared
    assert callable_entries | IMPLEMENTED == declared, declared - (callable_entries | IMPLEMENTED)


# --------------------------------------------------------------------------- #
# 4a. queries.py -- the templates agents will actually send
# --------------------------------------------------------------------------- #

LIVE_TEMPLATES: tuple[tuple[str, Any], ...] = (
    ("q_reference", lambda: queries.q_reference("lexicon")),
    ("q_admissions", queries.q_admissions),
    ("q_identity_candidates", lambda: queries.q_identity_candidates(
        _row(ihi_syn="SYN-123456789012", name_given="Margaret", name_family="Smith", dob_raw="1948-07-03")
    )),
    ("q_meds_for", lambda: queries.q_meds_for([_LINK])),
    ("q_verify_rows", lambda: queries.q_verify_rows(["GP-002210", "PHM-004410"])),
)


@pytest.mark.parametrize(("name", "build"), LIVE_TEMPLATES)
def test_template_is_one_statement(name: str, build: Any) -> None:
    """`REFERENCE_NOTES` 1.2: one statement per REST call, no trailing semicolon."""
    sql = build()
    assert ";" not in sql
    assert sql == " ".join(sql.split())
    assert sql.startswith("SELECT ")


@pytest.mark.parametrize(("name", "build"), LIVE_TEMPLATES)
def test_template_avoids_the_constructs_that_fail_or_time_out(name: str, build: Any) -> None:
    """The three live findings in this module's docstring, as a test.

    A `JOIN` cost 91 s on a 2-table query; a second reference to the union view
    fails outright; `DISTINCT` over a union of explode views is unproven.
    """
    sql = build().upper()
    for banned in (" JOIN ", "DISTINCT", "OVER (", "GROUP BY", "SELECT *"):
        assert banned not in sql, f"{name} uses {banned.strip()!r}"


def test_the_union_view_is_referenced_exactly_once() -> None:
    """A second reference raises MISSING_ATTRIBUTES on a union-of-explode view."""
    for build in (
        lambda: queries.q_identity_candidates(_row(dob_raw="1948-07-03", name_family="Smith")),
        lambda: queries.q_meds_for([_LINK]),
        lambda: queries.q_verify_rows(["GP-002210"]),
    ):
        assert build().count(queries.ALL_SOURCES_VIEW) == 1


def test_q_reference_covers_every_reference_view() -> None:
    for name, view in queries.REFERENCE_VIEWS.items():
        assert view in queries.q_reference(name)
    with pytest.raises(queries.QueryBuildError):
        queries.q_reference("tga")


def test_q1_blocks_on_ihi_dob_formats_the_swap_and_the_surname() -> None:
    """The blocking predicate has to catch every planted identity corruption.

    A candidate that Q1 does not return can never be linked, scored or shown as a
    near-miss, so recall here caps the recall of the whole identity stage.
    """
    sql = queries.q_identity_candidates(
        _row(ihi_syn="SYN-123456789012", name_given="Margaret", name_family="Smith", dob_raw="1948-07-03")
    )
    assert "'SYN-123456789012'" in sql
    for spelling in ("'1948-07-03'", "'03/07/1948'", "'1948-03-07'", "'07/03/1948'"):
        assert spelling in sql, f"Q1 does not block on {spelling}"
    assert "UPPER(name_previous) LIKE 'SMIT%'" in sql   # maiden name
    assert "UPPER(name_given) LIKE 'SMIT%'" in sql      # pharmacy's combined name field
    assert "source = 'emr' AND source_patient_id = 'MRN000123'" in sql   # the anchor itself


def test_q1_still_builds_for_a_row_with_nothing_to_block_on() -> None:
    sql = queries.q_identity_candidates(_row())
    assert sql.count("WHERE") == 1
    assert "MRN000123" in sql


def test_dob_match_literals_emits_the_swap_only_when_it_is_a_real_date() -> None:
    assert queries.dob_match_literals("1948-07-03") == ["03/07/1948", "07/03/1948", "1948-03-07", "1948-07-03"]
    # Day 25 is not a month, so there is no swapped spelling to look for.
    assert queries.dob_match_literals("1948-07-25") == ["1948-07-25", "25/07/1948"]
    assert queries.dob_match_literals("07/03/1948") == ["03/07/1948", "07/03/1948", "1948-03-07", "1948-07-03"]
    assert queries.dob_match_literals(None) == []
    # Unparseable text is still worth blocking on verbatim.
    assert queries.dob_match_literals("3 July 1948") == ["3 July 1948"]


def test_surname_prefix_survives_punctuation() -> None:
    """`O'Brien` must yield `O''BR%`, not `OBRI%`, or it never matches `O'BRIEN`."""
    sql = queries.q_identity_candidates(_row(name_family="O'Brien", dob_raw="1948-07-03"))
    assert r"UPPER(name_family) LIKE 'O\'BR%'" in sql
    assert "OBRI" not in sql
    assert "'O''BR%'" not in sql   # the doubled form would collapse to 'OBR%'


def test_sql_literal_uses_backslash_escaping_not_a_doubled_quote() -> None:
    """The doubled quote is **wrong in this dialect and fails silently.**

    Measured live on 24 Oct: `SELECT 'O''Brien'` returns `OBrien`, length 6.
    `''` closes one literal and opens another, adjacent literals concatenate,
    and the apostrophe is deleted with balanced quotes and no error. A
    `WHERE zone LIKE '%''%'` matched 789 of 789 rows against the real 12.

    So this assertion is not a style preference. With the doubled form,
    `O'Brien` reaches Zetaris as `OBrien`, matches nothing, and the pharmacist
    is told "GP: no record found" for a record that exists.
    """
    assert queries.sql_literal("O'Brien") == r"'O\'Brien'"
    assert "''" not in queries.sql_literal("O'Brien")
    assert queries.sql_literal("a\\b") == r"'a\\b'"       # backslash doubled, not refused
    assert queries.sql_literal(None) == "NULL"
    assert queries.sql_literal(5) == "5"
    for hostile in ("x; DROP VIEW medtrace.emr", "a\nb", "a\x00b", "x" * 257):
        with pytest.raises(queries.QueryBuildError):
            queries.sql_literal(hostile)
    with pytest.raises(queries.QueryBuildError):
        queries.sql_literal(True)


def test_an_injection_attempt_stays_inside_the_literal() -> None:
    """Verified live: these come back from Zetaris as inert strings."""
    assert queries.sql_literal("x' OR 1=1 --") == r"'x\' OR 1=1 --'"
    assert queries.sql_literal("x'") == r"'x\''"


def test_a_hostile_name_cannot_change_the_shape_of_a_template() -> None:
    """A quote in the data must stay inside the literal, not add a clause.

    A semicolon is still refused outright, because no template embeds free text
    and refusing keeps the statement-level guard sound.
    """
    with pytest.raises(queries.QueryBuildError):
        queries.q_identity_candidates(_row(ihi_syn="SYN-1'; DROP VIEW medtrace.emr --"))
    sql = queries.q_identity_candidates(_row(name_family="O'Brien OR 1=1", dob_raw="1948-07-03"))
    assert sql.count("WHERE") == 1
    assert "1=1" not in sql   # truncated at the space by the prefix scan


def test_empty_in_lists_are_refused_not_silently_emptied() -> None:
    """An empty `IN ()` is a successful query returning nothing, which reads as
    'this patient has no medicines' -- the most dangerous possible wrong answer."""
    with pytest.raises(queries.QueryBuildError):
        queries.q_meds_for([])
    with pytest.raises(queries.QueryBuildError):
        queries.q_verify_rows([])


def test_q_meds_for_reads_both_ends_of_every_link_and_validates_keys() -> None:
    sql = queries.q_meds_for([_LINK])
    assert "source = 'emr' AND source_patient_id = 'MRN000123'" in sql
    assert "source = 'gp' AND source_patient_id = 'GP004411'" in sql
    bad = _LINK.model_copy(update={"candidate_id": "gp/GP004411"})
    with pytest.raises(queries.QueryBuildError):
        queries.q_meds_for([bad])


def test_q_verify_rows_batches_and_deduplicates() -> None:
    sql = queries.q_verify_rows(["GP-002210", "GP-002210", "PHM-004410"])
    assert sql.count("GP-002210") == 1
    with pytest.raises(queries.QueryBuildError):
        queries.q_verify_rows(["GP-002210'"])


def test_the_query_budget_matches_the_plan() -> None:
    assert queries.MAX_ZETARIS_QUERIES_PER_RUN == 8
    assert set(queries.SOURCE_VIEWS) == set(SOURCES)
    assert queries.TEMPLATE_IDS == ("Q_REF", "Q0", "Q1", "Q2", "Q3", "Q4")


def test_every_template_selects_only_declared_harmonised_columns() -> None:
    """A column that is not in PLAN 2.3 means the view and the templates disagree."""
    declared = set(queries.HARMONISED_COLUMNS)
    assert set(queries.IDENTITY_COLUMNS) <= declared
    selected = queries.q_meds_for([_LINK]).split(" FROM ")[0].removeprefix("SELECT ")
    assert [c.strip() for c in selected.split(",")] == list(queries.HARMONISED_COLUMNS)


# --------------------------------------------------------------------------- #
# 4b. identity.decide -- real today, replaced by World Model at 4pm
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("probability", "band"),
    [
        (1.0, "auto-merge"),
        (0.85, "auto-merge"),
        (0.8499, "review"),
        (0.82, "review"),
        (0.8199, "new"),
        (0.0, "new"),
    ],
)
def test_decide_bands(probability: float, band: str) -> None:
    """0.85 / 0.82, inclusive at both edges. The World Model port must agree."""
    from app.domain.packs.medtrace.identity import decide

    assert decide(probability) == band


# --------------------------------------------------------------------------- #
# 4c. trust.SOURCE_TRUST_PRIORS -- the H-MEM seed
# --------------------------------------------------------------------------- #


def test_priors_quote_the_plan_verbatim() -> None:
    """PLAN 2.5 names seven of these. They are the agreed contract, not a default."""
    from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS

    for key, value in {
        ("pharmacy", "existence"): 0.85,
        ("pharmacy", "strength"): 0.90,
        ("gp", "intended_dose"): 0.75,
        ("gp", "existence"): 0.60,
        ("patient", "actually_taking"): 0.80,
        ("patient", "name"): 0.50,
        ("emr", "admission_chart"): 0.60,
    }.items():
        assert SOURCE_TRUST_PRIORS[key] == pytest.approx(value), key


def test_priors_cover_every_source_and_fusable_attribute() -> None:
    """`fuse` resolves five attributes; a missing prior would silently fall back."""
    from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS

    for source in SOURCES:
        for attribute in FUSED_ATTRIBUTES:
            assert (source, attribute) in SOURCE_TRUST_PRIORS, (source, attribute)


def test_prior_keys_are_in_the_declared_vocabulary() -> None:
    from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS

    attributes = set(get_args(TrustAttribute))
    for source, attribute in SOURCE_TRUST_PRIORS:
        assert source in SOURCES, source
        assert attribute in attributes, attribute


def test_priors_are_probabilities_and_nothing_is_certain() -> None:
    from app.domain.packs.medtrace.trust import DEFAULT_TRUST, SOURCE_TRUST_PRIORS

    assert all(0.0 < v < 1.0 for v in SOURCE_TRUST_PRIORS.values())
    assert DEFAULT_TRUST == 0.5


def test_the_priors_encode_who_knows_what() -> None:
    """The point of keying trust by attribute, asserted rather than assumed.

    If these ever invert, fusion is resolving conflicts by the wrong authority
    and every downstream discrepancy inherits the error.
    """
    from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS as p

    # The pharmacy saw the box; the patient is guessing.
    assert p[("pharmacy", "strength")] > p[("patient", "strength")]
    # Dispensing proves supply; a GP list outlives the prescription.
    assert p[("pharmacy", "existence")] > p[("gp", "existence")]
    # Only the patient knows what they actually swallow.
    assert p[("patient", "actually_taking")] > p[("emr", "actually_taking")]
    # The pharmacy silo has no directions field at all (PLAN 2.2).
    assert p[("pharmacy", "frequency")] < p[("emr", "frequency")]


# --------------------------------------------------------------------------- #
# 4d. types.py -- the vocabulary the UI and the pipeline share
# --------------------------------------------------------------------------- #


def test_absence_stays_three_valued() -> None:
    """Collapsing `UNKNOWN` into `ABSENT_IN_SCOPE` is the failure that tells a
    pharmacist a patient stopped a medicine they are still taking."""
    assert {s.value for s in EvidenceState} == {"present", "absent_in_scope", "unknown"}


def test_the_taxonomy_matches_the_plan() -> None:
    assert {t.value for t in DiscrepancyType} == {
        "omission", "commission", "dose", "frequency", "formulation", "route",
        "duplication", "stale_listing", "dose_unconfirmable",
        "unpropagated_discharge_change", "identity_uncertain",
    }
    assert {n.value for n in NoticeType} == {
        "coverage_gap", "bpmh_not_confirmable", "possible_second_pharmacy",
        "patient_only_item", "conflict_abstained", "stale_document",
        # Declared while types.py was being frozen so Monday's optional TGA
        # overlay cannot force an edit to a shared file Arnav already imports.
        "known_shortage",
    }


def test_suppressed_differences_are_never_findings() -> None:
    """Lipitor vs atorvastatin is the canonical false positive. The demo shows it
    *not* firing, so the list is asserted rather than left to a detector."""
    from app.domain.packs.medtrace.triage import SUPPRESS

    assert SUPPRESS == ["brand_only", "notation_only", "equivalent_daily_dose"]
    assert not set(SUPPRESS) & {t.value for t in DiscrepancyType}


def test_source_row_keeps_the_raw_dob_and_rejects_unknown_columns() -> None:
    row = _row(dob_raw="03/07/1948", dob=date(1948, 7, 3))
    assert (row.dob_raw, row.dob.isoformat()) == ("03/07/1948", "1948-07-03")
    assert row.record_key == "emr:MRN000123"
    assert row.has_med is False
    with pytest.raises(Exception):
        _row(unexpected_column="x")


def test_the_sql_envelope_type_matches_the_recorded_fixture() -> None:
    """`SqlResult` describes a real response, not a hoped-for one."""
    import json

    from app.domain.packs.medtrace.types import SqlResult

    for name in ("select_1", "empty_result", "show_lightning_databases"):
        with open(f"tests/fixtures/zetaris/{name}.json", encoding="utf-8") as handle:
            recorded = json.load(handle)
        assert SqlResult.__required_keys__ <= set(recorded), name
    # `timeUsed` is stripped from the fixtures, so requiring it would make every
    # SAMPLE_MODE replay fail this type.
    assert SqlResult.__optional_keys__ == frozenset({"timeUsed"})
