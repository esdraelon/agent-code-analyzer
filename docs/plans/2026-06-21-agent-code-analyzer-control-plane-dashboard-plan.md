# Agent Code Analyzer Control Plane and Dashboard Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Add a non-agent control plane for project administration, ingestion control, log inspection, and unified code search, then build a lightweight PHP dashboard that can inspect and manage the analyzer without going through MCP tools.

**Architecture:** Keep the current MCP server as the agent-facing surface, but move all administrative behavior into a shared service layer that both MCP tools and the new HTTP control API call. The control API will expose project lifecycle, ingestion job state, log search, and normalized search results with source and related-index links. A separate PHP dashboard will consume that API and present project operations, progress, logs, and search results in a browser-friendly operator UI.

**Tech Stack:**
- Python 3.11+ for the analyzer and control API
- Existing sqlite/Qdrant/Tree-sitter stack already in the repo
- New HTTP layer for the control plane, preferably FastAPI or an equally small ASGI app
- PHP 8.4 for the dashboard, with a lightweight router/framework if needed
- pytest for Python verification
- PHP lint/smoke checks for the dashboard

---

## Current state to preserve

The repository already supports:
- project registration and listing
- project ingestion and refresh
- Tree-sitter parsing and AST skeleton generation
- lexical search
- semantic search
- file-watcher driven refreshes
- logging configuration and Hermes harness verification

What is still missing for the requested operator workflow:
- offboarding projects
- live ingestion progress and job history
- a non-agent HTTP API for administrative actions
- searchable log access
- normalized result envelopes that link back to source code and related indexes
- a browser dashboard for operators

---

## Milestone 1: Define the shared control-plane contract

### Task 1: Add explicit control-plane models and configuration

**Objective:** Introduce stable request/response shapes for project management, ingestion status, log entries, and search results.

**Files:**
- Modify: `src/agent_code_analyzer/config.py`
- Add: `src/agent_code_analyzer/control_models.py`
- Add: `src/agent_code_analyzer/control_api.py`
- Modify: `tests/test_config.py`
- Add: `tests/test_control_models.py`

**Contract to define:**
- project list item: name, root path, mode, indexed_at, file_count, symbol_count, languages, status
- ingestion job: job_id, project, action, phase, started_at, updated_at, processed_count, total_count, percent_complete, last_error
- log entry: timestamp, level, logger, project, job_id, message, source file if available
- search result envelope: result_type, index_type, project, file_path, symbol_name, line range, source link, related index links

**Verification:**
- config loads the new control-plane settings with safe defaults
- model serialization is deterministic and round-trips cleanly in tests
- the plan stays compatible with the current MCP tool surface

### Task 2: Decide the shared service boundary

**Objective:** Make the control API and MCP tools call the same service layer instead of duplicating business logic.

**Files:**
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`

**Boundary decision:**
- the service layer owns project lifecycle and ingestion orchestration
- the MCP server stays as a transport wrapper
- the new HTTP API reuses the same service functions
- offboarding must remove project metadata and both index families in one transactionally safe flow

**Verification:**
- MCP calls still work after the service split
- the new boundary is clean enough that the dashboard can use it without special agent logic

---

## Milestone 2: Project lifecycle control

### Task 3: Implement project offboarding

**Objective:** Add a supported way to remove a project from the analyzer and all related indexes.

**Files:**
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/lexical_index.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Add: `tests/test_project_offboarding.py`

**Expected behavior:**
- remove project metadata from the registry
- delete lexical records for the project
- delete semantic/vector records for the project
- preserve unrelated projects
- return a clear status payload for the dashboard and the API

**Verification:**
- offboarding a known project leaves no lingering records in the project summary tables
- the project no longer appears in `list_projects`
- a repeated offboard request returns a safe not-found or already-removed response

### Task 4: Add asynchronous ingestion jobs and progress reporting

**Objective:** Make reingestion observable instead of opaque, with a job record and progress snapshots.

**Files:**
- Add: `src/agent_code_analyzer/ingestion_jobs.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/project_storage.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/semantic_agent.py`
- Add: `tests/test_ingestion_jobs.py`

**Progress fields to capture:**
- current phase: discover, parse, lexical, semantic, finalize, failed, complete
- counts: processed files, total files, processed symbols, total symbols
- timestamps: queued_at, started_at, updated_at, completed_at
- outcome: success, failure, cancellation
- error detail and last successful step

**Verification:**
- a running ingest job can be polled without guessing at internal state
- the job state updates during each phase
- failures are visible in the job record and in logs

### Task 5: Expose project onboarding and reingestion through a shared API

**Objective:** Provide a non-agent endpoint surface for listing projects, onboarding, offboarding, and reingestion.

**Files:**
- Add: `src/agent_code_analyzer/control_api.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_control_api.py`

**Endpoints to plan for:**
- `GET /api/projects`
- `POST /api/projects`
- `DELETE /api/projects/{project}`
- `POST /api/projects/{project}/reingest`
- `GET /api/projects/{project}/status`
- `GET /api/projects/{project}/jobs`

**Verification:**
- each endpoint returns a predictable JSON envelope
- the API can be used without any MCP agent transport
- the same underlying service call powers both the API and MCP wrappers

---

## Milestone 3: Search, source links, and related-index references

### Task 6: Normalize search result envelopes across all index types

**Objective:** Make tree-sitter, lexical, semantic, and AST results look like one coherent operator surface.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/search_rank.py`
- Modify: `src/agent_code_analyzer/search_scoring.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/lexical_index.py`
- Add: `src/agent_code_analyzer/search_envelopes.py`
- Add: `tests/test_search_envelopes.py`

**Result fields to include:**
- index type: tree-sitter, lexical, semantic, AST
- scope type: file, class, function, method, chunk, project
- source identifiers: project, file_id, symbol_id, sqlite_uri, file_path
- source coordinates: start/end rows and columns when available
- source link: a direct file reference with line numbers
- related index links: pointers to the same file or symbol in the other index families

**Verification:**
- every result type exposes the same minimum metadata
- source links can be reconstructed from the API output alone
- related index links are not hidden in ad hoc flags

### Task 7: Add dedicated query endpoints for tree-sitter, lexical, semantic, and AST search

**Objective:** Give the dashboard a clear API for each search mode instead of forcing it through one opaque generic call.

**Files:**
- Modify: `src/agent_code_analyzer/control_api.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_control_api_search.py`

**Planned query surface:**
- `GET /api/search/tree-sitter`
- `GET /api/search/lexical`
- `GET /api/search/semantic`
- `GET /api/search/ast`
- `GET /api/search/unified`

**Verification:**
- each search mode can be queried independently
- the unified search response clearly labels which backend produced each result
- source code links and related index links are present in the JSON response

### Task 8: Add source-code drill-through for search hits

**Objective:** Let operators jump from a result to the actual source snippet and owning symbol.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_source_links.py`

**Expected behavior:**
- search results include direct links to file snippets and symbol anchors
- line ranges are preserved for files, classes, and methods
- the dashboard can render a “view source” action without inventing its own mapping

**Verification:**
- a search hit on a method exposes the file path, method name, and source span
- a file-level result exposes a file snippet reference and the project context

---

## Milestone 4: Logging and instrumentation

### Task 9: Make ingestion and search events queryable

**Objective:** Add enough structure to logs that operators can search them from the dashboard.

**Files:**
- Modify: `src/agent_code_analyzer/logging_config.py`
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/semantic_agent.py`
- Add: `src/agent_code_analyzer/log_query.py`
- Add: `tests/test_log_query.py`

**Instrumentation fields to emit:**
- project name
- job id
- ingestion phase
- backend name
- request identifier
- elapsed time
- error class and message
- row counts for files, symbols, lexical hits, and semantic hits

**Verification:**
- logs can be filtered by project and job id
- the dashboard can search logs without reading raw files directly
- ingest failures surface in a structured way

### Task 10: Add log indexing or a small log-search store

**Objective:** Support log search without turning the dashboard into a filesystem scraper.

**Files:**
- Add or modify: `src/agent_code_analyzer/project_storage.py`
- Add: `src/agent_code_analyzer/log_index.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `tests/test_log_index.py`

**Approach to choose:**
- either a small sqlite FTS5 log table
- or a rolling structured log mirror table keyed by project/job/timestamp

**Verification:**
- the log store can answer time-range and keyword queries
- recent failures are easy to retrieve from the dashboard
- the storage approach does not slow down ingestion materially

---

## Milestone 5: PHP dashboard

### Task 11: Scaffold the PHP dashboard shell

**Objective:** Create a lightweight browser UI that talks only to the new control API.

**Files:**
- Add: `dashboard/composer.json`
- Add: `dashboard/public/index.php`
- Add: `dashboard/public/assets/app.css`
- Add: `dashboard/src/ApiClient.php`
- Add: `dashboard/src/Config.php`
- Add: `dashboard/src/Controller/ProjectController.php`
- Add: `dashboard/src/Controller/SearchController.php`
- Add: `dashboard/src/Controller/LogController.php`
- Add: `dashboard/templates/layout.php`
- Add: `dashboard/templates/projects.php`
- Add: `dashboard/templates/project-detail.php`
- Add: `dashboard/templates/search.php`
- Add: `dashboard/templates/logs.php`

**UI pages to include:**
- project list with status and ingestion state
- project detail with offboard and reingest controls
- search page with tabs for tree-sitter, lexical, semantic, and AST
- logs page with filters and result drill-down

**Verification:**
- the dashboard loads without needing an MCP client
- the project list renders from API data
- the dashboard can submit onboarding and reingestion actions

### Task 12: Add dashboard actions and result drill-down

**Objective:** Let the operator manage projects and inspect search hits from the same page flow.

**Files:**
- Modify: `dashboard/src/Controller/ProjectController.php`
- Modify: `dashboard/src/Controller/SearchController.php`
- Modify: `dashboard/src/Controller/LogController.php`
- Add: `dashboard/templates/partials/*.php`

**Expected behavior:**
- onboarding form posts a project name and root path
- offboard action asks for confirmation before removal
- reingest action shows the job id and live progress state
- search results open source references and related index references

**Verification:**
- the dashboard can operate against a running local analyzer
- the result drill-down includes enough metadata to reach source without guessing

---

## Milestone 6: Safety, access, and deployment hardening

### Task 13: Lock down the control plane

**Objective:** Keep the administrative API safe enough for shared use.

**Files:**
- Modify: `src/agent_code_analyzer/config.py`
- Modify: `src/agent_code_analyzer/control_api.py`
- Add: `tests/test_control_api_security.py`
- Add: `docs/control-plane.md` or a similar operator note

**Security decisions:**
- bind only to the intended host or localhost by default
- require a shared secret or reverse-proxy authentication if exposed beyond localhost
- keep mutating endpoints separate from read-only search endpoints
- log admin actions with project and actor context where available

**Verification:**
- read-only and mutating endpoints are clearly separated
- the default deployment does not accidentally expose admin actions publicly

### Task 14: Verify the full operator workflow end-to-end

**Objective:** Prove the dashboard and control API work together before calling the feature done.

**Files:**
- Add: `tests/test_end_to_end_control_flow.py`
- Add: `dashboard/tests/` or a small PHP smoke script if a PHP test runner is not present

**End-to-end scenarios:**
- list projects
- onboard a new project
- start reingestion
- watch ingestion progress move forward
- search logs for the job id
- query lexical and semantic results
- follow source links from a result
- offboard the project and verify cleanup

**Verification:**
- the Python test suite passes
- the dashboard lints cleanly
- a manual browser smoke test can complete the full lifecycle

---

## Acceptance criteria

This work is complete when:
- the analyzer exposes a non-agent control API for project lifecycle and search
- ingestion progress is visible and queryable
- logs are searchable from the dashboard
- search responses include source-code links and related-index references
- the PHP dashboard can manage projects and inspect results without MCP tooling
- the existing MCP server continues to function for agent use

## Recommended implementation order

1. define the shared models and control-plane boundary
2. add offboarding and ingestion job state
3. normalize search envelopes and source links
4. instrument and query logs
5. build the PHP dashboard shell
6. lock down and verify the whole operator flow

## Notes

- Keep the MCP tools as thin wrappers around the shared service layer.
- Do not force the dashboard through the agent transport; the whole point is a non-agent operator path.
- Prefer result envelopes that are explicit about index type and source link rather than clever but ambiguous.
- If the ingest process is already running, let the control plane report its state instead of creating a second parallel ingestion mechanism.
