# Semantic Algorithm Rate Limiting and Freshness Lifecycle

**Goal:** add a service-wide limiter for agent calls and make semantic records carry a freshness lifecycle so stale results remain visible without being mistaken for current data.

**Completed work:**
- Added a shared global rate limiter and normalized rate-limit signal handling for the fake, shell, and Hermes-lib agent backends.
- Added `FreshnessRegistry` / `FreshnessSnapshot` helpers for dirty, fresh, and obsolete state transitions.
- Wired watcher enqueue paths to mark projects dirty before refresh work begins.
- Added freshness metadata to semantic payloads and search results, including a stale-warning flag.
- Added tests covering rate-limit normalization, limiter behavior, freshness promotion, and stale-hit surfacing.

**Source of truth:**
- active working plan: `docs/plans/2026-06-18-semantic-algorithm/`
- milestone 9 design: `docs/plans/2026-06-18-semantic-algorithm/designs/rate-limiting-and-freshness.md`

**Verification:**
- branch: `feat/semantic-algorithm-m9-freshness-rate-limit`
- commit: `938bddf1b2f1c6ed03ff27dcee78877301bf90cd`
- repo verification: `git diff --check`; `PYTHONPATH=/home/hal9k/host-tools/agent-code-analyzer python3 -m pytest -q` (`97 passed`)
