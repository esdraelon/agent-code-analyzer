# Design: Milestone 5 — Incremental fswatch Diff Refresh

## Purpose

Refresh only the semantic records that were actually affected by file changes, instead of rebuilding the whole project.

## Requirements covered

- batch file-system events into a unit of work
- normalize add / modify / delete / move
- map edits back to the smallest affected scope
- preserve neighboring scopes
- treat deletions as removals
- support rename / remap when possible
- conservative fallback for ambiguous changes

## Current codebase evidence

The watcher already has the right control-flow skeleton in `src/agent_code_analyzer/watcher.py`:

- `DirtyProjectQueue` tracks debounce windows and pending projects (`watcher.py:15-58`)
- `WatchProjectRouter` maps filesystem paths back to projects (`watcher.py:62-87`)
- `WatchProcessManager` owns watcher subprocess lifecycle (`watcher.py:91-114`)
- `ProjectWatcherService` runs the watch loop and the safety sweep (`watcher.py:118-302`)

The current watcher therefore already distinguishes:

- event observation
- queueing
- timed release
- background process supervision

## Design pattern

**Unit of Work + Command + Event Aggregator**

Why it fits:

- the watcher must absorb event bursts before acting
- each change type has explicit behavior
- the batch becomes the transaction boundary for semantic refresh work

## Design details

### 1. Event aggregation

Raw `fswatch` events should be treated as noisy inputs. The aggregator should normalize them into a short-lived batch that captures:

- project
- path
- change type
- old/new path if relevant
- observed time
- diff hunk / anchor data when available

### 2. Unit of work

The batch should be grouped by owning semantic scope before calling the refresh pipeline. That keeps the writer input small and avoids re-describing unrelated code.

### 3. Command mapping

The refresh layer should expose explicit commands:

- add scope
- update scope
- delete scope
- move scope

Each command should map to the smallest confident scope first, then expand only when the anchor is ambiguous.

### 4. Existing watcher reuse

`ProjectWatcherService.observe_event(...)` and `flush_ready_projects(...)` already provide the debounce and dispatch structure. The new semantic diff refresh can reuse that model while changing the payload from "dirty project" to "semantic update batch".

## Proposed file responsibilities

- `src/agent_code_analyzer/watcher.py`
  - event aggregation and batching
  - path-to-project routing
  - process supervision
- `src/agent_code_analyzer/projects.py`
  - diff materialization and source metadata access
- `src/agent_code_analyzer/vector_index.py`
  - record invalidation, replacement, and deletion
- `tests/test_watcher.py`
  - debounce cases
  - deletion cases
  - move/refactor cases
  - safety sweep cases

## Verification targets

- multiple rapid saves collapse into one batch
- delete events remove semantic records cleanly
- move/refactor events preserve identity where possible
- unchanged neighboring scopes remain untouched
