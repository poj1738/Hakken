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

from app.domain.packs.medtrace.types import Lexicon, MedStatement, SourceRow


def normalise_med(row: SourceRow, lex: Lexicon) -> MedStatement:
    """Resolve one harmonised row into a canonical medication statement.

    Resolution, in order, recorded in `MedStatement.resolution`:
      1. `code` -- `med_code` against the lexicon by `code_system` (AMT MP/MPP/TPP
         or PBS). Joining on codes rather than names is a reference-data rule:
         `drug_name` does not map 1:1 to the AMT preferred term (PLAN 3).
      2. `lexicon` -- exact match on brand, generic, or the salt-stripped generic,
         so "atorvastatin calcium" meets "atorvastatin".
      3. `fuzzy` -- Jaro-Winkler / trigram above a threshold, score retained.
      4. `unmapped` -- shown as unresolved. Never guessed.

    Also:
      - **Decomposes combinations** into `ingredients`, which is what makes
        Coversyl Plus + perindopril detectable as a duplication rather than two
        unrelated drugs.
      - Computes total `daily_dose_mg` from `dose_text`, `strength_text` and
        `freq_text`, parsing bd/tds/qid/mane/nocte/weekly and PRN, and handling
        **mcg vs mg** -- a 1000x error that lands on digoxin and levothyroxine,
        both high-risk.
      - Sets `release` (IR/MR), because oxycodone CR and IR at the same daily dose
        are a real formulation discrepancy and not a notation difference.
      - Maps `status_text` to `active`/`ceased`/`unknown` per source: the GP's
        `ceased`, the EMR's `discharge_action`, and the patient's
        `yes/no/unsure`, where `unsure` is `unknown` and never `ceased`.
    """
    raise NotImplementedError("Arpon: normalise.py")


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
    raise NotImplementedError("Arpon: normalise.py")
