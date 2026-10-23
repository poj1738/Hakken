"""DomainPack interface -- what a track-specific pack must provide.

A pack supplies sources.yaml, prompts/, output_schema.py, safety.py,
examples/ and evaluation.py. Switching tracks means switching DOMAIN_PACK,
not rewriting plumbing.

PHASE 6 STUB (contract sketch only; filled when we pick a track).
"""

from __future__ import annotations
