# Design: Milestone 0 — Agent Abstraction and Hermes Adapter POC

## Purpose

Provide the normalized agent boundary used by the semantic-description branch and prove that the caller can swap between a fake backend, Hermes shell execution, and Hermes in-process execution without changing the call site.

## Requirements covered

- normalized request and response objects
- a single wrapper/factory for agent selection
- fake, Hermes shell, and Hermes lib backends
- traceable JSONL request logs
- a stable boundary suitable for the semantic-evaluation path

## Current codebase evidence

The POC already exists in `src/agent_code_analyzer/agents/`:

- `base.py` defines `AgentRequest`, `AgentResponse`, `AgentCaller`, and `build_agent`
- `fake.py` defines `FakeAgent`
- `hermes.py` defines `HermesShellAgent` and `HermesLibAgent`
- `tests/test_agents.py` covers the wrapper and both Hermes execution modes

The current implementation already follows the desired split:

- `AgentCaller.call(...)` is the stable caller-facing API
- `build_agent(kind, **kwargs)` is the concrete strategy factory
- `FakeAgent` writes request logs and returns the deterministic placeholder `No detail here`
- `HermesShellAgent` shells out with `hermes chat`
- `HermesLibAgent` imports `run_agent.AIAgent` in-process

## Design pattern

**Strategy + Facade + Adapter + Null Object**

Why it fits:

- Strategy lets the caller choose a backend without branching on transport details.
- Facade keeps the caller-facing API tiny (`AgentCaller.call`).
- Adapter isolates Hermes-specific execution details from the caller.
- Null Object keeps the fake backend deterministic and safe for tests.

## Design details

### 1. General agent contract

The shared contract should remain the only thing the semantic pipeline depends on:

- prompt text
- optional system prompt
- request metadata
- requested response format
- normalized response content
- raw backend output
- parsed output
- backend identity

That contract is already embodied by `AgentRequest` and `AgentResponse` in `base.py`.

### 2. Hermes abstraction layer

The Hermes-facing boundary should remain lower-level than the semantic pipeline. It should own:

- CLI invocation details
- in-process Hermes imports
- model/provider configuration
- response normalization
- backends’ trace metadata

The current split in `hermes.py` is a good basis:

- `HermesShellAgent` owns subprocess execution
- `HermesLibAgent` owns import-path management and direct `AIAgent` calls

### 3. Fake backend

The fake backend should continue to behave as a deterministic sentinel provider:

- emit `No detail here`
- preserve request metadata in logs
- optionally emit structured placeholder payloads when a structured format is requested
- never require a network or model dependency

The current `FakeAgent` already logs JSONL request records and returns the placeholder response.

### 4. Wrapper / factory

The wrapper should remain the public boundary used by future semantic-description code. It should make agent selection explicit and keep the caller insulated from backend-specific kwargs.

The current `build_agent()` factory is the right place for backend selection, while `AgentCaller` stays the caller-friendly facade.

## Proposed file responsibilities

- `src/agent_code_analyzer/agents/base.py`
  - request / response dataclasses
  - agent protocol
  - caller wrapper
  - factory
- `src/agent_code_analyzer/agents/fake.py`
  - deterministic fake backend
  - JSONL request logging
- `src/agent_code_analyzer/agents/hermes.py`
  - Hermes CLI adapter
  - Hermes in-process adapter
- `tests/test_agents.py`
  - wrapper contract
  - shell command shape
  - in-process Hermes import path
  - fake placeholder behavior

## Verification targets

- callers can invoke all three backends through one wrapper
- the fake backend remains deterministic and traceable
- the shell and library adapters satisfy the same response contract
- the wrapper can be reused by later semantic-description milestones without caller rewrites
