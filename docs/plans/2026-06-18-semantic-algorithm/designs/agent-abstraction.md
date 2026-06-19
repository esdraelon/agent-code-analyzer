# Design: Agent Abstraction and Hermes Adapters

## Purpose

Provide a layered agent interface that can evaluate semantic descriptions through multiple backends without the caller caring which concrete agent is used.

## Layers

1. **General agent abstraction**
   - A single `Agent` call surface for callers and wrappers.
   - Normalized request and response objects.

2. **Lower-level Hermes abstraction**
   - Shared Hermes-specific prompt preparation and response normalization.
   - Common configuration for shell and library execution.

3. **Hermes shell adapter**
   - Calls `hermes chat` as a subprocess.
   - Best for a simple integration boundary and easy operational inspection.

4. **Hermes library adapter**
   - Imports Hermes Python code directly and calls the agent runtime in-process.
   - Best for tighter coupling and lower per-call overhead.

## Concrete implementations

- `FakeAgent`
- `HermesShellAgent`
- `HermesLibAgent`

## Proof-of-concept wrapper

Use a small calling wrapper that accepts a backend name, builds the agent, and invokes it through the same normalized request shape.

## Evaluation flow

- `agent-code-analyzer` prepares a semantic evaluation prompt.
- The wrapper selects the backend.
- The backend returns a normalized response.
- The caller stores the raw response and metadata for traceability.

## Verification targets

- Callers can swap backends without changing the request shape.
- The shell and library Hermes adapters both satisfy the same interface.
- The fake backend remains deterministic for offline and test runs.
