# Design: Milestone 1 — Semantic Record Model and Stable Identities

## Purpose

Define the canonical semantic-description record shape so the pipeline can store, refresh, and search package/module/file/class/method/chunk summaries without inventing a new schema at every layer.

## Requirements covered

- all six scope levels
- stable identity for idempotent upserts
- source path, symbol name, and line range anchors
- source fingerprint / content hash
- plain-language description text
- update-mode metadata
- parent/child lineage for nested scopes

## Current codebase evidence

The existing storage model already separates file-level and symbol-level payloads inside `src/agent_code_analyzer/vector_index.py`:

- `_make_point(...)` decides whether a Qdrant point is built from a file payload or a symbol payload (`vector_index.py:144-206`)
- `sync_analysis(...)` and `sync_records(...)` persist file analysis and symbol records (`vector_index.py:493-553`)
- `bootstrap_project(...)` and `bootstrap_all_projects(...)` bulk-load the current vector collection (`vector_index.py:555-682`)
- `_upsert_file_analysis(...)` in `src/agent_code_analyzer/projects.py` persists file rows and symbol rows in sqlite (`projects.py:147-240`)

The current code therefore already has the right split between:

- authoritative sqlite metadata
- Qdrant point payloads
- stable file and symbol identifiers

## Design pattern

**Value Object + Data Mapper**

Why it fits:

- the semantic record should be immutable and easy to compare
- storage concerns belong in mappers, not in the record type
- the same record model should feed sqlite, vector storage, and tests

## Design details

### 1. Semantic record value object

Introduce a dedicated semantic record type, conceptually similar to:

- `SemanticDescriptionRecord`

It should capture:

- `project`
- `scope_type` (`package`, `module`, `file`, `class`, `method`, `chunk`)
- `scope_id` (stable identity string)
- `file_path`
- `symbol_path` when available
- `line_start` / `line_end` when available
- `parent_scope_id` when nested
- `source_fingerprint`
- `description_text`
- `update_mode` (`mass_ingestion` or `fswatch_diff`)
- `source_kind` (`tree-sitter`, `chunk`, or other internal provenance labels if needed)

### 2. Stable identity rules

Identity should be derived from structural facts, not from generated text. Recommended identity inputs:

- project name
- normalized file path
- scope type
- symbol path / AST path
- line anchors when present
- parent scope identity when nested

Identity should not change when the description wording changes.

### 3. Storage mapping

The record should not know whether it is stored in sqlite or Qdrant. That responsibility belongs to mapping helpers.

The current code already demonstrates this boundary:

- sqlite rows are managed in `projects.py`
- vector point payloads are assembled in `vector_index.py`

The semantic layer should keep the same separation:

- record creation in semantic code
- sqlite persistence in a mapper / repository layer
- Qdrant payload creation in a point mapper

### 4. Relationship to existing file/symbol records

The semantic record should sit beside, not replace, the existing file and symbol payloads. The file/symbol tables already provide a good anchor for:

- file path
- language
- Tree-sitter line ranges
- node counts
- source fingerprints

The semantic record should extend that model with generated description text and lineage.

## Proposed file responsibilities

- `src/agent_code_analyzer/semantic_descriptions.py` if a dedicated record module is created
- `src/agent_code_analyzer/vector_index.py`
  - point mappers for description records
  - stable identity helpers
- `src/agent_code_analyzer/projects.py`
  - sqlite persistence helpers for semantic records

## Verification targets

- every supported scope level fits the same record model
- stable identity survives description rewrites
- storage mapping remains separate from record construction
- lineage survives rebuild and incremental refresh
