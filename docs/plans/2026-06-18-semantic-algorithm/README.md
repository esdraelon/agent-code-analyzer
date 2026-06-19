# Semantic Algorithm Plan Folder

This folder contains the working plan, tracking ledger, and per-feature design notes for the semantic algorithm / architecture-description branch.

## Document map

- `implementation-plan.md` — milestone plan and implementation order
- `tracking-work-complete.md` — living progress ledger and completion evidence
- `designs/record-model.md` — record schema and identity design
- `designs/agent-abstraction.md` — general agent abstraction, Hermes shell/lib adapters, and fake strategy
- `designs/semantic-writer.md` — writer abstraction, stub, and backend swap design
- `designs/chunking.md` — Tree-sitter chunking and scope partition design
- `designs/mass-ingestion.md` — full rebuild pipeline design
- `designs/fswatch-diff-updates.md` — incremental diff-update pipeline design
- `designs/mcp-surface.md` — server / MCP command surface design
- `designs/retrieval-and-quality.md` — retrieval, ranking, and validation design
- `designs/operator-guidance.md` — operator usage and prompt guidance
- `designs/agent-evaluation.md` — fake-vs-real agent strategy for plan-building evaluation

## Reading order

1. Read `implementation-plan.md` for the milestone sequence and pattern choices.
2. Use the matching design doc for the feature you are changing.
3. Update `tracking-work-complete.md` as work lands.

## Source of truth

The older single-file plan at `docs/plans/2026-06-18-semantic-algorithm-plan.md` remains as a historical summary. This folder is the working set for implementation.
