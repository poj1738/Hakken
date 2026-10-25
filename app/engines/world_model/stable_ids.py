# Ported from Meterless World Model, reference/src/stableIds.ts
# (github.com/Meterless/Meterless, engines/world-model), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""Stable, deterministic, content-addressable ids (docs/stable-ids.md).

Same input, same id, on every machine, every re-run, every backfill -- and the
same id the TypeScript reference produces, because sha-256 and the canonical
JSON below match it byte for byte for the values we use.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any

_COMBINING = re.compile("[̀-ͯ]")
_ZERO_WIDTH = re.compile("[​-‍﻿]")
_WHITESPACE = re.compile(r"\s+")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _js_scalar(value: Any) -> str:
    """`JSON.stringify` of a scalar: integral floats print as integers, non-ASCII unescaped."""
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return str(int(value))
        return json.dumps(value)
    return json.dumps(value, ensure_ascii=False)


def canonical_json(value: Any) -> str:
    """Deterministic JSON: object keys sorted, absent (None) members dropped.

    TypeScript drops `undefined` members; Python has no undefined, so a key whose
    value is None is treated as absent. Lists keep their order.
    """
    if isinstance(value, dict):
        keys = sorted(k for k, v in value.items() if v is not None)
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical_json(value[k]) for k in keys) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    return _js_scalar(value)


def normalize_name(name: str) -> str:
    """NFKD -> strip combining marks -> strip zero-width -> lowercase -> collapse whitespace -> trim.

    "José García" (with an NBSP) and "jose garcia" normalise identically; "Acme Corp"
    and "Acme Corporation" stay different: normalisation never abbreviates or stems.
    """
    out = unicodedata.normalize("NFKD", name)
    out = _COMBINING.sub("", out)
    out = _ZERO_WIDTH.sub("", out)
    return _WHITESPACE.sub(" ", out.lower()).strip()


def external_id(type_: str, system: str, id_: str) -> str:
    """Externally keyed entity or context: the literal grammar `type:system:externalId`."""
    return f"{type_}:{system}:{id_}"


def entity_id_from_name(type_: str, name: str) -> str:
    """Name-keyed entity: `ent_` + first 16 hex of sha256(`type:normalizeName(name)`). Type is part of the key."""
    return "ent_" + sha256_hex(f"{type_}:{normalize_name(name)}")[:16]


def context_id_from_attrs(type_: str, attrs: dict[str, Any], parent: str | None = None) -> str:
    """Attr-keyed context, hashed WITH its parent (week:14 under season:145 != under season:144)."""
    return "ctx_" + sha256_hex(f"{type_}:{canonical_json(attrs)}:{parent or ''}")[:16]


def relationship_id(from_: str, type_: str, to: str, context: str | None = None,
                    valid_from: str | None = None) -> str:
    """hash(from + type + to + context? + validFrom?). Re-adding the same edge is a no-op."""
    return "rel_" + sha256_hex(f"{from_}|{type_}|{to}|{context or ''}|{valid_from or ''}")[:16]


def fact_id(about: str, predicate: str, value: Any, asserted_at: str, source_kind: str,
            source_url: str | None = None) -> str:
    """Content-addressed dedupe key. Asserting the identical fact twice is a no-op."""
    return "fact_" + sha256_hex(
        f"{about}|{predicate}|{canonical_json(value)}|{asserted_at}|{source_kind}|{source_url or ''}")[:16]
