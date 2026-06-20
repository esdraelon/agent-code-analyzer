# Design: Milestone 4 — Full-Project Mass Ingestion for All Semantic Levels

## Purpose

Rebuild the complete semantic-description layer in one pass when the project needs a clean refresh.

## Requirements covered

- project-wide traversal
- every semantic level
- description generation for each scope
- write descriptions and embeddings
- idempotent rebuilds
- stable identities across repeat runs

## Current codebase evidence

The current project ingestion path is already a working template:

- `projects.py` owns `_upsert_file_analysis(...)`, `ingest_project_tree(...)`, and `sync_project_tree(...)` (`projects.py:147-240`, `283-290`)
- `vector_index.py` owns `sync_analysis(...)`, `sync_records(...)`, `bootstrap_project(...)`, and `bootstrap_all_projects(...)` (`vector_index.py:493-682`)
- `server.py` already exposes `ingest_project_tree(...)` as the user-facing MCP command (`server.py:152-169`)

That means the new semantic rebuild can follow the same orchestration shape: build source facts first, then map them into search records.

## Design pattern

**Template Method + Coordinator**

Why it fits:

- the ingestion sequence is fixed
- each stage can be specialized independently
- orchestration remains obvious and testable

## Design details

### 1. Pipeline stages

The rebuild should run in a fixed order:

1. discover project files and source metadata
2. derive semantic scopes from Tree-sitter
3. build semantic requests for each scope
4. call the writer
5. map description output into record payloads
6. persist sqlite metadata and vector points

### 2. Idempotency rules

The rebuild must be safe to rerun on the same tree:

- stable scope identities
- upsert-by-identity semantics
- deletion of stale records when a scope disappears
- no duplicate vector points for the same stable record

### 3. Scope ordering

Generate descriptions from high to low level so lower-level summaries can inherit structure from parent scopes when needed:

- package
- module
- file
- class
- method
- chunk

### 4. Relationship to current code

The current file/symbol persistence logic can be reused as the foundation for the semantic rebuild.
The semantic rebuild should not replace `ingest_project_tree`; it should become the next layer that can be invoked after the source tree is synced.

## Proposed file responsibilities

- `src/agent_code_analyzer/projects.py`
  - source discovery
  - refresh coordination
  - source metadata retrieval
- `src/agent_code_analyzer/vector_index.py`
  - point construction and upsert/delete helpers
  - semantic record sync
- `src/agent_code_analyzer/server.py`
  - command surface for rebuild triggers
- `tests/test_vector_index.py`
  - record upsert and idempotency
- `tests/test_server_helpers.py`
  - orchestration / command surface coverage

## Verification targets

- a whole-project rebuild produces the full semantic record set
- rerunning the rebuild does not duplicate records
- the coordinator stays thin and testable
- the pipeline remains compatible with the existing file/symbol ingestion path
