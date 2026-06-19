# Design: Full-Project Mass Ingestion

## Purpose

Rebuild the semantic layer from scratch when the project needs a clean refresh.

## How it works

The ingestion coordinator runs a fixed sequence:

1. discover project scopes
2. build the context for each scope
3. call the semantic writer
4. map the result to storage payloads
5. persist the new records

The pipeline should be idempotent: rerunning it against the same source tree should not create duplicates.

## How it is used

- Cold start rebuilds
- Manual repair after a major refactor
- Baseline refresh before enabling incremental updates

## Design pattern

**Template Method + Coordinator**

Why it fits:
- the overall sequence is fixed
- each step can be specialized or mocked
- orchestration is clearer when the pipeline is explicit

## Verification targets

- A whole-project rebuild produces the full semantic record set.
- Re-running the rebuild remains safe.
- The coordinator remains thin enough to test step-by-step.
