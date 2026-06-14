# Persistence and Project Search Roadmap Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Harden project persistence in sqlite, then evolve the server into a cached, incremental, project-scoped code index with optional vector search.

**Architecture:**
Use sqlite as the source of truth for metadata and per-project structural indexes. Keep DB connections short-lived and write windows small to support concurrent MCP traffic. Add incrementality at the file level first, then introduce background filewatching, caching, and vector search as additive layers rather than replacing the current sqlite index too early.

**Tech Stack:**
- Python 3.11+
- sqlite3
- Tree-sitter bindings already in the repo
- pytest
- Optional future vector DB: Qdrant (candidate)

---

## Immediate steps

### Task 1: Add unit test coverage for sqlite persistence and project-scoped indexing

**Objective:** Lock in the current persistence model before building on top of it.

**Files:**
- Modify: `tests/test_smoke.py`
- Create: `tests/test_projects_sqlite.py`
- Modify: `src/agent_code_analyzer/projects.py` only if a test exposes a real bug

**What to cover:**
- metadata DB is created and contains the project registry row
- per-project DB is created for a project
- `add_project(mode="directory")` writes structured file and symbol rows
- `ingest_project_tree(refresh=False)` reuses cached state instead of reindexing
- `project_file_summary()` backfills file/symbol rows in the project DB
- project-scoped calls reject files outside the project root
- unsupported files fail softly and do not create bad rows

**Verification:**
- Run: `uv run pytest -q`
- Expected: all tests pass

**Commit:**
- `feat: add sqlite persistence coverage`

---

### Task 2: Push the current feature branch to remote

**Objective:** Publish the current persistence feature so the branch is backed by remote history before the next iteration.

**Files:**
- No code changes unless a final fix is required

**Steps:**
1. Review status: `git status -sb`
2. Review diff: `git diff --stat`
3. Commit outstanding changes with a focused message
4. Push the current branch to origin

**Verification:**
- Remote branch exists and matches local HEAD
- `git status -sb` is clean after push

**Commit:**
- Use the smallest accurate message, for example: `feat: persist project indexes in sqlite`

---

## Milestones

### Milestone 1: Per-project filewatching incremental re-parsing service

**Objective:** Reparse only changed files instead of rebuilding project indexes on every refresh.

**Planned shape:**
- Add a project watcher service that monitors the project root recursively.
- Debounce filesystem events.
- Reparse only changed, added, or deleted supported files.
- Update the per-project sqlite DB incrementally.
- Keep the metadata DB as the registry and summary source.

**Likely files:**
- Create: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under `tests/`

**Success criteria:**
- Editing one file only updates that file’s index rows.
- Deletes remove file and symbol rows.
- Repeated no-op scans do not rewrite the database.

---

### Milestone 2: Validate sub-file symbols for projects with poor structure hygiene

**Objective:** Detect when a project’s file structure is too messy for reliable symbol extraction.

**Planned shape:**
- Add validation rules for class / method nesting and symbol sanity.
- Flag malformed or suspicious symbol trees instead of silently treating them as healthy.
- Separate “parsed successfully” from “structurally healthy.”

**Possible validations:**
- nested classes or methods beyond a configured depth
- duplicate symbol names in the same scope
- empty or truncated declarations
- parse trees with significant error nodes

**Likely files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Add: `tests/test_symbol_validation.py`

**Success criteria:**
- Bad structure gets explicit warnings / flags.
- Good files remain clean.
- Validation is deterministic and test-covered.

---

### Milestone 3: Add caching

**Objective:** Reduce repeated parse cost for hot files and repeated requests.

**Planned shape:**
- Cache parsed analysis by file hash and/or mtime+size.
- Cache per-project summaries separately from per-file results.
- Ensure cache invalidation is deterministic when source changes.

**Likely files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/parsing.py`
- Possibly create: `src/agent_code_analyzer/cache.py`

**Success criteria:**
- Repeated reads of unchanged files avoid reparsing.
- Cache invalidates correctly on content change.
- Cached lookups do not hold sqlite connections open longer than necessary.

---

### Milestone 4: Select a vector database

**Objective:** Choose the best vector store for semantic code search.

**Decision inputs:**
- local development simplicity
- operational overhead
- filtering by project / path / language
- embedding lifecycle and reindex cost
- ability to scale project-scoped search cleanly

**Candidate:**
- Qdrant

**Outcome:**
- Pick one vector DB and document why it beats the alternatives for this repo.

**Likely files:**
- Create: `docs/decisions/vector-db.md`
- Possibly create: `docker-compose.yml` or deployment docs if a local service is needed

**Success criteria:**
- Decision recorded with trade-offs and a clear default choice.

---

### Milestone 5: Project-scoped code ingestion in the vector database

**Objective:** Enable semantic retrieval over project code, not just structural lookup.

**Planned shape:**
- Ingest project files into the vector DB with project id metadata.
- Store chunk text, path, symbol context, and language metadata.
- Keep vector ingestion project-scoped so searches never cross project boundaries accidentally.
- Use sqlite as the structural source of truth while vector DB handles semantic search.

**Likely files:**
- Create: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add integration tests under `tests/`

**Success criteria:**
- Querying a project returns relevant code chunks from that project only.
- Reindexing preserves project scoping and metadata filters.
- Vector ingestion is repeatable and testable.

---

### Milestone 6: Decide whether vector DB supplements or replaces some sqlite responsibilities

**Objective:** Avoid unnecessary duplication and keep the system maintainable.

**Decision questions:**
- Does sqlite remain the registry + structural index only?
- Should vector DB store only semantic chunks, while sqlite stores authoritative structure?
- Is any sqlite data duplicated purely for query convenience?
- Which index should own freshness and deletion semantics?

**Likely outputs:**
- A short design note and data ownership matrix.
- One final storage strategy that is explicit about source of truth.

**Recommended default direction:**
- sqlite remains the authoritative registry and structural index.
- vector DB supplements it for semantic search rather than replacing it immediately.

**Success criteria:**
- Clear ownership of metadata, structure, and semantic vectors.
- No ambiguous dual-write behavior without a defined source of truth.

---

## Recommended implementation order

1. Add unit test coverage
2. Push the current feature branch to remote
3. Implement incremental filewatching
4. Add structure-health validation
5. Add caching
6. Evaluate and select a vector DB
7. Build project-scoped vector ingestion/search
8. Revisit sqlite vs vector ownership

---

## Notes

- Keep sqlite connections short-lived.
- Favor deterministic rebuilds when uncertainty is high.
- Don’t introduce vector search until the sqlite-backed project model is stable and covered by tests.
- Treat project identity as explicit everywhere; never infer it from cwd.
