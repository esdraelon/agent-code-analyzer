# Design: Incremental fswatch Diff Refresh

## Purpose

Refresh only the semantic records that were actually affected by file changes.

## How it works

Raw filesystem events are noisy, so the watcher first batches them into a short-lived unit of work. That batch is normalized into explicit commands:

- add
- modify
- delete
- move

Each command is resolved against the semantic scope tree. If a change cannot be mapped confidently, the pipeline falls back to the smallest enclosing scope instead of guessing.

## How it is used

- Edit a file: only the affected scopes refresh.
- Delete a file: the semantic records disappear.
- Move a method or class: lineage is remapped when possible.
- Burst saves: collapse into one refresh batch.

## Design pattern

**Unit of Work + Command + Event Aggregator**

Why it fits:
- the watcher must absorb event bursts before acting
- each change type has explicit behavior
- the batch is the transaction boundary for refresh work

## Verification targets

- Multiple rapid saves collapse into one batch.
- Delete events remove semantic records cleanly.
- Move/refactor events preserve identity where possible.
- Unchanged neighboring scopes remain untouched.
