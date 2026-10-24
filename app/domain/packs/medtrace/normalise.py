"""Free text and codes -> one `MedStatement` (brief section 4; PLAN 2.5).

Resolution order is strict, and the order is the point: `code -> exact lexicon ->
fuzzy -> unmapped`. A code is a fact; a fuzzy match is a guess with a score; and
`unmapped` is an honest answer that the UI renders as "could not resolve". The
LLM never enters this chain -- it only picks from `llm_candidates`, and its
answer is recorded as `resolution="llm"` so a reader can discount it.

`daily_dose_mg` is the comparison key for dose discrepancies, so "500mg bd" and
"1g daily" must land on the same number. Getting that wrong in either direction
is a false flag or a missed one.
"""

from __future__ import annotations

import re

import jellyfish

from app.domain.packs.medtrace.parse import normalise_text, parse_date
from app.domain.packs.medtrace.types import Lexicon, MedStatement, SourceRow

#: Salt and ester words stripped when resolving a *name*. This is for lookup
#: only and never decides equivalence.
#:
#: **Metoprolol is the trap.** Tartrate is the immediate-release salt and
#: succinate the modified-release one, and they are *not* interchangeable
#: 1:1 -- so stripping the salt would collapse two genuinely different products.
#: It is safe here only because `release` is determined **independently** from
#: the form text, so "metoprolol succinate MR" resolves to the molecule
#: metoprolol *and* keeps `release="MR"`. If release were ever inferred from the
#: salt, this list would become a correctness bug.
SALTS = (
    "arginine", "erbumine", "calcium", "sodium", "potassium", "hydrochloride",
    "hydrobromide", "maleate", "besylate", "mesylate", "fumarate", "succinate",
    "tartrate", "citrate", "sulfate", "sulphate", "phosphate", "acetate",
    "benzoate", "dihydrate", "monohydrate", "anhydrous", "hcl",
)

#: Phrases that mean modified release. Matched as substrings: they are long
#: enough that a substring hit is never a coincidence.
MR_MARKERS = ("modified release", "controlled release", "controlled delivery",
              "sustained release", "extended release")

#: Short suffixes that mean modified release ("Efexor-XR", "Diamicron MR",
#: "Cardizem CD", "Inderal LA"). Matched as **whole words only**. As bare
#: substrings they matched the start of ordinary names: " cr" made **Crestor**
#: modified release, and " la" would have done the same to lansoprazole, Lasix,
#: lamotrigine and lactulose -- so rosuvastatin, which has no MR form in
#: Australia, was being reported as MR and set up a false formulation finding.
MR_SUFFIXES = re.compile(r"\b(mr|cr|sr|xr|xl|cd|la)\b")

#: `pattern -> doses per day`. Covers the enum forms (DATA_SPEC 2.1) and the
#: free text the GP and patient silos emit. Longest patterns first, so "twice a
#: day" is not matched by "a day".
FREQUENCY: tuple[tuple[str, float], ...] = (
    ("six monthly", 1 / 182), ("6-monthly", 1 / 182), ("6 monthly", 1 / 182),
    ("every six months", 1 / 182), ("yearly", 1 / 365), ("annually", 1 / 365),
    ("monthly", 1 / 30), ("every month", 1 / 30),
    ("once a week", 1 / 7), ("once weekly", 1 / 7), ("weekly", 1 / 7),
    ("four times a day", 4.0), ("4 times a day", 4.0), ("qid", 4.0),
    ("three times a day", 3.0), ("3 times a day", 3.0), ("tds", 3.0), ("tid", 3.0),
    ("morning and night", 2.0), ("twice a day", 2.0), ("twice daily", 2.0),
    ("bd", 2.0), ("bid", 2.0),
    ("in the morning", 1.0), ("at night", 1.0), ("once a day", 1.0),
    ("once daily", 1.0), ("one a day", 1.0), ("mane", 1.0), ("nocte", 1.0),
    ("daily", 1.0), ("od", 1.0),
)

#: Lay descriptions -> the ATC classes they could mean (DATA_SPEC 10.3). Used
#: only to constrain `llm_candidates`; never to resolve a medicine directly.
LAY_TERMS: dict[str, tuple[str, ...]] = {
    "blood thinner": ("B01AA", "B01AF", "B01AE", "B01AC"),
    "clot pill": ("B01AA", "B01AF", "B01AE", "B01AC"),
    "water tablet": ("C03", "C09BA", "C09DA"),
    "fluid pill": ("C03",),
    "puffer": ("R03AC02",), "blue puffer": ("R03AC02",),
    "preventer puffer": ("R03AK", "R03AL"),
    "sugar tablet": ("A10B",), "diabetes tablet": ("A10B",),
    "my insulin": ("A10A", "A10BJ"), "the pen": ("A10A", "A10BJ"),
    "cholesterol tablet": ("C10A", "C10B"),
    "blood pressure tablet": ("C02", "C03", "C07", "C08", "C09"),
    "heart tablet": ("C01", "C07", "C08", "B01AC"),
    "spray under the tongue": ("C01DA02",),
    "thyroid tablet": ("H03AA01",),
    "stomach tablet": ("A02BC", "A02BA"), "reflux tablet": ("A02BC", "A02BA"),
    "pain killer": ("N02BE01", "N02A"), "arthritis panadol": ("N02BE01",),
    "sleeping tablet": ("N05CD", "N05CF"),
    "nerve tablet": ("N06A", "N05BA"),
    "bone tablet": ("M05BA", "M05BB"), "bone injection": ("M05BX04",),
    "gout tablet": ("M04AA01",),
    "prostate tablet": ("G04CA",), "waterworks tablet": ("G04CA",),
    "patch": ("N02AB03", "N02AE01", "C01DA02"),
}

#: Jaro-Winkler at or above this is a `fuzzy` resolution; below it, `unmapped`.
FUZZY_THRESHOLD = 0.92

_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")
_UNIT = re.compile(r"(microgram|mcg|µg|milligram|mg|gram|\bg\b|unit|iu|ml)", re.I)


def strip_salt(name: str) -> str:
    """`"atorvastatin calcium"` -> `"atorvastatin"`. Lookup only -- see `SALTS`."""
    words = [w for w in normalise_text(name).split() if w not in SALTS]
    return " ".join(words)


def parse_strength_mg(text: str | None) -> float | None:
    """Leading strength in milligrams.

    **mcg and mg are a 1000x error** and they land on digoxin (62.5 microgram)
    and levothyroxine (50-150 microgram), both of which we treat as high-risk.
    Units the silos use: mg, microgram/mcg, g, unit/IU, mL.

    For a combination written `5/1.25 mg`, returns the **first** component --
    the per-ingredient split lives in `MedStatement.ingredients`.
    """
    if not text:
        return None
    raw = str(text).strip()
    number = _NUMBER.search(raw)
    if not number:
        return None
    value = float(number.group(1))
    unit = _UNIT.search(raw)
    token = (unit.group(1).lower() if unit else "mg")
    if token in ("microgram", "mcg", "µg"):
        return value / 1000.0
    if token in ("gram", "g"):
        return value * 1000.0
    # units, IU and mL are not masses; carry the number without scaling and let
    # the comparison stay within the same unit family.
    return value


def parse_frequency(text: str | None) -> tuple[float | None, bool]:
    """Free text -> `(doses per day, is PRN)`.

    Handles the enum forms and the lay phrasings the GP and patient silos emit
    ("morning and night", "one a day"). A leading count multiplies: `"2 tds"`
    is six doses a day, which is how paracetamol MR is actually written.

    Returns `(None, prn)` when nothing matches, rather than defaulting to once
    daily -- a guessed frequency produces a confidently wrong daily dose.
    """
    if not text:
        return None, False
    raw = f" {normalise_text(text)} "
    prn = bool(re.search(r"\bprn\b|as needed|when (?:i )?need|if needed", raw))
    per_day: float | None = None
    for pattern, value in FREQUENCY:
        if pattern in raw:
            per_day = value
            break
    if per_day is None:
        return None, prn
    return per_day * _leading_units(raw), prn


#: Number words the GP and patient silos write out. "2 tds" is rendered as
#: "two three times a day", and a digit-only regex reads that as one dose.
_WORD_NUMBERS = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
                 "half": 0.5, "a": 1.0, "an": 1.0}

_DOSE_FORM = r"(?:tab|tabs|tablet|tablets|cap|caps|capsule|capsules|puff|puffs)?"


def _leading_units(raw: str) -> float:
    """Doses per administration, from the front of a direction.

    Handles `"1 tab bd"`, `"two three times a day"` and the **range** form
    `"1 to 2 nocte"`, which the T2DM and osteoporosis bundles both use. A range
    is averaged rather than taken at either end: picking the low end
    understates every titrated dose and the high end overstates it, and both
    land on a dose comparison that then reports a discrepancy that is not there.
    """
    span = re.match(rf"\s*(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*{_DOSE_FORM}\s", raw)
    if span:
        return (float(span.group(1)) + float(span.group(2))) / 2.0
    digits = re.match(rf"\s*(\d+(?:\.\d+)?)\s*{_DOSE_FORM}\s", raw)
    if digits:
        return float(digits.group(1))
    words = re.match(rf"\s*([a-z]+)\s*{_DOSE_FORM}\s", raw)
    if words and words.group(1) in _WORD_NUMBERS:
        return _WORD_NUMBERS[words.group(1)]
    return 1.0


def parse_release(*texts: str | None) -> str:
    """`IR` / `MR` / `unknown`, from any of the form, brand or medicine text.

    Determined **independently of the salt**, which is what makes salt
    stripping safe for metoprolol -- see `SALTS`.
    """
    blob = " " + " ".join(normalise_text(t) for t in texts if t) + " "
    if any(marker in blob for marker in MR_MARKERS) or MR_SUFFIXES.search(blob):
        return "MR"
    if any(word in blob for word in ("tablet", "capsule", "immediate release")):
        return "IR"
    return "unknown"


#: id(lex) -> (lex, generic -> the releases its products come in). Holding the
#: Lexicon itself means the id cannot be reused by a different object.
_RELEASES: dict[int, tuple[Lexicon, dict[str, frozenset[str]]]] = {}


def _releases_for(generic: str | None, lex: Lexicon) -> frozenset[str]:
    cached = _RELEASES.get(id(lex))
    if cached is None or cached[0] is not lex:
        table: dict[str, set[str]] = {}
        for entry in lex.entries:
            if entry.generic and entry.release in ("IR", "MR"):
                table.setdefault(entry.generic, set()).add(entry.release)
        cached = (lex, {g: frozenset(r) for g, r in table.items()})
        _RELEASES[id(lex)] = cached
    return cached[1].get(generic or "", frozenset())


def _pins_product(row: SourceRow, entry: object) -> bool:
    """Did this row identify one specific product, rather than just a medicine?

    A PBS item code or an AMT MPP/TPP code names one product; so does its brand
    written in the text. An AMT **MP** code or a bare generic name does not --
    the MP code is shared by every product of that medicine.
    """
    code = (row.med_code or "").strip()
    if code and code in {getattr(entry, k, None) for k in ("pbs_code", "amt_mpp", "amt_tpp")}:
        return True
    brand = normalise_text(getattr(entry, "brand", None))
    generic = normalise_text(getattr(entry, "generic", None))
    return bool(brand) and brand != generic and brand in normalise_text(row.med_text)


def _release_from_lexicon(row: SourceRow, entry: object, lex: Lexicon) -> str:
    """The lexicon's release, but only when it actually knows.

    `by_amt_code` is filled with `setdefault`, so an AMT MP code -- shared by
    every product of a medicine -- resolves to whichever product was loaded
    first. Taking *that* product's release invented a formulation: the EMR's
    plain "metformin" came out IR while the GP and pharmacy, which name Diabex
    XR, said MR, which is a formulation discrepancy that does not exist.

    So the lexicon may supply release only if the row pinned one product, or if
    every product of that medicine has the same release (rosuvastatin is IR
    whatever brand). Six medicines in the lexicon come in both, and for those an
    unspecified release stays `unknown`.
    """
    if _pins_product(row, entry):
        own = getattr(entry, "release", "unknown")
        if own in ("IR", "MR"):
            return own
        return parse_release(getattr(entry, "form", None))
    releases = _releases_for(getattr(entry, "generic", None), lex)
    return next(iter(releases)) if len(releases) == 1 else "unknown"


#: Route codes the EMR writes, and their spoken forms.
ROUTE_CODES = {"po": "PO", "oral": "PO", "by mouth": "PO", "sl": "SL",
               "sublingual": "SL", "iv": "IV", "intravenous": "IV", "sc": "SC",
               "subcut": "SC", "subcutaneous": "SC", "im": "IM", "intramuscular": "IM",
               "inh": "INH", "inhaled": "INH", "neb": "INH", "top": "TOP",
               "topical": "TOP", "td": "TD", "transdermal": "TD", "pr": "PR"}

#: Dose forms that imply exactly one route. Anything else -- "injection" could be
#: SC, IM or IV; "spray" could be sublingual or nasal -- implies nothing.
FORM_ROUTES = (("inhaler", "INH"), ("patch", "TD"), ("tablet", "PO"), ("capsule", "PO"))


def _canonical_route(text: str | None) -> str | None:
    """A route code (`PO`, `SL`, `INH` ...), or `None` when the text does not say.

    The pharmacy silo has no route column: what arrives in `route_text` is the
    dosage form ("tablet", "modified release tablet", "spray"). Passed through
    raw it disagreed with the EMR's "PO" on nearly every medicine, so fusion saw
    a route conflict that does not exist. A form that implies one route is
    mapped to it; an ambiguous one is `None`, which counts as no evidence
    rather than as a contradiction.
    """
    value = normalise_text(text)
    if not value:
        return None
    if value in ROUTE_CODES:
        return ROUTE_CODES[value]
    for form, route in FORM_ROUTES:
        if form in value:
            return route
    return None


#: Dose forms whose pack size does not imply a daily dose.
DEVICE_FORMS = ("inhaler", "spray", "patch", "injection", "pen", "device",
                "cream", "ointment", "drops", "solution")


def _is_device(row: SourceRow, entry: object | None) -> bool:
    blob = " ".join(normalise_text(t) for t in (
        row.route_text, getattr(entry, "form", None), row.med_text) if t)
    return any(form in blob for form in DEVICE_FORMS)


def _status_for(row: SourceRow) -> str:
    """Per-source status mapping (DATA_SPEC 2.1 to 2.4).

    The patient silo's `unsure` maps to `unknown`, **never** `ceased` -- reading
    uncertainty as cessation is how a tool tells someone to stop a medicine.
    """
    value = normalise_text(row.status_text)
    if not value:
        return "unknown"
    if row.source == "patient":
        return {"yes": "active", "no": "ceased"}.get(value, "unknown")
    if row.source == "gp":
        return {"active": "active", "ceased": "ceased"}.get(value, "unknown")
    if row.source == "emr":
        # A discharge action, not a status: `cease` is the only one that ends it.
        return {"cease": "ceased", "continue": "active",
                "start": "active", "change": "active"}.get(value, "unknown")
    return "unknown"


def _resolve(row: SourceRow, lex: Lexicon) -> tuple[object | None, str]:
    """`(lexicon entry or None, resolution)` -- the strict order."""
    # 1. code. A code is a fact, so it wins outright.
    code = (row.med_code or "").strip()
    if code:
        entry = lex.by_amt_code.get(code) or lex.by_pbs_code.get(code)
        if entry is not None:
            return entry, "code"

    text = row.med_text or ""
    # Strip a trailing strength: the GP silo writes "Lipitor 40mg".
    name = re.sub(r"\s*\d+(?:\.\d+)?\s*(?:mg|mcg|microgram|g|iu|units?)\b.*$", "",
                  text, flags=re.I).strip()
    name = re.sub(r"\s*\d+(?:\.\d+)?/\d+(?:\.\d+)?\s*\w*\s*$", "", name).strip()
    key = normalise_text(name)

    # 2. exact lexicon: brand, then generic, then salt-stripped generic.
    for candidate in (key, strip_salt(name)):
        if not candidate:
            continue
        entry = lex.by_brand.get(candidate) or lex.by_generic.get(candidate)
        if entry is not None:
            return entry, "lexicon"

    # 3. fuzzy, with the score kept.
    if key:
        best, score = None, 0.0
        for index in (lex.by_generic, lex.by_brand):
            for candidate_key, entry in index.items():
                similarity = jellyfish.jaro_winkler_similarity(key, candidate_key)
                if similarity > score:
                    best, score = entry, similarity
        if best is not None and score >= FUZZY_THRESHOLD:
            return best, "fuzzy"

    # 4. unmapped. Never guessed.
    return None, "unmapped"


def normalise_med(row: SourceRow, lex: Lexicon) -> MedStatement:
    """Resolve one harmonised row into a canonical medication statement.

    Resolution, in order, recorded in `MedStatement.resolution`:
      1. `code` -- `med_code` against the lexicon by `code_system` (AMT MP/MPP/TPP
         or PBS). Joining on codes rather than names is a reference-data rule:
         `drug_name` does not map 1:1 to the AMT preferred term (PLAN 3).
      2. `lexicon` -- exact match on brand, generic, or the salt-stripped generic,
         so "atorvastatin calcium" meets "atorvastatin".
      3. `fuzzy` -- Jaro-Winkler above a threshold, score retained.
      4. `unmapped` -- shown as unresolved. Never guessed.

    Also:
      - **Decomposes combinations** into `ingredients`, which is what makes
        Coversyl Plus + perindopril detectable as a duplication rather than two
        unrelated drugs.
      - Computes total `daily_dose_mg`, parsing bd/tds/qid/mane/nocte/weekly and
        PRN, and handling **mcg vs mg** -- a 1000x error that lands on digoxin
        and levothyroxine, both high-risk.
      - Sets `release` (IR/MR), because oxycodone CR and IR at the same daily
        dose are a real formulation discrepancy and not a notation difference.
      - Maps `status_text` per source, where the patient silo's `unsure` is
        `unknown` and **never** `ceased`.

    The pharmacy silo carries no directions at all, so its frequency is inferred
    from `qty / days_supply`. That inference is weaker than a written direction,
    which is why `trust.SOURCE_TRUST_PRIORS` scores pharmacy lowest on frequency.
    """
    entry, resolution = _resolve(row, lex)

    generic = None
    ingredients: list[tuple[str, float | None]] = []
    atc = None
    if entry is not None:
        generic = entry.generic
        ingredients = list(entry.ingredients)
        atc = entry.atc_primary

    # What this source itself wrote, first. The lexicon only fills a gap, and
    # only when it can genuinely say -- see _release_from_lexicon.
    release = parse_release(row.route_text, row.med_text)
    if (release == "IR" and entry is not None and entry.release == "MR"
            and _pins_product(row, entry)):
        # A bare "capsule" or "tablet" is a weak signal; a named product is a
        # strong one. Cymbalta is a delayed-release capsule, and the pharmacy
        # silo's form column just says "capsule" -- read alone that made it IR
        # and contradicted the GP and the EMR.
        release = "MR"
    elif release == "unknown" and entry is not None:
        release = _release_from_lexicon(row, entry, lex)

    strength = parse_strength_mg(row.strength_text or row.dose_text)
    per_day, prn = parse_frequency(row.freq_text)
    if per_day is None and row.source == "pharmacy" and row.qty and row.days_supply:
        # No directions column in this silo, so infer from the pack -- but only
        # for a counted solid dose form. One inhaler per 7 days is not "0.14
        # doses a day": a device's pack size says nothing about how much is
        # taken, and the arithmetic produced daily doses that were wrong by an
        # order of magnitude (a GTN spray came out at 0.057 mg/day against a
        # true 0.4). Returning nothing is the honest answer, and `fuse` already
        # treats an absent value as absent rather than as zero.
        if not _is_device(row, entry):
            per_day = row.qty / row.days_supply

    daily = round(strength * per_day, 4) if (strength is not None and per_day) else None

    return MedStatement(
        source=row.source,
        row_id=row.row_id,
        raw_text=row.med_text or "",
        generic=generic,
        ingredients=ingredients,
        atc=atc,
        release=release,  # type: ignore[arg-type]
        route=_canonical_route(row.route_text),
        daily_dose_mg=daily,
        frequency=(row.freq_text or None),
        prn=prn,
        status=_status_for(row),  # type: ignore[arg-type]
        doc_date=row.doc_date,
        resolution=resolution,  # type: ignore[arg-type]
        qty=row.qty,
        days_supply=row.days_supply,
        pharmacy_id=row.pharmacy_id,
        script_type=row.script_type,
        note_text=row.note_text,
    )


def llm_candidates(text: str, lex: Lexicon, k: int = 5) -> dict:
    """The **only** options an LLM may choose from when resolving free text.

    Returns `{"ingredients": [...], "atc_classes": [...]}`, at most `k` of each,
    drawn entirely from `lex`. This is the constraint that keeps the hard rule
    "the LLM never invents drug names" enforceable in code rather than in a
    prompt: a reply outside this set is rejected and the line stays `unmapped`.

    Deliberately permits a class-level answer. "My blood thinner" has no single
    right ingredient, and `B01` plus "matches warfarin (GP), confirm" is both
    true and useful, where guessing warfarin outright is neither.
    """
    key = normalise_text(text)
    classes: list[str] = []
    for phrase, codes in LAY_TERMS.items():
        if phrase in key:
            for code in codes:
                if code not in classes:
                    classes.append(code)

    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for index in (lex.by_generic, lex.by_brand):
        for candidate_key, entry in index.items():
            if not entry.generic or entry.generic in seen:
                continue
            seen.add(entry.generic)
            scored.append((jellyfish.jaro_winkler_similarity(key, candidate_key), entry.generic))
    scored.sort(reverse=True)
    ingredients = [name for _score, name in scored[:k]]

    # A lay term that names a class should not also suggest an unrelated
    # ingredient just because the strings look alike.
    if classes:
        in_class = [e.generic for e in lex.entries
                    if e.generic and e.atc_primary
                    and any(e.atc_primary.startswith(c) for c in classes)]
        ingredients = list(dict.fromkeys(in_class))[:k] or ingredients

    return {"ingredients": ingredients, "atc_classes": classes[:k]}
