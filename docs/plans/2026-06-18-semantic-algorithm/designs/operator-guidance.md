# Design: Milestone 8 — Documentation and Operator Guidance

## Purpose

Explain how the semantic-description workflow works so the next developer or operator can use it without reconstructing the architecture from code.

## Requirements covered

- define semantic descriptions
- explain the stub agent behavior
- explain when to use mass ingestion
- explain when to use fswatch diff refresh
- explain how chunking changes method-level summaries
- explain scope-level differences
- keep docs aligned with behavior

## Current codebase evidence

The current repo already has a split between behavior and guidance:

- `docs/plans/2026-06-18-semantic-algorithm-plan.md` captures the roadmap summary
- `docs/plans/2026-06-18-semantic-algorithm/requirements.md` captures the low-level requirements
- `docs/plans/2026-06-18-semantic-algorithm/tracking-work-complete.md` captures live status
- `docs/plans/2026-06-18-semantic-algorithm/designs/*.md` captures per-milestone design intent
- `docs/prompts/agent-code-analyzer-mcp-prompt.md` is the operator-facing prompt surface referenced by the MCP tools

## Design pattern

**Runbook + Playbook**

Why it fits:

- guidance should read like an operator checklist
- mode selection should be explicit and repeatable
- the document should explain what to do, when to do it, and what success looks like

## Design details

### 1. Guidance scope

The guidance doc should explain:

- what the semantic-description layer is
- how it differs from raw source chunks
- how the fake / stub / real backends differ
- when to run rebuild vs diff refresh
- how retrieval scope should be chosen

### 2. Operator playbook language

Keep the wording practical and explicit:

- semantic descriptions are the summaries attached to package/module/file/class/method/chunk scopes
- the semantic layer complements source chunks; it does not replace them
- use full rebuild when a pull, repair, or broad refactor can invalidate many scopes
- use incremental refresh when the change set is local and already anchored by fswatch-style diffs
- use `FakeAgent` for deterministic baselines, the stub backend for plumbing checks, and the real backend for live indexing

### 3. User-facing mode selection

Give plain rules, not architecture jargon:

- use rebuild when the tree was reindexed, repaired, or heavily refactored
- use diff refresh when changes are local and incremental
- use search when the question is exploratory or exact

### 4. Document hygiene

Keep the docs synchronized with the implementation state:

- update the guide when the server surface changes
- update examples when the writer contract changes
- move the plan to `docs/complete/` only when the branch is truly done

## Proposed file responsibilities

- `docs/prompts/agent-code-analyzer-mcp-prompt.md`
  - operational usage notes
- `docs/plans/2026-06-18-semantic-algorithm/designs/operator-guidance.md`
  - semantic-description runbook
- `docs/plans/2026-06-18-semantic-algorithm/tracking-work-complete.md`
  - live milestone state

## Verification targets

- the docs describe both operating modes clearly
- the docs match the shipped behavior
- a new developer can understand the workflow from the docs alone
