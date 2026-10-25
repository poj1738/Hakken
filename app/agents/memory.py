"""H-MEM in the product: the trust the pharmacist teaches, durable and auditable.

  - Each `(source, attribute)` trust prior (`trust.SOURCE_TRUST_PRIORS`) is a long_term
    H-MEM record, tagged `trust:<source>:<attribute>`. `fuse()` reads its trust from these
    records' confidence, so what the pharmacist teaches is what the next run uses.
  - A verdict is `HMEM.feedback()` on that record: the exact deltas (+0.05 / -0.03 /
    -0.20, clamped), the `review` tag on `wrong`, and a ledger entry with the before and
    after confidence. PLAN 5.7's deltas are H-MEM's own.
  - The verdict itself is remembered as a memory, and the Planner recalls relevant
    memories by H-MEM's hybrid retrieval before it plans. They come back in
    `RunResponse.memory_used`.

Persisted under `STATE_DIR/hmem/` live (`state.json` + `ledger.jsonl`); in memory in
SAMPLE_MODE, so an offline run writes no state.
"""

from __future__ import annotations

from app.domain.packs.medtrace.trust import SOURCE_TRUST_PRIORS
from app.engines.hmem import HMEM, MemoryRecord
from app.schemas import MemoryUsed

#: The final-score threshold for recall. The spec's default is 0.35, but absolute scores
#: depend on the embedder (conformance/README.md: only ordering is embedding-independent),
#: and the reference's deterministic mock embedder scores short clinical sentences low.
#: Measured 25 Oct: a past pharmacist verdict scores ~0.18 for RECALL_QUERY and generic
#: trust records <= 0.11, so 0.15 surfaces verdicts and not the trust table. Stated in
#: every `retrieval_reason`.
RECALL_THRESHOLD = 0.15
#: The words verdict memories and review-tagged trust records carry (keyword + tag terms).
RECALL_QUERY = "verdict review pharmacist rejected confirmed gp pharmacy patient emr dose existence"


class TrustMemory:
    def __init__(self, hmem: HMEM) -> None:
        self.hmem = hmem
        self._ids: dict[tuple[str, str], str] = {}
        for record in hmem.store.all():
            for tag in record.tags:
                if tag.startswith("trust:"):
                    _, source, attribute = tag.split(":", 2)
                    self._ids[(source, attribute)] = record.id
        for (source, attribute), prior in sorted(SOURCE_TRUST_PRIORS.items()):
            if (source, attribute) not in self._ids:
                rec = hmem.add(content=f"Trust in the {source} source for {attribute.replace('_', ' ')}",
                               source="trust.SOURCE_TRUST_PRIORS", type="factual", layer="long_term",
                               confidence=prior,
                               tags=["trust", f"source:{source}", f"attribute:{attribute}",
                                     f"trust:{source}:{attribute}"])
                self._ids[(source, attribute)] = rec.id

    def trust(self) -> dict[tuple[str, str], float]:
        """What `fuse()` reads: each record's confidence, rounded off float noise (0.7-0.2)."""
        return {key: round(self.hmem.store.get(mid).confidence, 4) for key, mid in self._ids.items()}

    def record_id(self, source: str, attribute: str) -> str | None:
        return self._ids.get((source, attribute))

    def feedback(self, source: str, attribute: str, kind: str) -> tuple[str, float, float] | None:
        """Apply one verdict to one trust record. Returns (record id, before, after), or None."""
        mid = self._ids.get((source, attribute))
        if mid is None:
            return None
        before = round(self.hmem.store.get(mid).confidence, 4)
        self.hmem.feedback(mid, kind)
        return mid, before, round(self.hmem.store.get(mid).confidence, 4)

    def remember_verdict(self, text: str, *, source: str | None, reason: str | None) -> MemoryRecord:
        tags = ["verdict"] + ([f"source:{source}"] if source else []) + ([f"reason:{reason}"] if reason else [])
        return self.hmem.add(content=text, source="pharmacist feedback", type="factual", layer="working", tags=tags)

    def recall(self, query: str) -> list[MemoryUsed]:
        result = self.hmem.query(query, threshold=RECALL_THRESHOLD)
        reason = result.trace.get("retrievalReason", "")
        return [MemoryUsed(memory_id=r.memory.id, content=r.memory.content, layer=r.memory.layer,
                           score=round(r.relevance, 4),
                           retrieval_reason=f"{reason}; threshold {RECALL_THRESHOLD} on the final score")
                for r in result.memories]
