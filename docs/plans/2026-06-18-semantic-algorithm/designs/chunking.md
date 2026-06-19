# Design: Tree-sitter Chunking and Scope Partitioning

## Purpose

Split long or complex code regions into semantic chunks that are still meaningful for descriptions and retrieval.

## How it works

Tree-sitter provides the scope tree. The chunker walks that tree recursively and decides whether a region should stay whole or split further. The splitter prefers:

- class boundaries
- method boundaries
- control-flow boundaries inside complex methods
- a fallback line-window only when the AST does not provide a better partition

Each chunk keeps the parent scope identity so the refresh pipeline can remap it later.

## How it is used

- The writer receives a smaller, more focused source slice.
- Retrieval can surface chunk-level algorithm summaries instead of oversized file summaries.
- Refresh updates can invalidate only the affected region.

## Design pattern

**Composite + Recursive Descent + Strategy**

Why it fits:
- the code tree is nested, so the algorithm should follow that nesting
- recursive descent makes the traversal explicit
- a strategy object can swap between conservative and aggressive chunking behavior

## Verification targets

- Small methods remain a single chunk.
- Long methods split at sensible AST boundaries.
- Every chunk remains traceable to its parent method or class.
