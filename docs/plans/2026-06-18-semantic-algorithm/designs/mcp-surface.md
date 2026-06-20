# Design: Milestone 6 — MCP Surface for Semantic Description Indexing

## Purpose

Expose the semantic-description workflow through the MCP server so operators can rebuild, refresh, and query it without touching internals.

## Requirements covered

- full rebuild command
- piecewise refresh command
- clear semantic-description mode
- preserve existing retrieval paths
- backwards-compatible surface
- operator guidance in prompts

## Current codebase evidence

The current MCP surface in `src/agent_code_analyzer/server.py` already exposes the core project and search tools:

- `add_project`
- `list_projects`
- `search_projects`
- `semantic_search`
- `lexical_search`
- `search_code`
- `ingest_project_tree`
- `parse_source`
- `generate_ast_skeleton`
- `list_code_symbols`
- `detect_source_language`
- `read_file_excerpt`

That is the correct facade shape: it already separates discovery, ingestion, and search into distinct commands.

## Design pattern

**Facade + Command**

Why it fits:

- the server should present a small stable surface
- each action maps to a concrete command
- callers should not need to know about storage or refresh internals

## Design details

### 1. New semantic commands

Add commands that make the semantic-description layer explicit:

- trigger full semantic rebuild
- trigger refresh for changed files or projects
- query semantic description records at a chosen scope level

### 2. Surface separation

Keep the existing code-understanding tools separate from the new semantic-description actions:

- current parse / symbol / excerpt tools remain unchanged
- search tools continue to work for existing retrieval
- semantic rebuild/refresh is an additional command family

### 3. Prompt guidance

The MCP prompt should tell operators when to use each mode:

- use full rebuild for cold start, major refactors, or index repair
- use diff refresh for local edits and fswatch-driven updates
- use search endpoints for interactive lookup

## Proposed file responsibilities

- `src/agent_code_analyzer/server.py`
  - command registration for semantic rebuild / refresh
  - command naming and request routing
- `docs/prompts/agent-code-analyzer-mcp-prompt.md`
  - operator guidance on which command to use
- `docs/plans/2026-06-18-semantic-algorithm/designs/operator-guidance.md`
  - doc-side explanation of mode selection

## Verification targets

- the MCP surface can initiate both ingestion modes
- existing tools continue to function
- operators can tell which mode they are invoking
