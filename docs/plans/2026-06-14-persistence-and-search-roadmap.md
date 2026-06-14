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

### Milestone 0: Add test mutations

**Objective:** Add mutation testing to prove the unit tests catch meaningful behavior changes, not just line coverage.

**Planned shape:**
- Evaluate `mutatest` for Python first, plus any better-fit alternatives if the toolchain has moved.
- Decide whether mutation runs should target the full suite or a curated subset first.
- Establish a minimal mutation gate for critical modules before expanding coverage.

**Decision inputs:**
- compatibility with Python 3.11+
- setup overhead in this repo
- reporting quality and exit codes
- ability to focus on changed modules or files

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

### Milestone 7: Add coverage tooling and regression safety nets

**Objective:** Make coverage, mutation testing, and regression safety visible and repeatable.

**Planned shape:**
- Add coverage reporting to the normal test workflow.
- Choose a regression safety-net mechanism for code changes that complements unit tests.
- Make the tooling easy to run locally and in CI.

**Possible tools:**
- Python coverage / pytest-cov
- mutation testing: `mutatest` or equivalent
- PHP: Infection if any PHP components are added later
- JVM: PIT if any JVM components are added later

**Likely files:**
- Modify: `pyproject.toml`
- Create: `docs/decisions/test-safety-nets.md`
- Possibly create: `scripts/test-coverage.sh`
- Possibly modify CI config

**Success criteria:**
- Coverage can be measured with a single documented command.
- Regression checks are part of the normal workflow, not ad hoc.
- The chosen safety-net tools produce deterministic signals.

---

### Milestone 8: Add code quality analysis

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

### Milestone 9: Add code security analysis

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

## Recommended implementation order

1. Add test mutations
2. Add unit test coverage
3. Push the current feature branch to remote
4. Implement incremental filewatching
5. Add structure-health validation
6. Add caching
7. Evaluate and select a vector DB
8. Build project-scoped vector ingestion/search
9. Revisit sqlite vs vector ownership
10. Add coverage tooling and regression safety nets
11. Add code quality analysis
12. Add code security analysis

---

## Notes

- Keep sqlite connections short-lived.
- Favor deterministic rebuilds when uncertainty is high.
- Don’t introduce vector search until the sqlite-backed project model is stable and covered by tests.
- Treat project identity as explicit everywhere; never infer it from cwd.
