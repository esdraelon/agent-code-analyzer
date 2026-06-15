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
- Detailed execution record: `docs/plans/2026-06-14-refactor-projects-parsing-watcher.md`.
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

### Milestone 4: Project-scoped code ingestion in the vector database

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

### Milestone 5: Decide whether vector DB supplements or replaces some sqlite responsibilities

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

### Milestone 6: Add coverage tooling and regression safety nets

**Status:** planned

**Objective:** Make unit coverage and regression checks visible and repeatable before the more environment-sensitive work.

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

### Milestone 7: Add code quality analysis

**Status:** planned

**Objective:** Enforce maintainable code shape and style automatically.

**Planned shape:**
- Add linting and style enforcement.
- Add method/function complexity analysis.
- Add static checks for code structure, naming, and pattern misuse where practical.
- Capture useful analysis in CI and developer commands.

**Possible tools:**
- Ruff / Black / pytest-based quality checks
- complexity analysis tools such as radon or similar
- design-pattern or architecture checks where they fit the repo
- agent skills for code review and quality triage

**Likely files:**
- Modify: `pyproject.toml`
- Create: `docs/decisions/code-quality.md`
- Possibly create: `.github/workflows/quality.yml`

**Success criteria:**
- Linting and style rules run automatically.
- Complexity hotspots are visible.
- Quality regressions are caught early.

---

### Milestone 8: Add code security analysis

**Status:** planned

**Objective:** Add automated security checks and agent workflows for unsafe code detection.

**Planned shape:**
- Add dependency and source-code security scanning.
- Add secret detection and risky-pattern analysis where appropriate.
- Define security review skills and automation for recurring checks.

**Possible tools:**
- `pip-audit` or equivalent dependency auditing
- `bandit` or similar Python security scanner
- secret scanning tools where relevant
- agent skills for security review and triage

**Likely files:**
- Modify: `pyproject.toml`
- Create: `docs/decisions/code-security.md`
- Possibly create: `.github/workflows/security.yml`

**Success criteria:**
- Security scans run automatically.
- Findings are actionable and documented.
- Unsafe patterns are flagged before merge.

---

### Milestone 9: Add mutation testing at the end

**Status:** planned

**Objective:** Prove the unit tests catch meaningful behavior changes once the project structure, build boundaries, and environment assumptions are stable.

**Why it is last:**
Mutation testing is the most environment-sensitive milestone here. It depends on stable packaging, reliable test isolation, and a clear answer to which environments are authoritative. That makes it a better fit after the filesystem watcher, caching, coverage, and quality gates are settled.

**Planned shape:**
- Evaluate `mutatest` for Python first, plus any better-fit alternatives if the toolchain has moved.
- Decide whether mutation runs should target the full suite or a curated subset first.
- Establish a minimal mutation gate for critical modules before expanding coverage.

**Decision inputs:**
- compatibility with Python 3.11+
- setup overhead in this repo
- reporting quality and exit codes
- ability to focus on changed modules or files
- behavior across local dev, CI, and project-specific environments

**Likely files:**
- Create: `docs/decisions/mutation-testing.md`
- Possibly create: `scripts/mutation.sh` or equivalent tooling entrypoint
- Modify: `pyproject.toml` if we add dependency/dev tooling hooks
- Add tests or CI wiring under `tests/` or `.github/workflows/`

**Success criteria:**
- At least one mutation-testing tool is selected and documented.
- The repo can run a mutation pass in a repeatable way.
- The result is actionable, not just a vanity score.

---

### Milestone 10: Cache review and tuning at the end

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
6. Revisit sqlite vs vector ownership
7. Add coverage tooling and regression safety nets
8. Add code quality analysis
9. Add code security analysis
10. Add mutation testing

---

## Notes

- Keep sqlite connections short-lived.
- Favor deterministic rebuilds when uncertainty is high.
- Don’t introduce vector search until the sqlite-backed project model is stable and covered by tests.
- Treat project identity as explicit everywhere; never infer it from cwd.
