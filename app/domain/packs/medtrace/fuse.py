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

from datetime import date

from app.domain.packs.medtrace.types import EvidenceState, FusedMed, MedStatement


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
    """
    raise NotImplementedError("Arpon: fuse.py")
