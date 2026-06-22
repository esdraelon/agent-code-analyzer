# Agent Code Analyzer Ingestion Recovery and Gap Reconciliation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Harden the analyzer so ingestion resumes safely after restarts and can detect and reconcile filesystem changes that occurred while the watcher was offline or missed by `fswatch`.

**Architecture:** Keep `fswatch` as the primary low-latency signal, but add durable ingestion state and a startup reconciliation path that compares on-disk reality against the last known indexed state. The watcher should recover after process restarts, reload pending work from persisted state, and run a periodic gap sweep that finds files changed while offline or missed by event delivery. The service layer should own the reconciliation logic so both the MCP runtime and any future control plane can trigger the same resume and gap-ingestion behavior.

**Tech Stack:**
- Python 3.11+ for the analyzer runtime
- Existing sqlite project metadata and per-project databases
- Current Tree-sitter / lexical / semantic pipeline
- `fswatch` for event-driven refreshes
- pytest for verification

---

## Current behavior to preserve

The repository already has:
- an `fswatch`-driven watcher service
- a debounce queue for dirty projects
- periodic safety sweeps in the watcher loop
- project scanning and `sync_project_tree()` diff logic
- semantic refresh and rebuild operations
- structured project metadata and freshness tracking

What this plan adds:
- durable restart recovery for ingestion state
- gap detection when `fswatch` misses changes
- startup reconciliation after downtime
- explicit resume semantics for in-flight or interrupted ingestion work
- tests that prove the analyzer catches up after missed events

---

## Milestone 1: Persist ingestion state for restart recovery

### Task 1: Define a durable ingestion state record

**Objective:** Introduce a stable record for “what was being ingested” so the watcher can resume after restart.

**Files:**
- Add: `src/agent_code_analyzer/ingestion_state.py`
- Modify: `src/agent_code_analyzer/project_storage.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Modify: `tests/test_ingestion_state.py`

**State fields to capture:**
- project name
- mode: `watch`, `gap_sweep`, `semantic_refresh`, `semantic_rebuild`, or `manual_sync`
- current phase
- queued/start/update/finish timestamps
- last processed file path
- last processed file hash or mtime snapshot
- pending file count / total file count
- error state if the job stopped unexpectedly

**Verification:**
- the record can be written and read back deterministically
- the state schema is compatible with the existing sqlite layout
- a restarted process can identify unfinished work from the persisted record

### Task 2: Persist watcher checkpoints during sync work

**Objective:** Update the sync pipeline so it leaves behind a usable checkpoint during long runs.

**Files:**
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/semantic_agent.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Add/modify tests under `tests/`

**Checkpoint behavior:**
- write a checkpoint before a project sync starts
- update the checkpoint after each file or phase boundary
- mark the checkpoint complete only after lexical and semantic updates finish
- mark the checkpoint failed if an exception interrupts the run

**Verification:**
- an interrupted run leaves a resumable checkpoint instead of a silent half-state
- the checkpoint reflects the last successful phase
- successful runs clear or close the checkpoint cleanly

---

## Milestone 2: Resume ingestion after restart

### Task 3: Add startup recovery for unfinished ingestion work

**Objective:** Make the analyzer resume any incomplete work when the process starts back up.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `tests/test_restart_recovery.py`

**Recovery behavior:**
- load persisted ingestion checkpoints at startup
- identify projects with incomplete work
- re-enqueue those projects automatically
- avoid duplicate ingestion if the project already finished cleanly
- preserve the original project order or priority where possible

**Verification:**
- a restart with unfinished work re-queues the missing jobs
- completed projects do not get re-ingested unnecessarily
- restart recovery does not require manual operator intervention

### Task 4: Expose a resume path for manual recovery

**Objective:** Give the runtime a direct way to resume work that was interrupted while offline.

**Files:**
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_resume_ingestion.py`

**Expected behavior:**
- a project can be explicitly resumed from its saved checkpoint
- resume uses the current on-disk state rather than stale assumptions
- resume is safe to call repeatedly

**Verification:**
- resuming an interrupted project continues from the saved state
- resuming a clean project is a no-op or a safe confirmation response

---

## Milestone 3: Gap ingestion for missed filesystem changes

### Task 5: Add a gap-scan that compares disk against the last indexed state

**Objective:** Detect files that changed while `fswatch` was offline, overloaded, or otherwise blind.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `src/agent_code_analyzer/gap_ingestion.py`
- Add: `tests/test_gap_ingestion.py`

**Gap-scan inputs:**
- current project roots from the registry
- last indexed file metadata from sqlite
- current file snapshots from disk

**Gap-scan outputs:**
- changed files not seen by watcher events
- deleted files
- newly added files
- files whose hashes or mtimes diverge from the stored snapshot

**Verification:**
- a changed file with no watcher event is still detected
- a deleted file is removed from indexes during the gap pass
- a newly added file gets indexed on the next reconciliation pass

### Task 6: Schedule periodic gap reconciliation

**Objective:** Make missed-change recovery automatic instead of relying on a manual scan.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/config.py`
- Modify: `tests/test_watcher.py`

**Scheduling behavior:**
- run a periodic project reconciliation sweep even when `fswatch` is healthy
- use a configurable interval for the gap sweep
- throttle the sweep so it does not compete with active ingestion unnecessarily
- keep the sweep separate from the debounce queue used for live events

**Verification:**
- the watcher eventually catches missed changes even without new events
- the sweep interval is configurable and covered by tests
- the reconciliation does not duplicate work already handled by the event queue

### Task 7: Make offline detection explicit

**Objective:** Detect when the watcher has been down long enough that a reconciliation pass should be forced on restart.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/freshness.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `tests/test_offline_detection.py`

**Offline signals to track:**
- watcher last-started time
- last successful fswatch event time
- last successful reconciliation time
- projects marked dirty while the watcher was unavailable
- gap between on-disk snapshots and indexed snapshots

**Verification:**
- if the watcher was offline, the next start triggers a reconciliation sweep
- dirty projects are not silently forgotten across restarts
- the analyzer can explain why a gap sweep was forced

---

## Milestone 4: Observability and operator feedback

### Task 8: Emit ingestion recovery and gap-ingestion logs

**Objective:** Make recovery actions visible enough to debug missed-change issues quickly.

**Files:**
- Modify: `src/agent_code_analyzer/logging_config.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_sync_steps.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add: `tests/test_recovery_logging.py`

**Log events to add:**
- watcher startup and shutdown
- resumed checkpoint recovery
- gap sweep start/end
- file-level reconciliation decisions
- recovery failures and retry decisions

**Verification:**
- logs clearly distinguish live `fswatch` events from offline gap reconciliation
- the operator can tell why a project was re-indexed
- error conditions include enough context to debug the missed change

### Task 9: Surface recovery status in the existing project status payloads

**Objective:** Let users and future dashboards see whether a project is currently healthy, catching up, or overdue for a reconciliation pass.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/project_repository.py`
- Add: `tests/test_project_status_recovery.py`

**Status fields to consider:**
- watcher state: running, restarted, offline, recovering
- last checkpoint age
- last gap sweep time
- stale-detection flag
- recovery queue depth

**Verification:**
- project listings show whether recovery is active or stale
- the status payload is enough to drive a future dashboard widget

---

## Milestone 5: End-to-end validation

### Task 10: Add restart and gap-ingestion integration tests

**Objective:** Prove the full recovery loop with real file changes and restart conditions.

**Files:**
- Add: `tests/test_restart_and_gap_ingestion_e2e.py`
- Modify: existing watcher and sync tests as needed

**Scenarios to cover:**
- watcher running normally handles live changes
- watcher is stopped, files change on disk, watcher restarts, gap sweep catches the missed changes
- ingestion is interrupted mid-run, restart resumes from the checkpoint
- deleted files stay deleted after reconciliation
- newly added files are indexed after recovery

**Verification:**
- the test suite proves the analyzer catches up after downtime
- restart recovery and gap ingestion do not regress normal watcher behavior

---

## Acceptance criteria

This work is complete when:
- ingestion can resume after process restart without losing unfinished work
- missed on-disk changes are reconciled even if `fswatch` never reported them
- gap ingestion runs automatically and can also be forced manually
- the runtime emits clear logs for recovery and reconciliation actions
- the existing live watcher path still works as before

## Recommended implementation order

1. define durable ingestion checkpoints
2. persist checkpoints during sync
3. add startup resume recovery
4. implement gap scan and periodic reconciliation
5. add offline detection
6. improve logs and status payloads
7. verify the restart and gap-ingestion scenarios end to end

## Notes

- Treat `fswatch` as a signal source, not the source of truth.
- Use sqlite-backed snapshots and project state to decide whether a file truly needs reprocessing.
- Prefer one reconciliation path shared by startup recovery and periodic gap sweeps.
- Keep the recovery behavior deterministic so it can be tested without relying on timing luck.
