# Long-Methods Design-Pattern Cleanup Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Reduce the longest methods and densest files in the new search/indexing code by extracting standard design-pattern boundaries, while preserving current behavior and test coverage.

**Architecture:** Keep the public module APIs stable, but move the implementation details into smaller collaborators. Use **Strategy** for search scoring, **Builder/Factory** for Qdrant payload assembly, **Coordinator/Template Method** for project synchronization, and **Repository** for sqlite-backed lexical storage. The module-level functions remain thin facades so callers do not need to change.

**Tech Stack:**
- Python 3.11+
- sqlite3
- qdrant-client
- pytest
- existing Tree-sitter parsing and search helpers

---

## Audit summary

I checked the current branch for long files and long methods. The main hotspots are:

- `src/agent_code_analyzer/vector_index.py` — 646 lines
  - `QdrantVectorIndex.search`
  - `QdrantVectorIndex._build_points_from_analysis`
  - `QdrantVectorIndex._build_points_from_records`
  - `QdrantVectorIndex._make_point`
  - `QdrantVectorIndex._symbol_payload`
- `src/agent_code_analyzer/project_service.py` — 619 lines
  - `sync_project_tree`
  - `ingest_project_tree`
  - `project_file_summary`
  - `_upsert_file_analysis`
- `src/agent_code_analyzer/lexical_index.py` — 324 lines
  - `sync_analysis`
  - `search`
  - `_insert_document`
- `src/agent_code_analyzer/search_rank.py` — 98 lines
  - `score_search_candidate` is compact enough to stay in one file, but dense enough to benefit from a dedicated scoring policy object
- `src/agent_code_analyzer/embedding_provider.py` — 77 lines
  - already a good narrow adapter boundary; likely leave as-is unless a second embedding backend appears

**Refactor target:** keep behavior unchanged, but move the work into smaller pattern-aligned units so the next search-quality changes are easier to reason about.

---

## Cleanup milestone: extract standard design patterns

**Status:** in progress

**Objective:** Convert the longest implementation paths into small collaborating objects with explicit responsibilities.

**Success criteria:**
- No public API breaks for existing callers.
- Search ranking logic is testable independently from retrieval and indexing.
- Qdrant payload creation is isolated from sync orchestration.
- Project sync logic is broken into scan/diff/apply steps instead of one long method.
- Lexical sqlite operations are separated from query ranking and result shaping.
- Current tests still pass, and new unit tests cover the extracted collaborators.

---

### Task 1: Freeze current behavior with focused tests

**Objective:** Capture the current ranking, indexing, and sync behavior before extracting anything.

**Files:**
- Modify: `tests/test_search_rank.py`
- Modify: `tests/test_vector_index.py`
- Modify: `tests/test_lexical_index.py`
- Modify: `tests/test_projects_sqlite.py`
- Modify: `tests/test_server_helpers.py`

**Coverage to add:**
- exact-token vs loose-substring ranking stays stable
- generated/minified penalty stays applied
- vector payloads still include stable project/file/symbol identifiers
- lexical search still returns the same order for representative queries
- project sync still preserves unchanged files and removes deleted ones

**Verification:**
- Run the focused tests first.
- Confirm the expected failures do not change before refactoring.

---

### Task 2: Extract search scoring into a Strategy object

**Status:** complete

**Objective:** Pull the dense scoring rules out of `search_rank.py` so the ranking policy can evolve independently.

**Files:**
- Modify: `src/agent_code_analyzer/search_rank.py`
- Possibly create: `src/agent_code_analyzer/search_scoring.py`
- Modify: `src/agent_code_analyzer/lexical_index.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `tests/test_search_rank.py`

**Planned pattern:**
- **Strategy** for the scoring policy
- optional `ScoreBreakdown` dataclass for explainability
- thin module-level wrapper that preserves the current function signature

**Refactor shape:**
- keep normalization helpers separate from ranking
- move exact-match, loose-match, path-match, symbol-match, and generated-content penalty into named steps
- make the scoring rules independently unit-testable

**Verification:**
- unit tests prove the strategy yields the same scores as the current function for representative inputs
- generated/minified suppression still works
- acronym and digit tokenization stays intact

---

### Task 3: Split Qdrant payload assembly into a Builder/Factory layer

**Objective:** Remove payload-construction noise from `vector_index.py` and make point creation easier to test.

**Files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `src/agent_code_analyzer/vector_payload_factory.py`
- Possibly create: `src/agent_code_analyzer/vector_point_builder.py`
- Modify: `tests/test_vector_index.py`

**Planned pattern:**
- **Builder** for payload construction
- **Factory** for point creation from file/symbol inputs
- **Mapper** for turning sqlite rows and parsed symbols into payload dictionaries

**Refactor shape:**
- move `_file_payload` and `_symbol_payload` into dedicated helper(s)
- isolate stable ID generation from payload shape
- keep `_build_points_from_analysis` and `_build_points_from_records` as orchestration only
- keep document vs symbol embedding text generation explicit and separate

**Verification:**
- file points and symbol points keep identical payload keys and IDs
- bootstrap and sync still upsert the same number of points
- payload-specific tests can run without hitting Qdrant

---

### Task 4: Break project synchronization into a Coordinator pipeline

**Objective:** Turn `ingest_project_tree` and `sync_project_tree` into orchestration layers that call smaller steps.

**Files:**
- Modify: `src/agent_code_analyzer/project_service.py`
- Possibly create: `src/agent_code_analyzer/project_sync.py`
- Possibly create: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `tests/test_projects_sqlite.py`
- Modify: `tests/test_watcher.py`

**Planned pattern:**
- **Coordinator** or **Template Method** for project sync
- small step objects/functions for:
  - scan source files
  - diff current vs existing state
  - apply updates
  - apply deletions
  - persist project summary

**Refactor shape:**
- keep sqlite writes grouped by responsibility
- move secondary-index sync calls behind explicit helper boundaries
- keep the public `ingest_project_tree()` and `sync_project_tree()` signatures unchanged
- remove duplicated metadata update blocks by centralizing them

**Verification:**
- unchanged files remain untouched during sync
- deleted files are removed from sqlite and secondary indexes
- refresh mode still fully rebuilds the project state

---

### Task 5: Extract lexical storage and query logic into a Repository layer

**Objective:** Make `lexical_index.py` responsible for search semantics while the database work lives in a clearer repository boundary.

**Files:**
- Modify: `src/agent_code_analyzer/lexical_index.py`
- Possibly create: `src/agent_code_analyzer/lexical_repository.py`
- Possibly create: `src/agent_code_analyzer/lexical_documents.py`
- Modify: `tests/test_lexical_index.py`

**Planned pattern:**
- **Repository** for sqlite persistence
- **Value Object** or frozen dataclass for lexical documents
- keep `search()` as a facade over repository + scorer

**Refactor shape:**
- move schema creation and insert/upsert/delete SQL into repository methods
- separate document assembly from query execution
- keep the ranking sort key stable and explicit
- reduce `sync_analysis()` to build document records, persist them, and return a summary

**Verification:**
- lexical documents still deduplicate correctly
- search order remains stable for existing representative queries
- delete/reinsert paths still preserve project scoping

---

### Task 6: Keep the embedding provider as a narrow adapter boundary

**Objective:** Confirm the embedding provider stays small and only gets split if another backend appears.

**Files:**
- Modify only if needed: `src/agent_code_analyzer/embedding_provider.py`
- Modify only if needed: `tests/test_vector_index.py`

**Planned pattern:**
- **Adapter/Protocol** for embedding backends

**Notes:**
- the current provider file is already close to the desired shape
- do not split it further unless a second embedding implementation is added
- keep the interface stable so the vector index can remain backend-agnostic

**Verification:**
- vector size discovery still works
- query/document embedding prefix behavior remains unchanged

---

### Task 7: Re-run the full verification ladder

**Objective:** Prove the cleanup did not change behavior or weaken coverage.

**Files:**
- All touched source files
- All touched tests

**Verification ladder:**
- run focused unit tests for the extracted collaborators
- run the full pytest suite
- compare the search-result and sync behavior against the pre-refactor baseline
- confirm the working tree is clean before the next plan step

---

## Implementation order

1. Freeze behavior with tests
2. Extract the scoring Strategy
3. Extract Qdrant payload Builder/Factory helpers
4. Split project sync into a Coordinator pipeline
5. Move sqlite work into a Repository layer
6. Keep the embedding adapter narrow and stable
7. Run the full verification ladder

---

## Notes for the next step

This cleanup should happen before the next search-quality or intent-analysis work. The goal is to make the new code easier to extend, not to change the retrieval surface or add new features during the refactor itself.
