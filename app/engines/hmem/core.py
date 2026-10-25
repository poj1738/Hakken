# Ported from Meterless H-MEM, reference/src/{types,embeddings,memoryStore,trustLedger,memoryRetrieval}.ts
# (github.com/Meterless/Meterless, engines/hmem, commit 1742dec), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""H-MEM core: record shape, the deterministic embedder, the store, the ledger, retrieval.

Exact-tier numbers (AGENTS.md 6.1, 9.2), matched to the reference:

    raw   = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain
          + 0.15*entity   + 0.05*layer   + 0.05*recency - 0.20*superseded
    score = clamp01(raw) * confidence      # confidence multiplies AFTER the sum
    threshold 0.35 on the final score, top N 5
    feedback: helpful +0.05 (+1 accessCount), not_helpful -0.03, wrong -0.20 (+ "review" tag), clamped
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

MemoryType = Literal["personal", "factual", "preference", "general"]
MemoryLayer = Literal["short_term", "working", "long_term"]
FeedbackKind = Literal["helpful", "not_helpful", "wrong"]

FEEDBACK_DELTAS: dict[str, float] = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.2}
DEFAULTS: dict[str, float] = {
    "retrievalTopN": 5, "retrievalThreshold": 0.35, "consolidationDays": 7, "archiveMinDays": 30,
    "archiveMaxAccess": 2, "synthesisCosine": 0.82, "dreamClusterMinSize": 2, "dreamRelatedness": 0.35,
    "maxDreamProposalsPerType": 8, "conflictAutoResolveGate": 0.7, "entityCap": 10, "relatedCap": 5,
    "recencyDays": 14,
}
DAY_MS = 24 * 60 * 60 * 1000
LEDGER_ACTIONS = (
    "create", "read", "update", "delete", "feedback", "promote", "demote", "merge", "conflict_detected",
    "conflict_resolved", "sleep_consolidate", "sleep_archive", "sleep_synthesize", "dream_proposed",
    "dream_approved", "dream_rejected", "restore",
)


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


# -- deterministic embedder (embeddings.ts) ----------------------------------------

DIM = 64
_NON_WORD = re.compile(r"[^a-z0-9\s]")


def tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", _NON_WORD.sub(" ", text.lower())) if len(t) > 1]


def _fnv1a(text: str) -> int:
    h = 0x811C9DC5
    for ch in text:  # tokens are ASCII after tokenize(), so ord() == charCodeAt()
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in tokenize(text):
        h = _fnv1a(token)
        sign = 1 if (h >> 8) % 2 == 0 else -1
        vec[h % DIM] += sign * (1 + ((h >> 16) % 8) / 8)
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0 else [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both unit-length


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


# -- record --------------------------------------------------------------------------


@dataclass
class MemoryRecord:
    id: str
    content: str
    type: str
    layer: str
    timestamp: int
    last_accessed: int
    access_count: int
    tags: list[str]
    embedding: list[float]
    confidence: float          # mandatory
    source: str                # mandatory: construction rejects records without it
    provenance: dict[str, Any]  # mandatory for new writes
    domain: str
    namespace: str
    entities: list[str]        # cap 10
    related_to: list[str]      # cap 5
    chat_id: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    derived_from: list[str] | None = None


def snapshot(r: MemoryRecord) -> dict[str, Any]:
    out = copy.deepcopy(asdict(r))
    out.pop("embedding", None)
    return out


# -- ledger (trustLedger.ts) ---------------------------------------------------------


class TrustLedgerService:
    """Append-only. Entries are never mutated or deleted."""

    def __init__(self, clock: Callable[[], int], persist_dir: Path | None = None) -> None:
        self._clock = clock
        self._entries: list[dict[str, Any]] = []
        self._file = persist_dir / "ledger.jsonl" if persist_dir else None
        if self._file and self._file.exists():
            self._entries = [json.loads(line) for line in self._file.read_text(encoding="utf-8").splitlines() if line]

    def log(self, memory_id: str, action: str, actor: str, **extra: Any) -> dict[str, Any]:
        if action not in LEDGER_ACTIONS:
            raise ValueError(f"H-MEM: {action!r} is not one of the 17 canonical ledger actions")
        entry = {"memoryId": memory_id, "action": action, "actor": actor, "timestamp": self._clock(),
                 **{k: v for k, v in extra.items() if v is not None}}
        self._entries.append(entry)
        if self._file:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return [e for e in self._entries if e["memoryId"] == memory_id]

    def all(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self._entries:
            out[e["action"]] = out.get(e["action"], 0) + 1
        return out


# -- store (memoryStore.ts) ----------------------------------------------------------

TECH_TERMS = ["react", "python", "typescript", "javascript", "rust", "sqlite", "postgres", "indexeddb", "node",
              "docker", "graphql", "redis", "webrtc", "tauri", "electron", "llm", "embedding"]
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "tech": ["code", "bug", "api", "database", "deploy", "framework", "library", "server", *TECH_TERMS],
    "work": ["meeting", "deadline", "client", "project", "sprint", "review", "report"],
    "personal": ["family", "hobby", "prefer", "like", "dislike", "morning", "evening"],
}
_CAPITALISED = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")
_CORRECTION = re.compile(r"\b(actually|instead|no longer|not anymore|changed to|correction)\b", re.IGNORECASE)


class MemoryStoreService:
    def __init__(self, clock: Callable[[], int], ledger: TrustLedgerService, actor: str,
                 persist_dir: Path | None = None) -> None:
        self._clock = clock
        self._ledger = ledger
        self._actor = actor
        self._records: dict[str, MemoryRecord] = {}
        self._seq = 0
        self._file = persist_dir / "state.json" if persist_dir else None
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
        if self._file and self._file.exists():
            saved = json.loads(self._file.read_text(encoding="utf-8"))
            self._seq = saved["seq"]
            for r in saved["records"]:
                self._records[r["id"]] = MemoryRecord(**r)

    def persist(self) -> None:
        if not self._file:
            return
        records = [asdict(self._records[k]) for k in sorted(self._records)]
        self._file.write_text(json.dumps({"seq": self._seq, "records": records}, indent=2) + "\n", encoding="utf-8")

    def add(self, *, content: str, source: str, type: str = "general", layer: str = "working",
            tags: list[str] | None = None, confidence: float | None = None, provenance: dict[str, Any] | None = None,
            chat_id: str | None = None, supersedes: str | None = None,
            derived_from: list[str] | None = None) -> MemoryRecord:
        if not source or not source.strip():
            raise ValueError("H-MEM: a memory record with no source must be rejected by construction (AGENTS.md section 2)")
        now = self._clock()
        self._seq += 1
        tags = list(tags or [])
        domain = self.classify_domain(content, tags, type)
        record = MemoryRecord(
            id=f"mem-{self._seq}", content=content, type=type, layer=layer, timestamp=now, last_accessed=now,
            access_count=0, tags=tags, embedding=embed(content),
            confidence=clamp01(0.7 if confidence is None else confidence), source=source,
            provenance=provenance or {"origin": "manual", "learnedAt": now, "label": source}, domain=domain,
            namespace=self._namespace(domain, type), entities=self.extract_entities(content), related_to=[],
            chat_id=chat_id, supersedes=supersedes, derived_from=derived_from)
        self._discover_relationships(record)
        self._records[record.id] = record
        self._ledger.log(record.id, "create", self._actor, newState=snapshot(record))
        self.persist()
        return record

    def get(self, id_: str) -> MemoryRecord | None:
        return self._records.get(id_)

    def all(self) -> list[MemoryRecord]:
        return list(self._records.values())

    def update(self, id_: str, **patch: Any) -> MemoryRecord:
        rec = self._must(id_)
        prev = snapshot(rec)
        for k, v in patch.items():
            setattr(rec, k, v)
        self._ledger.log(id_, "update", self._actor, previousState=prev, newState=snapshot(rec))
        self.persist()
        return rec

    def delete(self, id_: str, reason: str) -> None:
        rec = self._must(id_)
        del self._records[id_]
        self._ledger.log(id_, "delete", self._actor, previousState=snapshot(rec), details={"reason": reason})
        self.persist()

    def touch(self, id_: str) -> None:
        rec = self._must(id_)
        rec.last_accessed = self._clock()
        rec.access_count += 1

    def promote(self, id_: str, layer: str) -> None:
        rec = self._must(id_)
        prev = snapshot(rec)
        rec.layer = layer
        self._ledger.log(id_, "promote", self._actor, previousState=prev, newState=snapshot(rec))
        self.persist()

    def restore_all(self, records: list[MemoryRecord], seq: int) -> None:
        self._records = {r.id: copy.deepcopy(r) for r in records}
        self._seq = seq
        self.persist()

    def snapshot_all(self) -> tuple[list[MemoryRecord], int]:
        return copy.deepcopy(list(self._records.values())), self._seq

    def _must(self, id_: str) -> MemoryRecord:
        rec = self._records.get(id_)
        if rec is None:
            raise KeyError(f"H-MEM: unknown memory id {id_}")
        return rec

    def classify_domain(self, content: str, tags: list[str], type_: str) -> str:
        for t in tags:
            if t.startswith("project:"):
                return t[len("project:"):]
            if t.startswith("tech:"):
                return "tech"
        tokens = set(tokenize(content))
        best, best_score = "general", 0
        for domain, kws in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in tokens)
            if domain == "personal" and type_ in ("personal", "preference"):
                score += 1
            if score > best_score:
                best, best_score = domain, score
        return best if best_score > 0 else "general"

    @staticmethod
    def _namespace(domain: str, type_: str) -> str:
        bucket = "profile" if type_ in ("preference", "personal") else "facts" if type_ == "factual" else "notes"
        return f"{domain}/{bucket}"

    def extract_entities(self, content: str) -> list[str]:
        entities: list[str] = []
        for t in tokenize(content):
            if t in TECH_TERMS and t not in entities:
                entities.append(t)
        for m in _CAPITALISED.finditer(content):
            norm = m.group(1).lower()
            if norm not in ("the", "this", "that", "with") and norm not in entities:
                entities.append(norm)
        return entities[: int(DEFAULTS["entityCap"])]

    def _discover_relationships(self, record: MemoryRecord) -> None:
        cap = int(DEFAULTS["relatedCap"])
        for other in self._records.values():
            if len(record.related_to) >= cap:
                break
            shared = [e for e in other.entities if e in record.entities]
            sim = cosine(record.embedding, other.embedding)
            if not record.supersedes and sim > 0.85 and _CORRECTION.search(record.content):
                record.supersedes = other.id
                continue
            if shared and other.domain == record.domain:
                record.related_to.append(other.id)
                if len(other.related_to) < cap and record.id not in other.related_to:
                    other.related_to.append(record.id)  # bidirectional link


# -- retrieval (memoryRetrieval.ts) --------------------------------------------------

LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}


@dataclass
class RetrievedMemory:
    memory: MemoryRecord
    relevance: float


@dataclass
class QueryResult:
    memories: list[RetrievedMemory]
    context: str
    trace: dict[str, Any] = field(default_factory=dict)


class MemoryRetrievalService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int],
                 actor: str) -> None:
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor

    def _score(self, m: MemoryRecord, q_emb: list[float], q_tokens: list[str], q_entities: list[str],
               q_domain: str) -> float:
        semantic = clamp01(cosine(q_emb, m.embedding))
        keyword = jaccard(q_tokens, tokenize(m.content))
        tag = jaccard(q_tokens, [t.lower() for t in m.tags])
        domain = 1 if m.domain == q_domain else 0
        entity = jaccard(q_entities, m.entities)
        layer = LAYER_WEIGHT[m.layer]
        recency = math.exp(-((self._clock() - m.last_accessed) / DAY_MS) / DEFAULTS["recencyDays"])
        superseded = 1 if m.superseded_by else 0
        raw = (0.35 * semantic + 0.2 * keyword + 0.1 * tag + 0.1 * domain
               + 0.15 * entity + 0.05 * layer + 0.05 * recency - 0.2 * superseded)
        return clamp01(raw) * m.confidence

    def score_one(self, memory: MemoryRecord, query: str) -> float:
        return self._score(memory, embed(query), tokenize(query)[:8], self._store.extract_entities(query),
                           self._store.classify_domain(query, [], "general"))

    def query(self, query: str, *, top_n: int | None = None, threshold: float | None = None,
              chat_id: str | None = None) -> QueryResult:
        q_emb, q_tokens = embed(query), tokenize(query)[:8]
        q_entities = self._store.extract_entities(query)
        q_domain = self._store.classify_domain(query, [], "general")
        threshold = DEFAULTS["retrievalThreshold"] if threshold is None else threshold
        top_n = int(DEFAULTS["retrievalTopN"] if top_n is None else top_n)
        scored = []
        for m in self._store.all():
            if chat_id and m.chat_id and m.chat_id != chat_id:
                continue
            s = self._score(m, q_emb, q_tokens, q_entities, q_domain)
            if s >= threshold:
                scored.append(RetrievedMemory(m, s))
        scored.sort(key=lambda r: (-r.relevance, r.memory.id))
        top = scored[:top_n]
        for r in top:
            self._store.touch(r.memory.id)
            self._ledger.log(r.memory.id, "read", self._actor, details={"query": query})
        strategy = ("minimal" if len(top) <= 1 else "personal"
                    if any(r.memory.type in ("personal", "preference") for r in top) else "comprehensive")
        return QueryResult(memories=top, context=self.format_reinjection(top), trace={
            "retrievalReason": f'hybrid ranking for "{query}" (domain: {q_domain})', "strategy": strategy,
            "scores": {r.memory.id: round(r.relevance, 4) for r in top}})

    @staticmethod
    def format_reinjection(items: list[RetrievedMemory]) -> str:
        if not items:
            return ""
        by_domain: dict[str, list[RetrievedMemory]] = {}
        for it in items:
            by_domain.setdefault(it.memory.domain, []).append(it)
        lines = ["[MEMORY CONTEXT]"]
        for domain in sorted(by_domain):
            lines.append(f"## {domain}")
            for it in by_domain[domain]:
                m = it.memory
                marker = {"long_term": "LT", "working": "WK"}.get(m.layer, "ST")
                ents = f" (entities: {', '.join(m.entities)})" if m.entities else ""
                lines.append(f"- [{marker}] {m.content}{ents} <{m.id}>")
        lines.append("[/MEMORY CONTEXT]")
        return "\n".join(lines)

    def feedback(self, memory_id: str, kind: str) -> None:
        m = self._store.get(memory_id)
        if m is None:
            raise KeyError(f"H-MEM: unknown memory id {memory_id}")
        prev = snapshot(m)
        if kind == "helpful":
            m.access_count += 1
        m.confidence = clamp01(m.confidence + FEEDBACK_DELTAS[kind])
        if kind == "wrong" and "review" not in m.tags:
            m.tags.append("review")
        self._ledger.log(memory_id, "feedback", self._actor, previousState=prev, newState=snapshot(m),
                         details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]})
        self._store.persist()
