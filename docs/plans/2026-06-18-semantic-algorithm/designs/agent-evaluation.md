# Design: Milestone 0 Supporting Note — Agent Evaluation Strategy

## Purpose

Record the fake-vs-real evaluation pattern used by the agent abstraction POC so the semantic-description branch can stay deterministic during plumbing work.

## Current codebase evidence

The evaluation strategy is already implemented in `src/agent_code_analyzer/agents/fake.py` and verified in `tests/test_agents.py`.

- `FakeAgent` returns `No detail here`
- it logs request records to JSONL when a log directory is configured
- it preserves structural placeholder output for structured requests

The agent factory in `src/agent_code_analyzer/agents/base.py` already makes the fake backend the simplest backend to swap into a future semantic writer.

## Design pattern

**Strategy + Null Object + Adapter**

Why it fits:

- Strategy allows a fake backend today and a real backend later
- Null Object keeps the evaluation path deterministic
- Adapter isolates logging and feedback handling from provider details

## Design details

### 1. Fake backend behavior

The fake backend should continue to:

- parse the prompt shape enough to keep output valid
- log every request deterministically
- return a placeholder response that is easy to assert in tests

### 2. Why this exists

The semantic-description branch needs a transport-independent proof-of-life path before a model-backed writer is introduced.

### 3. Relationship to milestone 0

This note is intentionally narrower than `agent-abstraction.md`:

- `agent-abstraction.md` explains the caller boundary and Hermes adapters
- this file explains why the fake backend exists and how to keep it deterministic

## Verification targets

- the fake backend logs requests to disk
- the fake backend always emits `No detail here`
- structured prompts still receive structurally valid placeholders
- the fake strategy remains usable until a real backend is plugged in
