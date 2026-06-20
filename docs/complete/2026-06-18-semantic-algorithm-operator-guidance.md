# Semantic Algorithm Operator Guidance

**Goal:** document how the semantic-description layer works so an operator can choose the right mode, understand the scope levels, and distinguish the fake, stub, and real backend paths without reconstructing the implementation from code.

**Completed work:**
- Expanded the operator-facing MCP prompt to explain semantic descriptions, rebuild vs refresh usage, and the backend split.
- Expanded the milestone 8 design note with plain-language operator guidance.
- Marked the milestone 8 checklist items complete in the active plan folder.
- Recorded milestone 8 completion in the tracking ledger.

**Operator guidance now covered:**
- semantic descriptions are summaries attached to package/module/file/class/method/chunk scopes
- semantic descriptions complement source chunks; they do not replace them
- use `semantic_rebuild` for full rebuilds after onboarding, repairs, or broad refactors
- use `semantic_refresh` for incremental fswatch-driven diffs
- use `FakeAgent` for deterministic baselines, the stub backend for plumbing checks, and the real backend for live indexing

**Source of truth:**
- active working plan: `docs/plans/2026-06-18-semantic-algorithm/`
- operator prompt: `docs/prompts/agent-code-analyzer-mcp-prompt.md`

**Verification:**
- branch: `feat/semantic-algorithm-m8-operator-guidance`
- repo verification: `git diff --check`; `uv run pytest -q` (`91 passed`)
