# Design: Milestone 3 — Tree-sitter-Aware Chunking and Scope Partitioning

## Purpose

Split long or algorithmically dense regions into useful semantic chunks while preserving lineage, ownership, and line-accurate anchors.

## Requirements covered

- AST-aware chunk boundaries
- control-flow aware splitting
- parent method retention
- file and line anchors
- avoid trivial fragments
- keep small methods whole

## Current codebase evidence

The current ingestion pipeline already has the structure needed for scope-aware chunking:

- `projects.py` parses files and persists Tree-sitter-backed file/symbol records (`projects.py:147-240`)
- `vector_index.py` turns file and symbol records into Qdrant points (`vector_index.py:144-206`, `344-420`, `422-491`)
- `server.py` already exposes parse/AST helper tools (`server.py:89-170`, `179-224`)

Those helpers mean chunking can be added as a new structural layer instead of retrofitting raw text slicing everywhere.

## Design pattern

**Composite + Recursive Descent + Strategy**

Why it fits:

- Composite models the AST hierarchy.
- Recursive Descent walks the tree and decides where to stop or split.
- Strategy chooses the chunking policy for each scope type.

## Design details

### 1. Chunking inputs

The chunker should use the richest available source information:

- file source text
- Tree-sitter AST skeleton / outline
- symbol list with line anchors
- parent scope identity
- current file fingerprint

### 2. Chunking policy

Chunking should be scope-aware:

- package/module/file scopes should remain coarse and structural
- class scopes should track responsibilities and composition points
- method scopes should split only when algorithmic density or control-flow complexity demands it
- chunk scopes should stay line-accurate and traceable back to the parent method/class

### 3. Boundary rules

Prefer split points in this order:

1. AST node boundaries
2. control-flow region boundaries
3. logical block boundaries
4. line spans only as a fallback

### 4. Relation to existing vector points

The existing `file` and `symbol` payload split in `vector_index.py` is a useful precedent. Chunking should extend that model by adding a smaller semantic scope when one symbol is too dense to explain in one summary.

## Proposed file responsibilities

- `src/agent_code_analyzer/semantic_chunking.py` if created
  - recursive AST traversal
  - chunk policy selection
  - lineage preservation
- `src/agent_code_analyzer/vector_index.py`
  - chunk record point mapping
  - payload building
- `tests/test_semantic_chunking.py`
  - long-method split cases
  - small-method no-split cases
  - lineage cases

## Verification targets

- long methods split only when the AST says they should
- small methods remain whole
- every chunk can be traced back to its owning scope
- chunk spans remain line-accurate for refreshes
