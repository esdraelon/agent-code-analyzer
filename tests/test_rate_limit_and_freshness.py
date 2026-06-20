from __future__ import annotations

from agent_code_analyzer.freshness import FreshnessRegistry
from agent_code_analyzer.rate_limit import RateLimitError, GlobalRateLimiter, normalized_rate_limit_signal


def test_normalized_rate_limit_signal_detects_common_provider_language() -> None:
    signal = normalized_rate_limit_signal(RuntimeError("429 rate limit exceeded; retry after 2.5s"), backend="shell")
    assert signal is not None
    assert signal.backend == "shell"
    assert signal.scope == "provider"
    assert signal.retry_after is not None and signal.retry_after > 0


def test_global_rate_limiter_acquire_returns_and_snapshot_reflects_in_flight() -> None:
    limiter = GlobalRateLimiter(capacity=1, refill_per_second=100.0, concurrency_limit=1)
    before = limiter.snapshot()
    assert before["available_tokens"] == 1
    with limiter.acquire():
        mid = limiter.snapshot()
        assert mid["in_flight"] == 1
    after = limiter.snapshot()
    assert after["in_flight"] == 0


def test_freshness_registry_marks_dirty_and_promotes_conditionally() -> None:
    registry = FreshnessRegistry()
    dirty = registry.mark_dirty("sqlite://projects/demo/files/1")
    assert dirty.freshness_state == "dirty"
    assert dirty.potentially_inaccurate is True
    assert dirty.source_revision == 1

    promoted = registry.promote_if_current("sqlite://projects/demo/files/1", observed_revision=1)
    assert promoted is True
    fresh = registry.snapshot("sqlite://projects/demo/files/1")
    assert fresh.freshness_state == "fresh"
    assert fresh.potentially_inaccurate is False
    assert fresh.relevant is True

    stale_promote = registry.promote_if_current("sqlite://projects/demo/files/1", observed_revision=1)
    assert stale_promote is True

    stale = registry.mark_dirty("sqlite://projects/demo/files/1")
    assert stale.source_revision == 2
    refused = registry.promote_if_current("sqlite://projects/demo/files/1", observed_revision=1)
    assert refused is False
