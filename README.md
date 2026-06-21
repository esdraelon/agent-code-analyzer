# agent-code-analyzer

Tree-sitter-powered MCP server for project-scoped structural analysis, lexical retrieval, and semantic description indexing.

## Current features

- Project registry with explicit project names and root paths
- Project-scoped file parsing and AST skeleton generation
- Symbol extraction with line-accurate spans
- Recursive project ingestion for fast rebuilds
- Lexical search built from indexed document text and terms
- Semantic description pipeline for package, module, file, class, method, and chunk scopes
- Agent abstraction for semantic generation with fake, shell, and library-backed Hermes adapters
- Incremental freshness tracking and service-wide rate limiting for agent calls
- Config-driven logging and runtime behavior
- Hermes harness tooling for deterministic one-file and project-level verification
- File-watcher support for diff-based refresh workflows
- HTTP control plane for project lifecycle, ingestion jobs, and source drill-through

## Architecture

The system is organized as a layered pipeline:

1. **Project registry and persistence**
   - `project_state` stores the per-project metadata.
   - Each project has its own sqlite database for structural records.

2. **Tree-sitter structural layer**
   - `files` stores file metadata, parse status, root node spans, and hashes.
   - `symbols` stores classes, functions, and methods with precise source ranges.
   - `semantic_chunking` uses the AST to split long bodies into meaningful chunks.

3. **Lexical retrieval layer**
   - `lexical_documents` stores searchable text for project/file/symbol scopes.
   - `lexical_terms` supports token-level lookup and ranking.

4. **Semantic description layer**
   - `semantic_agent` defines the description-generation contract.
   - `vector_index` coordinates semantic record creation and indexing.
   - `freshness` tracks fresh, dirty, and obsolete semantic state.
   - `rate_limit` protects the agent backends from overload.

5. **Runtime orchestration**
   - `watcher` feeds file-system diffs into the refresh path.
   - `hermes_harness` and `scripts/hermes_one_file_harness.py` support repeatable validation.
   - `logging_config` and `config.toml` keep runtime behavior explicit and reproducible.

## Install

```bash
python scripts/install.py
```

The installer validates local prerequisites before syncing dependencies:

- Python 3.11 or newer
- `uv`
- `fswatch`
- Docker with the Compose plugin

It then runs `uv sync --all-extras --locked`, starts the local Qdrant container idempotently, and verifies that the core packages import cleanly.

## Usage

```bash
uv sync
uv run agent-code-analyzer
uv run agent-code-analyzer-api
```

### Add a project

```text
add_project(project="demo", root_path="/path/to/repo", mode="directory")
```

### Analyze a file in a project

```text
parse_source(project="demo", file_path="src/main.py")
```

### Ingest a whole project recursively

```text
ingest_project_tree(project="demo", refresh=true)
```

## Supported languages

Current parsing coverage includes common source and config formats such as:

- Python
- JavaScript / TypeScript
- Java
- Go
- Rust
- PHP
- Ruby
- C / C++ / C#
- Bash
- YAML
- HTML
- CSS
- SQL

Unsupported extensions return a documented fallback instead of failing noisily.

## Planning docs

Active planning documents live under `docs/plans/`, and finished plans are moved to `docs/complete/`.

Current active plan:
- `docs/plans/2026-06-21-agent-code-analyzer-instrumentation-control-frontend-plan.md`

Superseded drafts merged into the active plan:
- `docs/plans/2026-06-21-agent-code-analyzer-control-plane-dashboard-plan.md`
- `docs/plans/2026-06-21-agent-code-analyzer-ingestion-recovery-gap-plan.md`

## MCP tools

### Project management

- `add_project`
- `list_projects`
- `search_projects`
- `ingest_project_tree`

### Project-scoped analysis

- `parse_source`
- `generate_ast_skeleton`
- `list_code_symbols`
- `detect_source_language`
- `read_file_excerpt`

### Semantic and runtime support

- semantic description ingestion through the indexing pipeline
- Hermes-backed agent adapters
- freshness and rate-limit controls
- file-watcher driven refreshes
