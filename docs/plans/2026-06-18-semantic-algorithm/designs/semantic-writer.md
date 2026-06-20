# Design: Milestone 2 — Semantic Writer Abstraction with a Stub Backend

## Purpose

Add the narrow semantic-description writer boundary that can later be backed by a real model, while keeping the indexing pipeline testable with a deliberate no-response sentinel.

## Requirements covered

- narrow writer interface
- deliberate no-response sentinel
- transport/runtime failure distinction
- stub backend for early plumbing
- swap-ready boundary for future model-backed backends

## Current codebase evidence

The agent abstraction already exists in `src/agent_code_analyzer/agents/`:

- `AgentCaller.call(...)` is the current normalized entry point (`agents/base.py`)
- `FakeAgent` already proves the traceable placeholder pattern (`agents/fake.py`)
- `HermesShellAgent` and `HermesLibAgent` already provide transport-specific adapters (`agents/hermes.py`)

That means the semantic writer can be built as a small layer above the agent abstraction rather than as a separate transport system.

## Design pattern

**Strategy + Null Object + Adapter**

Why it fits:

- Strategy keeps the writer backend swappable.
- Null Object represents an intentional "no generated response yet" state.
- Adapter isolates whichever concrete agent or provider is chosen later.

## Design details

### 1. Writer contract

The writer should accept a semantic unit request with enough context to explain the code:

- source slice
- Tree-sitter outline / AST skeleton
- file path
- symbol path
- line anchors
- lineage metadata
- output contract / verbosity hints

The writer should return one of three outcomes:

- description text
- deliberate sentinel/no-op response
- transport/runtime failure

### 2. Stub backend

The initial backend should be a stub that always returns the sentinel path.

Recommended sentinel semantics:

- explicit no-response marker, not `None`
- easy to test
- distinguishable from exceptions
- safe to pass through indexing code

The stub backend should reuse the same request shape as the future real backend, so the caller never has to change when the writer becomes real.

### 3. Integration with agent abstraction

The writer should call the agent wrapper rather than depending on raw Hermes details directly. That allows the same request shape to be exercised by:

- the deterministic fake backend
- the Hermes shell backend
- the Hermes library backend

### 4. Relationship to future semantic extraction

The writer is not the schema. It produces description text only. The record layer owns persistence and metadata validation.

## Proposed file responsibilities

- `src/agent_code_analyzer/semantic_agent.py` if created
  - semantic writer interface
  - sentinel type / helper
  - adapter to the agent abstraction
- `src/agent_code_analyzer/vector_index.py`
  - call sites that request semantic descriptions
- `tests/test_semantic_agent.py` if created
  - sentinel path
  - failure path
  - wrapper contract

## Verification targets

- the caller can distinguish no-response from failure
- the writer boundary stays narrow and swappable
- the stub path keeps indexing testable without a model dependency
- existing agent backends can be plugged in later with minimal caller change
