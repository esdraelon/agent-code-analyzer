# Agent Code Analyzer Hardening, Control Plane, and PHP Frontend Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Harden the analyzer so it resumes ingestion after restarts and catches missed on-disk changes, expose a shared non-agent API/control plane for project and query operations, and deliver a Dockerized PHP Slim frontend for operators at `introspect.hal9k.ululuth.com`.

**Architecture:** Keep the current MCP server as the agent-facing transport, but move durable ingestion recovery and control/query logic into shared Python services that can be called from both MCP and HTTP. Add durable watcher checkpoints plus a startup reconciliation path so the analyzer can resume after downtime and run gap ingestion when `fswatch` misses changes. Expose the operational API through a small HTTP control plane, then build a separate PHP 8.4 Slim dashboard in Docker that consumes that API and is routed through the host reverse proxy under the `introspect.hal9k.ululuth.com` site.

**Tech Stack:**
- Python 3.11+ for the analyzer runtime and control API
- Existing sqlite / Qdrant / Tree-sitter stack already in the repo
- `fswatch` for live filesystem events
- PHP 8.4 Slim for the operator frontend
- Docker / Docker Compose for the PHP UI and deployment wiring
- pytest for Python verification
- PHPUnit or containerized smoke checks for the PHP UI

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

Current gaps the plan must close:
- ingestion state is not durable enough to survive restart cleanly
- missed on-disk changes need a forced reconciliation path
- there is no shared non-agent API for project lifecycle and query operations
- the existing results do not yet expose a consistent operator-friendly source/link envelope
- the frontend is not yet a PHP Slim app and there is no `introspect.hal9k.ululuth.com` site wiring

---

## Milestone 1: Hardening and restart

### Task 1: Add durable ingestion checkpoints and resume state

**Objective:** Make ingestion state persistent so the analyzer can resume after restart instead of starting blind.

**Files:**
- Add: `src/agent_code_analyzer/ingestion_state.py`
- Add: `src/agent_code_analyzer/gap_ingestion.py`
- Modify: `src/agent_code_analyzer/project_storage.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Add: `tests/test_ingestion_state.py`

**State to persist:**
- project name
- mode: `watch`, `gap_sweep`, `semantic_refresh`, `semantic_rebuild`, or `manual_sync`
- current phase
- queued / started / updated / completed timestamps
- last processed file path
- last processed file mtime/hash snapshot
- total file count and processed count
- error state if the job stopped unexpectedly

**Verification:**
- the record round-trips through sqlite deterministically
- a restart can identify unfinished work from persisted state
- a completed run clears or closes the checkpoint cleanly

### Task 2: Resume ingestion automatically on startup

**Objective:** Reload unfinished work when the analyzer process comes back up.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `tests/test_restart_recovery.py`

**Recovery behavior:**
- read all active checkpoints at startup
- re-enqueue projects with incomplete work
- avoid duplicate ingestion for already-complete projects
- preserve project ordering or priority when possible
- make the startup recovery path shared by MCP runtime and future API callers

**Verification:**
- a restart with unfinished work resumes automatically
- already-complete projects are not needlessly reprocessed
- the recovery path is idempotent

### Task 3: Add gap ingestion for missed filesystem changes

**Objective:** Reconcile on-disk changes that happened while `fswatch` was offline or blind.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Modify: `src/agent_code_analyzer/config.py`
- Add: `tests/test_gap_ingestion.py`
- Add: `tests/test_offline_detection.py`

**Gap-scan behavior:**
- compare current disk snapshots to the last indexed snapshots in sqlite
- detect changed, deleted, and newly added files
- enqueue projects whose on-disk state diverges from indexed state
- run a periodic sweep even when live events are quiet
- force a reconciliation pass after watcher downtime

**Verification:**
- a file changed while `fswatch` was offline is still discovered
- deletions are reflected in the indexes after reconciliation
- newly added files are indexed on the next sweep
- the sweep interval is configurable and test-covered

### Task 4: Emit recovery and reconciliation instrumentation

**Objective:** Make the hardening path observable enough that missed-change issues are diagnosable.

**Files:**
- Modify: `src/agent_code_analyzer/logging_config.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/freshness.py`
- Add: `tests/test_recovery_logging.py`
- Add: `tests/test_project_status_recovery.py`

**Events and status to surface:**
- watcher startup and shutdown
- resumed checkpoint recovery
- gap sweep start/end
- file-level reconciliation decisions
- forced sweep because the watcher was offline
- project status flags for stale / recovering / healthy

**Verification:**
- logs clearly distinguish live `fswatch` activity from gap reconciliation
- project status payloads can show whether recovery is in progress
- operators can tell why a project was re-indexed

---

## Milestone 2: API control and query plane

### Task 5: Define shared control-plane models and service boundaries

**Objective:** Introduce stable contracts and shared services that both MCP and HTTP can use.

**Files:**
- Add: `src/agent_code_analyzer/control_models.py`
- Add: `src/agent_code_analyzer/control_api.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `tests/test_control_models.py`
- Modify: `tests/test_config.py`

**Contract to define:**
- project list item: name, root path, mode, indexed_at, file_count, symbol_count, languages, status
- ingestion job: job_id, project, action, phase, timestamps, counts, last_error
- log entry: timestamp, level, logger, project, job_id, message, source file if available
- search result envelope: result_type, index_type, project, file_path, symbol_name, line range, source link, related index links

**Verification:**
- model serialization is deterministic
- the service boundary avoids duplicating business logic
- MCP behavior still works after the split

### Task 6: Add project lifecycle and ingestion control endpoints

**Objective:** Expose a non-agent admin surface for project management and reingestion.

**Files:**
- Modify: `src/agent_code_analyzer/control_api.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_control_api.py`
- Add: `tests/test_project_offboarding.py`
- Add: `tests/test_ingestion_jobs.py`

**Planned endpoints:**
- `GET /api/projects`
- `POST /api/projects`
- `DELETE /api/projects/{project}`
- `POST /api/projects/{project}/reingest`
- `GET /api/projects/{project}/status`
- `GET /api/projects/{project}/jobs`

**Expected behavior:**
- onboarding registers the project and captures root path and mode
- offboarding removes metadata and all related indexes
- reingest creates a visible job/state entry
- status reflects current ingestion and recovery state

**Verification:**
- each endpoint returns a predictable JSON envelope
- offboard removes lexical and semantic records for the project
- the same underlying service call is usable from MCP and HTTP

### Task 7: Add query endpoints for tree-sitter, lexical, semantic, AST, and unified search

**Objective:** Give the dashboard explicit query surfaces instead of a single opaque search call.

**Files:**
- Modify: `src/agent_code_analyzer/control_api.py`
- Modify: `src/agent_code_analyzer/search_rank.py`
- Modify: `src/agent_code_analyzer/search_scoring.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/lexical_index.py`
- Add: `src/agent_code_analyzer/search_envelopes.py`
- Add: `tests/test_control_api_search.py`
- Add: `tests/test_search_envelopes.py`

**Planned query surface:**
- `GET /api/search/tree-sitter`
- `GET /api/search/lexical`
- `GET /api/search/semantic`
- `GET /api/search/ast`
- `GET /api/search/unified`

**Response requirements:**
- label every result with its index type and scope type
- include source coordinates when available
- include source-code links with line numbers
- include related index links for the same file or symbol in other indexes

**Verification:**
- each search mode can be queried independently
- unified search states which backend produced each hit
- source and related-index references are reconstructible from API output alone

### Task 8: Add log search and source drill-through

**Objective:** Let operators search logs and jump from results to the relevant source code.

**Files:**
- Add: `src/agent_code_analyzer/log_query.py`
- Add: `src/agent_code_analyzer/log_index.py`
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/logging_config.py`
- Add: `tests/test_log_query.py`
- Add: `tests/test_source_links.py`

**Expected behavior:**
- logs can be searched by project, job id, time range, and keyword
- log entries preserve enough structure for the frontend to filter them
- search results expose direct source and symbol anchors
- related index references are not hidden in ad hoc fields

**Verification:**
- a log query returns structured entries, not raw text blobs
- a method-level search result includes file path, symbol name, and span
- the dashboard can render a “view source” action without guessing mappings

---

## Milestone 3: PHP frontend

### Task 9: Scaffold the PHP Slim frontend in Docker

**Objective:** Create a lightweight PHP operator UI that talks only to the new control API.

**Files:**
- Add: `frontend/composer.json`
- Add: `frontend/Dockerfile`
- Add: `frontend/docker-compose.yml`
- Add: `frontend/public/index.php`
- Add: `frontend/public/assets/app.css`
- Add: `frontend/src/Config.php`
- Add: `frontend/src/ApiClient.php`
- Add: `frontend/src/Controller/ProjectController.php`
- Add: `frontend/src/Controller/SearchController.php`
- Add: `frontend/src/Controller/LogController.php`
- Add: `frontend/templates/layout.php`
- Add: `frontend/templates/projects.php`
- Add: `frontend/templates/project-detail.php`
- Add: `frontend/templates/search.php`
- Add: `frontend/templates/logs.php`

**Frontend requirements:**
- PHP 8.4
- Slim-based routing
- class-based handlers, not route closures
- config-first bootstrap
- containerized verification
- no direct dependency on MCP transport

**Verification:**
- the image builds cleanly in Docker
- the app boots in container
- the frontend can render the project list from API data

### Task 10: Build the operator pages and action flow

**Objective:** Let the operator manage projects, start reingestion, and inspect search/log results from the browser.

**Files:**
- Modify: `frontend/src/Controller/ProjectController.php`
- Modify: `frontend/src/Controller/SearchController.php`
- Modify: `frontend/src/Controller/LogController.php`
- Add: `frontend/templates/partials/*.php`

**UI pages to include:**
- project list with status and recovery state
- project detail with offboard and reingest controls
- search page with tabs for tree-sitter, lexical, semantic, and AST
- logs page with filters and result drill-down

**Expected behavior:**
- onboarding form posts a project name and root path
- offboard action asks for confirmation before removal
- reingest action shows the job id and live progress state
- search results open source references and related index references

**Verification:**
- the browser flow can list projects, start a job, and inspect its progress
- result drill-through reaches the source link without special operator knowledge

### Task 11: Wire the host reverse proxy for `introspect.hal9k.ululuth.com`

**Objective:** Publish the PHP frontend under the new operator hostname using the existing host reverse proxy.

**Files:**
- Modify: the host reverse-proxy vhost / site config for `introspect.hal9k.ululuth.com`
- Modify: deployment notes for the host proxy and TLS wiring
- Modify: `frontend/docker-compose.yml` or a host override if needed

**Deployment behavior:**
- the host reverse proxy routes `introspect.hal9k.ululuth.com` to the PHP Slim frontend
- the frontend is reachable through the domain, not only through localhost
- the reverse proxy config keeps public hostname, upstream, and TLS settings explicit
- Docker networking or published ports are used consistently with the host proxy

**Verification:**
- the hostname resolves to the frontend site
- the reverse proxy serves the correct application instead of a default 404
- HTTPS/TLS works for the public site if the host already uses it
- the upstream container can be restarted without breaking the site mapping

### Current branch status

- Basic PHP Slim frontend scaffold is implemented on the `milestone3-operator-frontend-basic` branch.
- The frontend is serving on local port `40080` and the host reverse proxy now routes `introspect.hal9k.ululuth.com` to that upstream.
- Project list, project detail, search, and job/activity pages are wired to the control API.
- The browser smoke layer still needs deeper end-to-end coverage in a follow-on slice.

### Task 12: Add end-to-end smoke checks for the full operator flow

**Objective:** Prove the analyzer, API, and PHP frontend work together before the plan is considered done.

**Files:**
- Add: `tests/test_end_to_end_control_flow.py`
- Add: `frontend/tests/` or a PHP smoke script if a formal test runner is not in place

**Scenarios to cover:**
- list projects
- onboard a new project
- start reingestion
- watch ingestion progress move forward
- search logs for the job id
- query lexical and semantic results
- follow source links from a result
- offboard the project and verify cleanup

**Verification:**
- the Python suite passes
- the PHP app lints / smoke-checks in Docker
- the public hostname loads through the reverse proxy

---

## Acceptance criteria

This work is complete when:
- ingestion can resume after restart without losing unfinished work
- missed on-disk changes are reconciled even if `fswatch` never reported them
- the analyzer exposes a shared non-agent API for project lifecycle, ingestion, logs, and queries
- search results include source-code links and related-index references
- the PHP Slim frontend can manage the analyzer without MCP tooling
- the frontend is reachable at `introspect.hal9k.ululuth.com`
- the existing MCP server continues to function for agent use

## Recommended implementation order

1. hardening and restart recovery
2. gap ingestion and recovery instrumentation
3. control-plane models and shared service boundary
4. lifecycle and query API endpoints
5. log search and source drill-through
6. PHP Slim frontend scaffold and browser flows
7. host reverse proxy wiring and end-to-end smoke verification

## Notes

- Treat `fswatch` as a signal source, not the source of truth.
- Keep the MCP tools as thin wrappers around shared services.
- Keep the PHP app containerized and config-first; do not splice PHP business logic into the Python analyzer.
- Prefer explicit result envelopes with index type and source links rather than ambiguous search payloads.
- Use the host reverse proxy to publish the PHP frontend under the existing domain rather than inventing a second deployment path.
