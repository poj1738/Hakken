"""H-MEM engine: a Python port of the Meterless H-MEM reference (Apache-2.0).

Definition of done is the official conformance suite's 13 vectors
(`tests/engines/vectors/hmem_vectors.json`, run by `tests/engines/test_hmem_conformance.py`).
"""

from app.engines.hmem.core import (
    DEFAULTS,
    FEEDBACK_DELTAS,
    MemoryRecord,
    QueryResult,
    RetrievedMemory,
    clamp01,
    cosine,
    embed,
    jaccard,
    tokenize,
)
from app.engines.hmem.services import HMEM, ConflictRecord, DreamProposal, SleepPreview, SleepReport

__all__ = [
    "DEFAULTS", "FEEDBACK_DELTAS", "HMEM", "ConflictRecord", "DreamProposal", "MemoryRecord", "QueryResult",
    "RetrievedMemory", "SleepPreview", "SleepReport", "clamp01", "cosine", "embed", "jaccard", "tokenize",
]
