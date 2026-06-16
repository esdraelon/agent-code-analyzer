# Persistence and Project Search Roadmap Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Harden project persistence in sqlite, then evolve the server into a cached, incremental, project-scoped code index with optional vector search.

**Architecture:**
Use sqlite as the source of truth for metadata and per-project structural indexes. Keep DB connections short-lived and write windows small to support concurrent MCP traffic. Add incrementality at the file level first with filesystem watching, then introduce caching and vector search as additive layers rather than replacing the current sqlite index too early.

**Tech Stack:**
- Python 3.11+
- sqlite3
- Tree-sitter bindings already in the repo
- pytest
- Optional future vector DB: Qdrant (candidate)

---

## Milestones

### Milestone 0: Filesystem watching incremental re-parsing service

**Status:** complete

**Objective:** Run a background service that monitors configured projects and automatically refreshes persisted sqlite data when their files change.

**Implemented shape:**
- Add a project watcher service that monitors every registered project recursively.
- Route filesystem events into a **project-level dirty queue** instead of syncing on every event.
- Deduplicate dirty-project messages by project name and reset the debounce deadline on each burst.
- Run a periodic safety sweep every 10 seconds, but only flush projects whose debounce deadline has actually matured.
- Reparse only changed, added, or deleted supported files.
- Update the per-project sqlite DB incrementally and keep metadata in sync.
- Keep the metadata DB as the registry and summary source.

**Likely files:**
- Create: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under `tests/`

**Success criteria:**
- Registered projects are watched automatically without manual refresh calls.
- Editing one file only updates that file’s index rows.
- Deletes remove file and symbol rows.
- Repeated no-op scans do not rewrite the database.
- Bursts of save events collapse into a single project sync.

---

### Milestone 1: Validate sub-file symbols for projects with poor structure hygiene

**Status:** complete

**Objective:** Detect when a project’s file structure is too messy for reliable symbol extraction.

**Implemented shape:**
- Add deterministic symbol-health validation for Tree-sitter symbol lists.
- Flag parse trees with error nodes.
- Flag duplicate symbol names in the same symbol scope.
- Flag symbol nesting that exceeds the configured depth threshold.
- Return a structured health report alongside parsed symbols and skeletons.

**Likely files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under `tests/`

**Success criteria:**
- Bad structure gets explicit warnings / flags.
- Good files remain clean.
- Validation is deterministic and test-covered.

---

### Milestone 2: Refactor core modules around explicit design patterns

**Status:** complete

**Objective:** Break the largest implementation files into clearer collaborators before adding more features, so the persistence, parsing, and watcher layers remain maintainable.

**Implemented shape:**
- `projects.py` now delegates to repository / mapper / storage / service helpers:
  - `project_models.py`
  - `project_storage.py`
  - `project_row_mapper.py`
  - `project_repository.py`
  - `project_service.py`
- `parsing.py` now uses explicit source parsing and symbol-attribution strategies.
- `watcher.py` now separates queueing, project routing, and process supervision behind small collaborators.
- Detailed execution record: `docs/complete/2026-06-14-refactor-projects-parsing-watcher.md`.
- The public MCP surface and existing tests remained stable during the refactor.

**Likely files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `tests/test_smoke.py`
- Modify: `tests/test_projects_sqlite.py`
- Modify: `tests/test_coverage_gaps.py`
- Modify: `tests/test_language_attribution.py`
- Modify: `tests/test_symbol_validation.py`
- Modify: `tests/test_watcher.py`

**Success criteria:**
- Each implementation area has a clearer pattern boundary.
- Refactoring does not change the MCP API or the project persistence semantics.
- The related test suite still passes after the split.

**Validation note:**
- Coverage run: `PYTHONPATH=/home/hal9k/host-tools/agent-code-analyzer/src python3 -m pytest --cov=agent_code_analyzer --cov-report=term-missing -q`
- Result: `35 passed`, `92%` overall coverage.

---

### Milestone 3: Add caching

**Status:** complete

**Objective:** Reduce repeated parse cost for hot files and repeated requests.

**Implemented shape:**
- Reuse per-file snapshots keyed by `file_size` and `file_mtime_ns` to skip reparsing unchanged files.
- Preserve per-project summary rows and only rewrite them when file content or membership changes.
- Keep cache invalidation deterministic by falling back to a full reparse when the file snapshot changes.

**Likely files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/parsing.py`
- Possibly create: `src/agent_code_analyzer/cache.py`

**Success criteria:**
- Repeated reads of unchanged files avoid reparsing.
- Cache invalidates correctly on content change.
- Cached lookups do not hold sqlite connections open longer than necessary.

**Validation note:**
- Current implementation already has a no-op sync path covered by tests, including unchanged-file reuse and refresh behavior.
- Coverage run: `PYTHONPATH=/home/hal9k/host-tools/agent-code-analyzer/src python3 -m pytest --cov=agent_code_analyzer --cov-report=term-missing -q`
- Result: `35 passed`, `92%` overall coverage.

---

### Milestone 4: Select a vector database

**Status:** complete

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
- Qdrant chosen for the first implementation because it is easy to run locally with Docker, supports payload filters for project scoping, and keeps the semantic layer separate from sqlite’s structural source of truth.

**Likely files:**
- Create: `docs/decisions/vector-db.md`
- Possibly create: `docker-compose.yml` or deployment docs if a local service is needed

**Success criteria:**
- Decision recorded with trade-offs and a clear default choice.

**Validation note:**
- Local Qdrant startup is wired into the install path via Docker Compose.
- Dependency validation now includes `qdrant-client`.

---

### Milestone 5: Project-scoped code ingestion in the vector database

**Status:** complete

**Objective:** Enable semantic retrieval over project code, not just structural lookup.

**Implemented shape:**
- Ingest project files into the vector DB with project id metadata.
- Store chunk text, file path, symbol context, and language metadata.
- Keep vector ingestion project-scoped so searches never cross project boundaries accidentally.
- Use sqlite as the structural source of truth while vector DB handles semantic search.
- Expose an MCP `semantic_search` tool for code-chunk lookup.

**Likely files:**
- Create: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add integration tests under `tests/`

**Success criteria:**
- Querying a project returns relevant code chunks from that project only.
- Reindexing preserves project scoping and metadata filters.
- Vector ingestion is repeatable and testable.

**Validation note:**
- `uv run pytest -q` currently passes with the vector index and semantic search slices in place.

---

### Milestone 6: Decide whether vector DB supplements or replaces some sqlite responsibilities

**Status:** complete

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

**Outcome:**
- That ownership split is now implemented: sqlite remains authoritative, and Qdrant is a best-effort semantic projection with project-scoped payload filters.

**Success criteria:**
- Clear ownership of metadata, structure, and semantic vectors.
- No ambiguous dual-write behavior without a defined source of truth.

---

### Milestone 7: Add preprocessed lexical search

**Status:** planned

**Objective:** Add a lightweight exact and keyword search layer so the analyzer can answer literal queries quickly before it falls back to semantic retrieval.

**Why this belongs here:**
Lexical search is the cheapest high-signal win in the roadmap. It gives predictable results for file names, symbol names, and exact phrases, and it also improves the quality of the later embedding work because literal candidates can be surfaced first.

**Detailed shape:**
- Build a small preprocessed lexical index over:
  - file text
  - file paths
  - symbol names
  - normalized identifiers and metadata
- Normalize queries by:
  - lowercasing
  - splitting `snake_case` and `camelCase`
  - preserving exact identifiers and quoted phrases
  - keeping filename-style tokens intact
- Keep ranking simple and explainable:
  - exact token hits rank first
  - phrase hits rank next
  - filename and path hits are boosted
  - symbol-name hits outrank generic body text when the query is clearly identifier-shaped
- Keep the index project-scoped so results never cross repository boundaries.
- Keep the implementation local-first, ideally on top of sqlite FTS5 or a similarly small in-process index.

**Implementation slices:**
1. Define the document model for lexical indexing.
2. Build the normalizer/tokenizer for query and document text.
3. Implement project-scoped indexing and refresh logic.
4. Wire search ranking so exact and phrase matches surface ahead of looser hits.
5. Expose the result path through the server helpers.

**Possible tools:**
- sqlite FTS5 or a compact in-process inverted index
- preprocessing helpers for token normalization
- project metadata filters

**Likely files:**
- Create: `src/agent_code_analyzer/lexical_index.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/server.py`
- Possibly modify: `src/agent_code_analyzer/projects.py`
- Add tests under `tests/`

**Success criteria:**
- Exact keyword and phrase searches return the expected files and symbols quickly.
- Search ranking is more predictable than the current semantic-only path for literal lookups.
- The feature stays lightweight and does not introduce a separate search service.
- Preprocessing improves matches without making the query model opaque.
- The index remains fully project-scoped.

---

### Milestone 8: Add full-codebase embedding search

**Status:** in progress

**Objective:** Replace the current best-effort vector projection with a practical semantic retrieval layer that can search the whole codebase using real embeddings instead of hash-derived placeholders.

**Why this is separate from milestone 7:**
Lexical search handles literal precision; this milestone handles semantic recall. The two layers should cooperate, not compete.

**Detailed shape:**
- Replace the current hash-derived vectors with a real embedding model.
- Define what gets embedded and how chunks are formed:
  - raw source text
  - symbol signatures
  - file path context
  - AST skeleton or other structural hints
- Keep chunk identifiers stable so reindexing and incremental refresh remain deterministic.
- Keep the semantic layer project-scoped and payload-rich.
- Keep lexical and semantic retrieval separate, then merge their results at query time.
- Rank literal lexical hits before similarity-only matches when the query clearly contains exact tokens.
- Trigger embedding refreshes from filesystem events so changed files stay current.

**Implementation slices:**
1. Lock the embedding provider interface.
2. Decide the chunking strategy and metadata shape.
3. Build the embedding index / point builder around stable IDs.
4. Wire incremental refresh into project sync and watcher events.
5. Fuse lexical and semantic retrieval into a predictable result order.
6. Compare the hybrid output against ORK3 benchmark queries.

**Initial slice:**
- Build and wire the lexical index first, then compare it against the existing semantic path on ORK3 queries.

**Possible tools:**
- Embedding model provider or local embedding runtime
- Qdrant or equivalent vector store with payload filters
- filesystem watcher / fswatch trigger path

**Likely files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/server.py`
- Possibly create: `src/agent_code_analyzer/embedding_index.py`
- Add tests under `tests/`

**Success criteria:**
- The entire indexed codebase is covered by the embedding/search pipeline.
- File changes automatically refresh the affected embeddings.
- Semantic searches return useful project-scoped results that complement lexical lookup.
- The feature remains deterministic enough to test and verify.

---

### Milestone 9: Add coverage tooling and regression safety nets

**Status:** planned

**Objective:** Make unit coverage and regression checks visible and repeatable before the intent-analysis work resumes.

**Planned shape:**
- Add coverage reporting to the normal test workflow.
- Keep a documented command for running the full unit suite.
- Add a regression safety-net mechanism that complements unit tests.
- Make the tooling easy to run locally and in CI.

**Possible tools:**
- Python coverage / pytest-cov
- golden-file or snapshot-style checks where they fit
- additional smoke tests for server behavior

**Likely files:**
- Modify: `pyproject.toml`
- Create: `docs/decisions/test-safety-nets.md`
- Possibly create: `scripts/test-coverage.sh`
- Possibly modify CI config

**Success criteria:**
- Coverage can be measured with a single documented command.
- Regression checks are part of the normal workflow, not ad hoc.
- The chosen safety-net tools produce deterministic signals.

**Validation note:**
- `pytest-cov` is now installed in the dev environment.
- Current measured coverage: 97% overall; `watcher.py` is at 91%.

---

### Milestone 10: Add component intent analysis

**Status:** planned

**Objective:** Add component-level summaries that explain responsibilities, boundaries, and likely ownership after the retrieval layers and safety nets are stable.

**Why it moved here:**
Intent analysis is useful, but it depends on the retrieval pipeline being trustworthy first. Coverage and regression safety nets should come before it so the summaries sit on a stable base.

**Planned shape:**
- Produce a deeper semantic pass over meaningful code units.
- Store component-level summaries, responsibilities, and boundaries.
- Make those summaries queryable alongside structural code data.
- Keep the intent layer project-scoped and deterministic enough to test.

**Detailed scope questions:**
- What counts as a component: file, module, class, service, or package?
- Should intent summaries be one per file, or one per meaningful unit inside the file?
- Should intent analysis run synchronously on change, or be queued as a background pass?
- Do we want the intent layer to summarize architecture boundaries, dependencies, and risk areas?

**Likely files:**
- Possibly create: `src/agent_code_analyzer/intent_analysis.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under `tests/`

**Success criteria:**
- A component returns a stable intent summary.
- The summary is project-scoped and queryable.
- The intent layer improves code-analysis workflows without destabilizing retrieval.

---

### Milestone 11: Cache review and tuning at the end

**Status:** planned

**Objective:** Revisit the caching implementation after the rest of the roadmap settles, confirm the current first-pass cache still matches the intended behavior, and tune it only if later milestones expose a better ownership model.

**Review questions:**
- Is file-snapshot caching still the right invalidation boundary?
- Should parsed-analysis caching be split from project-summary caching later?
- Are there new code paths that bypass the cache and need tests?
- Did any later milestone change the source-of-truth contract for sqlite rows?

**Likely files:**
- Review: `src/agent_code_analyzer/projects.py`
- Review: `src/agent_code_analyzer/project_service.py`
- Review: `src/agent_code_analyzer/parsing.py`
- Review: `tests/test_projects_sqlite.py`
- Review: `tests/test_coverage_gaps.py`

**Success criteria:**
- The cache implementation is re-validated after the surrounding milestones settle.
- Any needed tuning is documented and covered by tests.
- No stale caching assumptions survive into the final milestone set.

---

## Recommended implementation order

1. Implement filesystem watching incremental re-parsing
2. Validate sub-file symbols
3. Add caching
4. Select a vector DB
5. Build project-scoped vector ingestion/search
6. Decide whether vector DB supplements or replaces some sqlite responsibilities
7. Add preprocessed lexical search
8. Add full-codebase embedding search
9. Add coverage tooling and regression safety nets
10. Add component intent analysis
11. Cache review and tuning at the end

---

## Notes

- Keep sqlite connections short-lived.
- Favor deterministic rebuilds when uncertainty is high.
- Don’t introduce vector search until the sqlite-backed project model is stable and covered by tests.
- Treat project identity as explicit everywhere; never infer it from cwd.
