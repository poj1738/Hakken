"""World Model engine: a Python port of the Meterless World Model (Apache-2.0).

Definition of done is the official conformance runner's 8 inline checks, ported in
`tests/engines/test_world_model_conformance.py`. Merge band 0.85, per the runner
and against `docs/ingest-pipeline.md` (docs/DECISIONS.md, 23 Oct).
"""

from app.engines.world_model.model import GraphView, ProvenanceError, WorldModel
from app.engines.world_model.resolve import decide, jaccard, levenshtein, name_similarity
from app.engines.world_model.stable_ids import (
    canonical_json,
    entity_id_from_name,
    external_id,
    normalize_name,
    sha256_hex,
)

# The conformance runner's required export names (camelCase), as aliases.
entityIdFromName = entity_id_from_name
normalizeName = normalize_name

__all__ = [
    "GraphView", "ProvenanceError", "WorldModel", "canonical_json", "decide", "entityIdFromName",
    "entity_id_from_name", "external_id", "jaccard", "levenshtein", "name_similarity", "normalizeName",
    "normalize_name", "sha256_hex",
]
