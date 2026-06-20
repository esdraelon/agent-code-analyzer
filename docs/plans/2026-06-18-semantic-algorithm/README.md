# Semantic Algorithm Plan Folder

This folder contains the low-level requirements, milestone-specific designs, and living tracking ledger for the semantic description extension of `agent-code-analyzer`.

## Document map

- `requirements.md` — milestone-by-milestone requirements
- `checklist.md` — implementation checklist for the branch
- `designs/agent-abstraction.md` — milestone 0 design: agent abstraction and Hermes adapter POC
- `designs/agent-evaluation.md` — milestone 0 supporting note: fake-agent evaluation strategy
- `designs/record-model.md` — milestone 1 design: semantic record model and stable identities
- `designs/semantic-writer.md` — milestone 2 design: semantic writer abstraction and stub backend
- `designs/chunking.md` — milestone 3 design: Tree-sitter-aware chunking and scope partitioning
- `designs/mass-ingestion.md` — milestone 4 design: full-project mass ingestion
- `designs/fswatch-diff-updates.md` — milestone 5 design: incremental fswatch diff refresh
- `designs/mcp-surface.md` — milestone 6 design: MCP surface for semantic indexing
- `designs/retrieval-and-quality.md` — milestone 7 design: retrieval and quality checks
- `designs/operator-guidance.md` — milestone 8 design: documentation and operator guidance
- `implementation-plan.md` — original milestone plan and pattern summary
- `tracking-work-complete.md` — living progress ledger and completion evidence

## Reading order

1. Read `requirements.md` for the milestone-by-milestone requirements.
2. Use the matching design doc for the milestone you are changing.
3. Use `implementation-plan.md` only if you need the original sequence and roadmap narrative.
4. Update `tracking-work-complete.md` as work lands.

## Source of truth

The older single-file plan at `docs/plans/2026-06-18-semantic-algorithm-plan.md` remains as a historical summary. This folder is the working set for implementation.
