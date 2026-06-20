from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition, Lock
from time import monotonic, sleep
from typing import Iterator

from .config import get_config


@dataclass(frozen=True, slots=True)
class RateLimitSignal:
    """Normalized rate-limit signal shared across agent backends."""

    scope: str = "global"
    retry_after: float | None = None
    backend: str = ""
    request_id: str | None = None
    message: str = "rate limited"


class RateLimitError(RuntimeError):
    """Raised when a backend reports a normalized rate-limit event."""

    def __init__(self, signal: RateLimitSignal) -> None:
        super().__init__(signal.message)
        self.signal = signal


class GlobalRateLimiter:
    """Small token-bucket style limiter shared by all agent calls."""

    def __init__(self, *, capacity: int = 8, refill_per_second: float = 8.0, concurrency_limit: int = 4) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        if concurrency_limit < 1:
            raise ValueError("concurrency_limit must be at least 1")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.concurrency_limit = int(concurrency_limit)
        self._tokens = float(capacity)
        self._last_refill = monotonic()
        self._active = 0
        self._lock = Lock()
        self._condition = Condition(self._lock)

    def _refill(self, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        elapsed = max(0.0, current - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_second)
        self._last_refill = current

    def snapshot(self) -> dict[str, float | int]:
        with self._condition:
            self._refill()
            return {
                "available_tokens": int(self._tokens),
                "capacity": int(self.capacity),
                "in_flight": self._active,
                "concurrency_limit": self.concurrency_limit,
            }

    @contextmanager
    def acquire(self, weight: int = 1) -> Iterator[None]:
        if weight < 1:
            raise ValueError("weight must be at least 1")
        with self._condition:
            while True:
                self._refill()
                enough_tokens = self._tokens >= weight
                enough_capacity = self._active < self.concurrency_limit
                if enough_tokens and enough_capacity:
                    self._tokens -= weight
                    self._active += 1
                    break
                wait_seconds = 0.01
                if not enough_tokens:
                    deficit = weight - self._tokens
                    wait_seconds = max(wait_seconds, deficit / self.refill_per_second)
                self._condition.wait(timeout=wait_seconds)
        try:
            yield
        finally:
            with self._condition:
                self._active = max(0, self._active - 1)
                self._condition.notify_all()


_CONFIG = get_config()
_GLOBAL_RATE_LIMITER = GlobalRateLimiter(
    capacity=_CONFIG.rate_limit.capacity,
    refill_per_second=_CONFIG.rate_limit.refill_per_second,
    concurrency_limit=_CONFIG.rate_limit.concurrency_limit,
)


def get_global_rate_limiter() -> GlobalRateLimiter:
    return _GLOBAL_RATE_LIMITER


def normalized_rate_limit_signal(error: Exception, *, backend: str) -> RateLimitSignal | None:
    text = str(error).lower()
    if not text:
        return None
    if "rate limit" in text or "too many requests" in text or "429" in text or "throttl" in text:
        retry_after: float | None = None
        for token in text.replace("/", " ").replace(",", " ").split():
            try:
                value = float(token)
            except ValueError:
                continue
            if value > 0:
                retry_after = value
                break
        return RateLimitSignal(scope="provider", retry_after=retry_after, backend=backend, message=str(error))
    return None


def sleep_for_signal(signal: RateLimitSignal) -> None:
    if signal.retry_after is not None and signal.retry_after > 0:
        sleep(signal.retry_after)
