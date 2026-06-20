# Design: Milestone 9 — Global Agent Rate Limiting and Semantic Freshness Lifecycle

## Purpose

Protect the semantic-description service from provider throttling while keeping search honest about records that are dirty, obsolete, or in flight during fswatch-driven updates.

## Requirements covered

- one global rate limit for all agent calls
- normalized provider rate-limit signals at the agent abstraction boundary
- provider-specific backoff / retry handling inside each concrete agent
- dirty / obsolete / fresh lifecycle for semantic units
- race-safe promotion from dirty to fresh after refresh work completes
- stale semantic units remain searchable but are flagged as potentially inaccurate

## Current codebase evidence

The code already has the right seams to host this work:

- `src/agent_code_analyzer/agents/base.py` provides the shared caller surface for agent execution
- `src/agent_code_analyzer/agents/fake.py` and `src/agent_code_analyzer/agents/hermes.py` provide concrete backend implementations
- `src/agent_code_analyzer/watcher.py` already owns fswatch batching and update dispatch
- `src/agent_code_analyzer/vector_index.py` already owns semantic record storage and retrieval
- `src/agent_code_analyzer/search_filters.py` can carry result-level flags if the search envelope needs a staleness marker

The design therefore adds policy and state transitions without forcing a new transport layer.

## Design pattern

**Token Bucket + Adapter + Versioned State Machine**

Why it fits:

- token bucket gives a single service-wide limiter for all agent calls
- adapter keeps provider-specific throttling logic inside each agent implementation
- versioned state machine prevents an in-flight refresh from overwriting a newer dirty mark

## Design details

### 1. Global service rate limit

The service should gate all agent calls through one shared limiter before the backend-specific call begins.

The limiter should cover:

- search-time semantic calls
- refresh-time semantic calls
- rebuild-time semantic calls

The limiter should expose at least:

- current capacity / available tokens
- request wait time when saturated
- a concurrency ceiling for in-flight calls

That keeps one burst of semantic work from starving the rest of the service.

### 2. Normalized provider throttling

Each agent backend should translate provider-specific throttling into a common signal that the analyzer can understand.

The shared signal should capture:

- that the request was rate-limited
- whether the limit is global, provider-specific, model-specific, or workspace-specific
- retry-after / wait duration when available
- any provider request identifier useful for tracing

Implementation detail stays inside the backend; the caller only consumes the normalized signal and applies shared retry/backoff policy.

### 3. Freshness model for semantic units

Every semantic unit should carry both a freshness state and a relevance marker.

Recommended states:

- `fresh` — the stored description matches the current source snapshot
- `dirty` — source changed and the stored description may be stale
- `obsolete` — the record is known to be invalid or replaced

Recommended additional marker:

- `relevant` — the record was updated against the latest known source snapshot and is still considered usable for search

That lets the service express both "is it current?" and "is it still useful to return?" without collapsing the two concerns into one flag.

### 4. Dirtying and promotion flow

When fswatch observes a delta:

1. affected semantic units are marked dirty or obsolete immediately
2. a new revision or generation is recorded for the source scope
3. refresh work captures the revision/hash observed at start time
4. refresh completion only promotes the unit to fresh/relevant if the source revision/hash still matches

If the source changes again while refresh is in flight, the unit stays dirty.

### 5. Race protection

Timestamps alone are not enough.

Use a monotonic revision number, content hash, or both, and treat update promotion as a compare-and-swap operation:

- start refresh against revision `N`
- if current source revision is still `N` at commit time, promote the unit
- if current source revision is now `N+1` or hash differs, refuse the promotion and keep the unit dirty

This prevents the classic race where a stale refresh overwrites a later delta.

### 6. Search-time honesty

Dirty and obsolete units should remain searchable.

Search results should include a warning envelope such as:

- `freshness_state`
- `potentially_inaccurate: true`
- `dirty_at`
- `source_revision`
- `source_hash`

The results can still be ranked and returned, but the caller must be told that the data may lag behind reality.

## Proposed file responsibilities

- `src/agent_code_analyzer/agents/base.py`
  - normalized rate-limit signal shape
  - shared agent caller policy hooks
- `src/agent_code_analyzer/agents/fake.py`
  - deterministic handling of limiter signals in tests
- `src/agent_code_analyzer/agents/hermes.py`
  - Hermes-specific throttling / retry handling
- `src/agent_code_analyzer/watcher.py`
  - dirtying / obsolete transitions on fswatch deltas
  - revision capture for refresh jobs
- `src/agent_code_analyzer/vector_index.py`
  - freshness metadata persistence
  - race-safe promotion of refreshed records
  - stale-result filtering or marking
- `src/agent_code_analyzer/search_filters.py`
  - search envelope flags if needed
- `tests/test_agents.py`
  - rate-limit normalization and limiter behavior
- `tests/test_watcher.py`
  - dirty/obsolete transitions and race cases
- `tests/test_vector_index.py`
  - stale-hit surfacing and freshness-state persistence

## Verification targets

- one shared limiter governs all agent calls
- provider throttling is normalized by each backend
- dirty records remain searchable with explicit warnings
- refresh completion cannot incorrectly mark a newer dirty entry as fresh
- search consumers can distinguish fresh, dirty, and obsolete hits
