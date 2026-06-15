# Refactor Projects, Parsing, and Watcher Architecture Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Refactor the long-lived code paths in `projects.py`, `parsing.py`, and `watcher.py` into smaller, pattern-driven modules while keeping the public MCP API and current tests stable.

**Architecture:**
Keep the existing public surface area intact, but move the implementation details behind focused helpers: a repository/mapper layer for sqlite project state, a parsing strategy layer for language-specific analysis, and a watcher orchestration layer that delegates queueing and process management to smaller collaborators. The immediate milestone is `projects.py`, because it contains the largest amount of persistence, mapping, and orchestration logic. Parsing and watcher refactors should follow the same shape: extract collaborators first, then preserve the existing wrapper functions.

**Tech Stack:**
- Python 3.11+
- sqlite3
- dataclasses
- tree-sitter / tree_sitter_languages
- pytest

---

## Milestone 2: Refactor module architecture around explicit design patterns

**Status:** complete

**Objective:** Make the implementation easier to reason about and keep each file under control by separating persistence, parsing strategy, and watcher orchestration concerns.

**Implemented shape:**
- `projects.py` now delegates to repository / mapper / storage / service helpers:
  - `project_models.py`
  - `project_storage.py`
  - `project_row_mapper.py`
  - `project_repository.py`
  - `project_service.py`
- `parsing.py` now uses explicit source parsing and symbol-attribution strategies.
- `watcher.py` now separates queueing, project routing, and process supervision behind small collaborators.
- The public MCP surface and the existing tests stayed stable during the refactor.

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
- Public functions keep their current names and behavior unless tests demonstrate a more correct contract.
- The current implementation step is visible in the roadmap, and the repo roadmap reflects this refactor as the active milestone.
- Existing tests continue to pass after the internal refactor.
- The new structure makes it obvious where to add new storage, parsing, or watcher behavior later.

**Validation note:**
- Coverage run: `PYTHONPATH=/home/hal9k/host-tools/agent-code-analyzer/src python3 -m pytest --cov=agent_code_analyzer --cov-report=term-missing -q`
- Result: `35 passed`, `92%` overall coverage.

---

### Task 1: Refactor `projects.py` around repository and mapper helpers

**Objective:** Split sqlite schema management, row mapping, project persistence, and project-file orchestration into smaller collaborators while preserving the public API.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Create: `src/agent_code_analyzer/project_models.py`
- Create: `src/agent_code_analyzer/project_storage.py`
- Create: `src/agent_code_analyzer/project_row_mapper.py`
- Create: `src/agent_code_analyzer/project_repository.py`
- Create: `src/agent_code_analyzer/project_service.py`
- Modify: `tests/test_projects_sqlite.py`
- Modify: `tests/test_coverage_gaps.py`
- Modify: `tests/test_smoke.py`

**Status:** complete

**Completed work:**
- Preserved the public functions required by the tests and external callers.
- Kept helper behavior stable for tests that directly import private helpers.
- Moved sqlite-specific work into repository, storage, mapper, and service helpers.
- Preserved serialized `languages` data.
- Preserved `project_state`, `files`, and `symbols` schema migration behavior.
- Preserved refresh / no-refresh semantics for `ingest_project_tree` and `sync_project_tree`.

---

### Task 2: Refactor `parsing.py` around parsing strategies

**Objective:** Split base language parsing, embedded-language extraction, and symbol attribution into explicit strategy-like helpers.

**Files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `tests/test_language_attribution.py`
- Modify: `tests/test_symbol_validation.py`
- Modify: `tests/test_coverage_gaps.py`

**Status:** complete

**Completed work:**
- Preserved `ParsedFile` as the parse result value object.
- Kept mixed-language attribution deterministic.
- Kept symbol health reporting separate from source detection and tree traversal.
- Preserved existing AST skeleton and symbol extraction behavior.

---

### Task 3: Refactor `watcher.py` around orchestration boundaries

**Objective:** Keep `ProjectWatcherService` as the public orchestration facade while reducing its internal responsibilities.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `tests/test_watcher.py`

**Status:** complete

**Completed work:**
- Kept `DirtyProjectQueue` as the debounced queue.
- Preserved watcher startup/shutdown behavior.
- Preserved event routing, flush behavior, and safety sweep timing.
- Maintained background process cleanup and fallback sweep coverage.

---

### Task 4: Post-refactor review and cleanup

**Objective:** Make the refactor easy to maintain for the next milestone.

**Files:**
- Modify: `docs/plans/2026-06-14-persistence-and-search-roadmap.md`
- Possibly modify: `README.md` if public behavior changes
- Possibly create: design notes under `docs/decisions/`

**Status:** complete

**Completed checks:**
- Confirmed the roadmap says refactoring is the complete milestone.
- Confirmed the refactored modules still expose the same MCP behavior.
- Confirmed the repo passes the full test suite.

---

## Immediate execution order

1. Refactor `projects.py` first.
2. Adjust the persistence-related tests to match the new structure, if needed.
3. Run the targeted tests, then the full suite.
4. Only after `projects.py` is stable, move on to `parsing.py` and `watcher.py`.

## Risks and tradeoffs

- `projects.py` has a lot of sqlite migration and summary logic; breaking it up too aggressively could destabilize schema compatibility.
- Private test imports mean some helpers may need to stay accessible during the refactor, even if they move behind cleaner internal abstractions.
- Parsing changes should avoid altering symbol ordering or file language metadata unless a test proves the current behavior is incorrect.
- Watcher refactors must not change timing semantics for debounce and safety sweeps.
