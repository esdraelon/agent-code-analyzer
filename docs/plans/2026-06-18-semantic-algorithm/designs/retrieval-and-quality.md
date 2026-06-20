# Design: Milestone 7 — Retrieval and Quality Checks for Semantic Descriptions

## Purpose

Make the semantic descriptions searchable and verify that the level-specific summaries answer the right kind of question.

## Requirements covered

- fuzzy semantic intent first
- lexical fallback second
- architecture queries prefer high-level scopes
- behavior queries prefer lower-level scopes
- project scoping preserved
- quality checks for retrieval usefulness
- both rebuild and incremental paths remain searchable

## Current codebase evidence

The current retrieval stack already exposes the right hooks in `src/agent_code_analyzer/vector_index.py` and `src/agent_code_analyzer/server.py`:

- `semantic_search(...)` is the semantic search entry point (`server.py:112-129`)
- `lexical_search(...)` is the token/identifier entry point (`server.py:132-149`)
- `search_code(...)` merges the two result sets (`server.py:152-169`)
- `QdrantVectorIndex.search(...)` owns the actual vector query and result filtering (`vector_index.py:585-666`)

The code already proves that search is layered; the milestone adds level-aware retrieval policy and quality validation on top of that structure.

## Design pattern

**Specification + Strategy**

Why it fits:

- Specification defines what counts as a useful semantic hit for each scope level
- Strategy lets the retrieval policy choose ranking behavior by query intent

## Design details

### 1. Query routing

Retrieval should route by question type:

- architecture / ownership questions -> package/module/file summaries
- behavior / algorithm questions -> class/method/chunk summaries
- exact token lookup -> lexical fallback or merged search

### 2. Scope-aware ranking

Add result-shaping rules so the ranking can prefer the right granularity instead of treating all records as equal:

- file/module/package records should surface intent and dependency context
- class/method/chunk records should surface behavior and control flow
- scope type should be carried through the payload and result envelope

### 3. Quality harness

Use a repeatable query set and compare outputs against expectations for:

- scope level
- anchor usefulness
- project scoping
- latency
- noise level

## Proposed file responsibilities

- `src/agent_code_analyzer/vector_index.py`
  - result ranking and filtering
  - scope-aware payload selection
- `src/agent_code_analyzer/projects.py`
  - source metadata needed for validation snapshots
- `tests/test_vector_index.py`
  - ranking / retrieval cases
- `tests/test_server_helpers.py`
  - query-shape and envelope cases

## Verification targets

- architecture queries hit high-level summaries
- algorithm queries hit lower-level summaries
- project scoping remains correct
- the stub path remains acceptable during early development
- both ingestion modes remain searchable
