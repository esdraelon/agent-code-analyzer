from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass(frozen=True, slots=True)
class FreshnessSnapshot:
    """Current freshness and revision state for a semantic unit."""

    key: str
    freshness_state: str
    source_revision: int
    source_hash: str = ""
    potentially_inaccurate: bool = False
    relevant: bool = True
    dirty_at: str | None = None


class FreshnessRegistry:
    """In-memory compare-and-swap freshness ledger for semantic records."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, dict[str, Any]] = {}

    def _ensure(self, key: str) -> dict[str, Any]:
        state = self._states.get(key)
        if state is None:
            state = {
                "freshness_state": "fresh",
                "source_revision": 0,
                "source_hash": "",
                "potentially_inaccurate": False,
                "relevant": True,
                "dirty_at": None,
            }
            self._states[key] = state
        return state

    def mark_dirty(self, key: str, *, source_hash: str = "", dirty_at: str | None = None) -> FreshnessSnapshot:
        with self._lock:
            state = self._ensure(key)
            state["source_revision"] = int(state["source_revision"]) + 1
            state["freshness_state"] = "dirty"
            state["source_hash"] = source_hash or str(state["source_hash"])
            state["potentially_inaccurate"] = True
            state["relevant"] = False
            state["dirty_at"] = dirty_at
            return self.snapshot(key)

    def mark_obsolete(self, key: str, *, source_hash: str = "", dirty_at: str | None = None) -> FreshnessSnapshot:
        with self._lock:
            state = self._ensure(key)
            state["source_revision"] = int(state["source_revision"]) + 1
            state["freshness_state"] = "obsolete"
            state["source_hash"] = source_hash or str(state["source_hash"])
            state["potentially_inaccurate"] = True
            state["relevant"] = False
            state["dirty_at"] = dirty_at
            return self.snapshot(key)

    def promote_if_current(self, key: str, *, observed_revision: int, source_hash: str = "") -> bool:
        with self._lock:
            state = self._ensure(key)
            if int(state["source_revision"]) != int(observed_revision):
                return False
            state["freshness_state"] = "fresh"
            if source_hash:
                state["source_hash"] = source_hash
            state["potentially_inaccurate"] = False
            state["relevant"] = True
            state["dirty_at"] = None
            return True

    def snapshot(self, key: str) -> FreshnessSnapshot:
        with self._lock:
            state = self._ensure(key)
            return FreshnessSnapshot(
                key=key,
                freshness_state=str(state["freshness_state"]),
                source_revision=int(state["source_revision"]),
                source_hash=str(state["source_hash"]),
                potentially_inaccurate=bool(state["potentially_inaccurate"]),
                relevant=bool(state["relevant"]),
                dirty_at=state["dirty_at"],
            )

    def apply_payload(self, payload: dict[str, Any], key: str | None = None) -> dict[str, Any]:
        lookup_key = key or str(payload.get("sqlite_uri") or payload.get("project_name") or payload.get("project") or "")
        snapshot = self.snapshot(lookup_key)
        merged = dict(payload)
        merged.setdefault("freshness_state", snapshot.freshness_state)
        merged.setdefault("source_revision", snapshot.source_revision)
        merged.setdefault("source_hash", snapshot.source_hash)
        merged.setdefault("potentially_inaccurate", snapshot.potentially_inaccurate)
        merged.setdefault("relevant", snapshot.relevant)
        merged.setdefault("dirty_at", snapshot.dirty_at)
        return merged


_GLOBAL_FRESHNESS_REGISTRY = FreshnessRegistry()


def get_freshness_registry() -> FreshnessRegistry:
    return _GLOBAL_FRESHNESS_REGISTRY
