# Ported from Meterless H-MEM, reference/src/{conflictDetection,sleepCycle,dreaming,index}.ts
# (github.com/Meterless/Meterless, engines/hmem, commit 1742dec), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""H-MEM services: conflicts (AGENTS.md 10), sleep (8), dreaming (7), and the HMEM facade.

Behaviour contracts the conformance suite pins:
  - conflict resolution marks the loser `superseded_by` and NEVER deletes; auto-resolve
    only at decision confidence >= 0.70, else the conflict queues;
  - sleep `preview()` mutates nothing; derived, superseding and hub records are never
    archived; `execute()` takes a backup first and returns its id;
  - dreaming materialises nothing before `approve()`; an approved insight/invariant is
    a long_term record with `derived_from` lineage.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.engines.hmem.core import (
    DAY_MS,
    DEFAULTS,
    MemoryRecord,
    MemoryRetrievalService,
    MemoryStoreService,
    QueryResult,
    TrustLedgerService,
    clamp01,
    cosine,
    jaccard,
    snapshot,
)

# Verbatim from the reference, including the precedence of the third pattern's alternation.
OPPOSING_PAIRS = [
    (re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
    (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
    (re.compile(r"\bprefer[s]?\b", re.I), re.compile(r"\bavoid[s]?|dislike[s]?\b", re.I)),
    (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
    (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I)),
]
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
HUB_THRESHOLD = 3


@dataclass
class ConflictRecord:
    id: str
    memory_a: str
    memory_b: str
    reason: str
    confidence: float
    resolved: bool = False
    resolution: str | None = None


class ConflictDetectionService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int],
                 actor: str) -> None:
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._conflicts: list[ConflictRecord] = []
        self._seq = 0

    def scan(self) -> list[ConflictRecord]:
        found = []
        records = self._store.all()
        for i, a in enumerate(records):
            for b in records[i + 1:]:
                conflict = self._check(a, b)
                if conflict:
                    found.append(conflict)
                    self._conflicts.append(conflict)
                    self._ledger.log(conflict.memory_a, "conflict_detected", self._actor, details={
                        "with": conflict.memory_b, "reason": conflict.reason, "confidence": conflict.confidence})
        return found

    def _check(self, a: MemoryRecord, b: MemoryRecord) -> ConflictRecord | None:
        if b.id in (a.supersedes, a.superseded_by) or a.id in (b.supersedes, b.superseded_by):
            return None  # an intended replacement, not a conflict
        sim = cosine(a.embedding, b.embedding)
        reason, confidence = "", 0.0
        for p, q in OPPOSING_PAIRS:
            if (p.search(a.content) and q.search(b.content)) or (q.search(a.content) and p.search(b.content)):
                if sim > 0.5:
                    reason, confidence = "opposing phrase pair on similar content", 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            nums_a, nums_b = _NUMBER.findall(a.content), _NUMBER.findall(b.content)
            if nums_a and nums_b and nums_a != nums_b:
                reason, confidence = "high-similarity conflicting numeric values", 0.55 + 0.25 * sim
        if not reason:
            return None
        if any(e in b.entities for e in a.entities):
            confidence += 0.1
        if a.domain == b.domain:
            confidence += 0.05
        if b.id in a.related_to:
            confidence -= 0.1  # an explicit relation lowers false positives
        self._seq += 1
        return ConflictRecord(id=f"conflict-{self._seq}", memory_a=a.id, memory_b=b.id, reason=reason,
                              confidence=clamp01(confidence))

    def auto_resolve(self, conflict: ConflictRecord) -> str:
        a, b = self._store.get(conflict.memory_a), self._store.get(conflict.memory_b)
        assert a is not None and b is not None

        def score_of(m: MemoryRecord) -> float:
            return (0.3 * (m.last_accessed / max(1, self._clock())) + 0.2 * min(1, m.access_count / 10)
                    + 0.25 * m.confidence + 0.1 * min(1, len(m.content) / 200)
                    + 0.15 * (1 if m.provenance.get("origin") == "user_correction" else 0.5))
        sa, sb = score_of(a), score_of(b)
        margin = abs(sa - sb) / max(sa, sb)
        decision_confidence = clamp01(conflict.confidence * 0.6 + margin * 0.8)
        if decision_confidence < DEFAULTS["conflictAutoResolveGate"]:
            return "queued"
        winner, loser = (a, b) if sa >= sb else (b, a)
        prev = snapshot(loser)
        loser.superseded_by = winner.id  # kept and penalised, never deleted
        conflict.resolved = True
        conflict.resolution = "keep_a" if winner.id == conflict.memory_a else "keep_b"
        self._ledger.log(loser.id, "conflict_resolved", self._actor, previousState=prev, newState=snapshot(loser),
                         details={"conflictId": conflict.id, "winner": winner.id,
                                  "decisionConfidence": round(decision_confidence, 3)})
        self._store.persist()
        return "resolved"

    def queue(self) -> list[ConflictRecord]:
        return [c for c in self._conflicts if not c.resolved]


@dataclass
class SleepPreview:
    to_consolidate: list[str] = field(default_factory=list)
    to_archive: list[str] = field(default_factory=list)
    to_synthesize: list[list[str]] = field(default_factory=list)


@dataclass
class SleepReport:
    backup_id: str
    consolidated: int
    archived: int
    synthesized: int
    action_log: list[str]


class SleepCycleService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int],
                 actor: str) -> None:
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._backups: dict[str, tuple[list[MemoryRecord], int]] = {}
        self._backup_seq = 0

    def preview(self) -> SleepPreview:
        """The full plan. Mutates nothing."""
        now = self._clock()
        records = self._store.all()
        referenced: set[str] = set()
        for m in records:
            referenced.update(m.related_to)
            if m.supersedes:
                referenced.add(m.supersedes)
            referenced.update(m.derived_from or [])
        consolidate = [m.id for m in records if m.layer == "short_term"
                       and now - m.last_accessed >= DEFAULTS["consolidationDays"] * DAY_MS]

        def archivable(m: MemoryRecord) -> bool:
            if not (now - m.timestamp >= DEFAULTS["archiveMinDays"] * DAY_MS
                    and m.access_count <= DEFAULTS["archiveMaxAccess"] and m.id not in referenced):
                return False
            # Guardrails (8.2): never archive a superseding record, a derived one, or a hub.
            return not (m.supersedes or (m.derived_from or []) or len(m.related_to) >= HUB_THRESHOLD)
        archive = [m.id for m in records if archivable(m)]
        synthesize: list[list[str]] = []
        used: set[str] = set()
        for i, seed in enumerate(records):
            if seed.id in used:
                continue
            group = [seed] + [o for o in records[i + 1:] if o.id not in used
                              and cosine(seed.embedding, o.embedding) >= DEFAULTS["synthesisCosine"]]
            if len(group) >= 2:
                used.update(g.id for g in group)
                synthesize.append([g.id for g in group])
        return SleepPreview(consolidate, archive, synthesize)

    def execute(self, preview: SleepPreview | None = None) -> SleepReport:
        plan = preview or self.preview()
        self._backup_seq += 1
        backup_id = f"backup-{self._backup_seq}"
        self._backups[backup_id] = self._store.snapshot_all()
        log = [f"backup {backup_id} created"]
        for id_ in plan.to_consolidate:
            if self._store.get(id_):
                self._store.promote(id_, "long_term")
                self._ledger.log(id_, "sleep_consolidate", self._actor, details={"from": "short_term", "to": "long_term"})
                log.append(f"consolidated {id_}")
        for id_ in plan.to_archive:
            m = self._store.get(id_)
            if m:
                self._ledger.log(id_, "sleep_archive", self._actor,
                                 details={"age": self._clock() - m.timestamp, "accessCount": m.access_count})
                self._store.delete(id_, "sleep archive")
                log.append(f"archived {id_}")
        synthesized = 0
        for group in plan.to_synthesize:
            members = [m for m in (self._store.get(i) for i in group) if m]
            if len(members) < 2:
                continue
            merged = self._store.add(
                content="Synthesis: " + " | ".join(m.content for m in members), type="factual", layer="long_term",
                tags=sorted({t for m in members for t in m.tags}), confidence=max(m.confidence for m in members),
                source="sleep:synthesis", derived_from=[m.id for m in members],
                provenance={"origin": "sleep_synthesis", "learnedAt": self._clock(),
                            "label": f"synthesized from {len(members)} memories"})
            self._ledger.log(merged.id, "sleep_synthesize", self._actor, details={"sources": group})
            for m in members:
                self._store.delete(m.id, "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged.id} from {', '.join(group)}")
        self._store.persist()
        return SleepReport(backup_id, len(plan.to_consolidate), len(plan.to_archive), synthesized, log)

    def restore(self, backup_id: str) -> None:
        if backup_id not in self._backups:
            raise KeyError(f"H-MEM: unknown backup {backup_id}")
        records, seq = self._backups[backup_id]
        self._store.restore_all(records, seq)
        self._ledger.log("*", "restore", self._actor, details={"backupId": backup_id})


@dataclass
class DreamProposal:
    id: str
    type: str
    content: str
    derived_from: list[str]
    status: str = "proposed"
    suggested_domain: str | None = None


class DreamingService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int],
                 actor: str) -> None:
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._proposals: dict[str, DreamProposal] = {}
        self._seq = 0

    @staticmethod
    def _relatedness(a: MemoryRecord, b: MemoryRecord) -> float:
        return (0.5 * max(0.0, cosine(a.embedding, b.embedding)) + 0.2 * jaccard(a.tags, b.tags)
                + 0.1 * (1 if a.domain == b.domain else 0) + 0.2 * jaccard(a.entities, b.entities))

    def _cluster(self) -> list[list[MemoryRecord]]:
        records, used, clusters = self._store.all(), set(), []
        for seed in records:
            if seed.id in used:
                continue
            group = [seed] + [o for o in records if o.id != seed.id and o.id not in used
                              and self._relatedness(seed, o) >= DEFAULTS["dreamRelatedness"]]
            if len(group) >= DEFAULTS["dreamClusterMinSize"]:
                used.update(g.id for g in group)
                clusters.append(group)
        return clusters

    def dream(self) -> list[DreamProposal]:
        created: list[DreamProposal] = []
        cap = int(DEFAULTS["maxDreamProposalsPerType"])

        def propose(type_: str, content: str, derived_from: list[str], suggested: str | None = None) -> None:
            self._seq += 1
            p = DreamProposal(id=f"dream-{self._seq}", type=type_, content=content, derived_from=derived_from,
                              suggested_domain=suggested)
            self._proposals[p.id] = p
            created.append(p)
            self._ledger.log(p.id, "dream_proposed", self._actor, details={"type": type_, "derivedFrom": derived_from})

        for cluster in self._cluster()[:cap]:
            domains = "/".join(dict.fromkeys(m.domain for m in cluster))
            propose("insight", f"Across {len(cluster)} related memories ({domains}): "
                    + " + ".join(m.content for m in cluster), [m.id for m in cluster])
        n = 0
        for m in self._store.all():
            if n >= cap:
                break
            if m.domain != "general":
                continue
            suggested = self._store.classify_domain(m.content, m.tags, m.type)
            if suggested != "general":
                propose("domain", f'Reclassify "{m.content[:60]}" as {suggested}', [m.id], suggested)
                n += 1
        by_domain: dict[str, list[MemoryRecord]] = {}
        for m in self._store.all():
            if m.type in ("preference", "personal") or "event:user_correction" in m.tags:
                by_domain.setdefault(m.domain, []).append(m)
        n = 0
        for domain, items in by_domain.items():
            if n >= cap:
                break
            if len(items) < 2:
                continue
            propose("invariant", f"Stable pattern in {domain}: " + "; ".join(m.content for m in items),
                    [m.id for m in items])
            n += 1
        return created

    def pending(self) -> list[DreamProposal]:
        return [p for p in self._proposals.values() if p.status == "proposed"]

    def approve(self, proposal_id: str) -> MemoryRecord | None:
        p = self._proposals.get(proposal_id)
        if p is None or p.status != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p.status = "approved"
        self._ledger.log(proposal_id, "dream_approved", self._actor, details={"type": p.type})
        if p.type == "domain":
            for id_ in p.derived_from:
                if self._store.get(id_) and p.suggested_domain:
                    self._store.update(id_, domain=p.suggested_domain)
            return None
        return self._store.add(
            content=p.content, type="factual" if p.type == "insight" else "preference", layer="long_term",
            tags=[f"dream:{p.type}"], confidence=0.75, source="dreaming", derived_from=p.derived_from,
            provenance={"origin": "dream", "learnedAt": self._clock(), "label": f"approved {p.type} proposal"})

    def reject(self, proposal_id: str) -> None:
        p = self._proposals.get(proposal_id)
        if p is None or p.status != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p.status = "rejected"  # logged, not materialised
        self._ledger.log(proposal_id, "dream_rejected", self._actor, details={"type": p.type})


class HMEM:
    """The facade (index.ts): `HMEM(clock=...)` with add/query/feedback and the services."""

    def __init__(self, *, clock: Callable[[], int] | None = None, persist_dir: Path | str | None = None,
                 actor: str = "system") -> None:
        self.clock = clock or (lambda: int(time.time() * 1000))
        folder = Path(persist_dir) if persist_dir else None
        self.ledger = TrustLedgerService(self.clock, folder)
        self.store = MemoryStoreService(self.clock, self.ledger, actor, folder)
        self.retrieval = MemoryRetrievalService(self.store, self.ledger, self.clock, actor)
        self.conflicts = ConflictDetectionService(self.store, self.ledger, self.clock, actor)
        self.sleep = SleepCycleService(self.store, self.ledger, self.clock, actor)
        self.dreaming = DreamingService(self.store, self.ledger, self.clock, actor)

    def add(self, **kwargs) -> MemoryRecord:
        return self.store.add(**kwargs)

    def query(self, query: str, *, top_n: int | None = None, threshold: float | None = None,
              chat_id: str | None = None) -> QueryResult:
        return self.retrieval.query(query, top_n=top_n, threshold=threshold, chat_id=chat_id)

    def feedback(self, memory_id: str, kind: str) -> None:
        self.retrieval.feedback(memory_id, kind)
