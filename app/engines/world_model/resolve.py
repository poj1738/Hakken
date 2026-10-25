# Ported from Meterless World Model, reference/src/resolve.ts
# (github.com/Meterless/Meterless, engines/world-model), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""Entity resolution: banded merge thresholds (AGENTS.md, merge detection).

    similarity >= 0.85          -> auto-merge   (0.85 EXACTLY is auto-merge)
    0.82 <= similarity < 0.85   -> operator review queue (0.82 EXACTLY queues)
    similarity < 0.82           -> new entity

The prose spec (`docs/ingest-pipeline.md`) says >=0.92 / 0.82-0.92 / <0.82. The
conformance runner (`band-001`) asserts 0.85 is auto-merge and 0.84 is review, and
the engine's own rule is that the suite is the definition of done. So 0.85 it is --
see docs/DECISIONS.md, 23 Oct. Never weaken band-001 to make anything pass.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from app.engines.world_model.stable_ids import normalize_name

ResolutionDecision = Literal["auto-merge", "review", "new"]
AUTO_MERGE_AT = 0.85
REVIEW_LOWER = 0.82


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = curr
    return prev[len(b)]


def name_similarity(raw_a: str, raw_b: str) -> float:
    """1 - levenshtein / max length, on NORMALISED names, so accents and spacing never inflate distance."""
    a, b = normalize_name(raw_a), normalize_name(raw_b)
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return 1.0 - levenshtein(a, b) / longest


def decide(similarity: float, auto_merge_at: float = AUTO_MERGE_AT,
           review_lower: float = REVIEW_LOWER) -> ResolutionDecision:
    if similarity >= auto_merge_at:
        return "auto-merge"  # the boundary value merges
    if similarity >= review_lower:
        return "review"      # the boundary value queues
    return "new"


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Clustering gate for ingest: entity-overlap Jaccard >= 0.5 co-clusters two observations."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)
