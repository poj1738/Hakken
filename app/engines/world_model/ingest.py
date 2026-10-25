# Ported from Meterless World Model, reference/src/ingest.ts
# (github.com/Meterless/Meterless, engines/world-model), Apache License 2.0.
# Python port by Team Hakken, 2026-10-25.
"""The canonical ingest pipeline (AGENTS.md 4.1). Idempotency contract: re-running
the same batch produces the same world state and an empty diff. Every derived
timestamp comes from the OBSERVATION, never the wall clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.engines.world_model.resolve import jaccard
from app.engines.world_model.stable_ids import canonical_json, sha256_hex
from app.engines.world_model.store import EventStore

CLUSTER_JACCARD = 0.5
HOUR_MS = 60 * 60 * 1000


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def iso_from_ms(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _days_before(iso: str, days: int) -> str:
    return iso_from_ms(_ms(iso) - int(timedelta(days=days).total_seconds() * 1000))


def world_state_shape(store: EventStore) -> dict[str, Any]:
    """The idempotency diff surface: everything derived from observations, sorted."""
    st = store.state
    return {
        "entities": [st.entities[k] for k in sorted(st.entities)],
        "contexts": [st.contexts[k] for k in sorted(st.contexts)],
        "relationships": [st.relationships[k] for k in sorted(st.relationships)],
        "facts": [st.facts[k] for k in sorted(st.facts)],
        "observations": [store.observations[k] for k in sorted(store.observations)],
        "stories": [store.stories[k] for k in sorted(store.stories)],
    }


def run_ingest_pipeline(store: EventStore, observations: list[dict[str, Any]],
                        upsert: Callable[[dict[str, Any]], tuple[str, list[str]]],
                        timer: Callable[[], float]) -> dict[str, Any]:
    run_id = "run_" + sha256_hex(canonical_json([o["externalId"] for o in observations]))[:12]
    timings: list[dict[str, Any]] = []
    before = canonical_json(world_state_shape(store))
    events_before = len(store.events)

    def timed(step: int, name: str, fn: Callable[[], Any]) -> Any:
        t0 = timer()
        out = fn()
        timings.append({"step": step, "name": name, "ms": timer() - t0})
        return out

    # 1. Reconcile stale: recompute staleness from observation times.
    def reconcile() -> None:
        latest = max((o["at"] for o in observations), default="")
        for rec in store.observations.values():
            rec["stale"] = latest != "" and rec["at"] < _days_before(latest, 30)
    timed(1, "reconcile-stale", reconcile)

    # 2. Classify: an unchanged observation (same checksum) is skipped.
    fresh: list[tuple[dict[str, Any], str]] = []
    skipped: list[dict[str, Any]] = []

    def classify() -> None:
        for obs in observations:
            checksum = sha256_hex(canonical_json({"externalId": obs["externalId"], "title": obs.get("title"),
                                                  "text": obs.get("text") or "", "at": obs["at"]}))
            existing = store.observations.get(obs["externalId"])
            if existing and existing["checksum"] == checksum:
                skipped.append(obs)
            else:
                fresh.append((obs, checksum))
    timed(2, "cluster-classify", classify)

    # 3. Persist primary aggregates: the observation entity plus mentioned entities.
    def persist() -> None:
        for obs, checksum in fresh:
            entity_id, entity_ids = upsert(obs)
            store.observations[obs["externalId"]] = {
                "id": "obs_" + sha256_hex(obs["externalId"])[:12], "externalId": obs["externalId"],
                "entityId": entity_id, "checksum": checksum, "at": obs["at"], "entityIds": entity_ids,
                "stale": False,
            }
    timed(3, "persist-aggregates", persist)

    # Group observations into stories by entity overlap.
    clusters: list[list[dict[str, Any]]] = []

    def group() -> None:
        records = [store.observations[k] for k in sorted(store.observations)]
        used: set[str] = set()
        for seed in records:
            if seed["externalId"] in used:
                continue
            members = [seed]
            used.add(seed["externalId"])
            for other in records:
                if other["externalId"] not in used and jaccard(seed.get("entityIds", []),
                                                               other.get("entityIds", [])) >= CLUSTER_JACCARD:
                    members.append(other)
                    used.add(other["externalId"])
            clusters.append(members)
    timed(2, "story-grouping", group)

    # 4. Score: velocity = mentions per hour over bucketed windows. Stories, milestones,
    #    and step 8 (patch source items with their story id).
    def score() -> None:
        for members in clusters:
            member_ids = sorted(m["externalId"] for m in members)
            story_id = "story_" + sha256_hex(canonical_json(member_ids))[:12]
            times = sorted(_ms(m["at"]) for m in members)
            last = times[-1]

            def velocity(window: int) -> float:
                return sum(1 for t in times if t > last - window) / (window / HOUR_MS)
            prev_hour = sum(1 for t in times if last - 2 * HOUR_MS < t <= last - HOUR_MS)
            curr_hour = sum(1 for t in times if t > last - HOUR_MS)
            store.scores = [s for s in store.scores if s["storyId"] != story_id]
            store.scores.append({"storyId": story_id, "at": iso_from_ms(last), "velocity1h": velocity(HOUR_MS),
                                 "velocity24h": velocity(24 * HOUR_MS), "velocity7d": velocity(7 * 24 * HOUR_MS),
                                 "trendDirection": (curr_hour > prev_hour) - (curr_hour < prev_hour)})
            entity_ids = sorted({e for m in members for e in m.get("entityIds", [])})
            store.stories[story_id] = {
                "id": story_id, "title": members[0]["externalId"], "memberIds": member_ids,
                "entityNames": list(entity_ids), "entityIds": entity_ids, "sources": [],
                "firstAt": iso_from_ms(times[0]), "lastAt": iso_from_ms(last),
                "milestones": [{"kind": "multi-source", "at": iso_from_ms(times[1])}] if len(members) >= 2 else [],
            }
            for m in members:
                m["storyId"] = story_id
    timed(4, "score-measure", score)

    # 9. Rebuild aggregates.
    def aggregates() -> None:
        for entity in store.state.entities.values():
            mentions = [o for o in store.observations.values() if entity["id"] in o.get("entityIds", [])]
            if not mentions:
                continue
            times = sorted(m["at"] for m in mentions)
            entity["aggregates"] = {"mentionCount": len(mentions), "firstSeenAt": times[0], "lastSeenAt": times[-1],
                                    "linkedStoryIds": sorted({m["storyId"] for m in mentions if m.get("storyId")})}
    timed(9, "rebuild-aggregates", aggregates)

    store.persist()
    after = canonical_json(world_state_shape(store))
    report = {"runId": run_id, "processed": len(fresh), "skippedUnchanged": len(skipped), "clusters": len(clusters),
              "eventsAppended": len(store.events) - events_before, "changed": before != after,
              "stepTimingsMs": timings}
    store.log_audit("ingest", "pipeline", f"run {run_id}: {len(fresh)} processed, {len(skipped)} skipped",
                    run_id=run_id, at=observations[0]["at"] if observations else None)
    return report
