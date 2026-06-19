# Design: MCP Surface for Semantic Refresh

## Purpose

Expose semantic ingestion and refresh controls through the existing server interface.

## How it works

The server acts as a facade over the semantic pipeline. Callers see a small command surface:

- trigger a full semantic rebuild
- trigger a diff-based refresh
- query semantic descriptions

The server should keep existing lexical and chunk retrieval behavior intact while the new commands are added.

## How it is used

- Operators can manually rebuild after a refactor.
- The watcher can route diff updates into the same refresh path.
- Prompt guidance can tell the model which mode to choose.

## Design pattern

**Facade + Command**

Why it fits:
- the server should hide pipeline complexity
- each operation maps cleanly to a distinct command
- future operations can be added without exposing internal steps

## Verification targets

- The server can trigger both refresh modes.
- Legacy endpoints continue to work.
- The prompt documentation matches the actual command names.
