# Design: Semantic Writer Abstraction

## Purpose

Provide a narrow interface that turns source scopes into plain-language semantic descriptions.

## How it works

The caller passes the source slice, the AST outline, the line anchors, and a small instruction contract. The writer returns either:

- a description text payload
- a deliberate no-response sentinel
- a transport/runtime failure

The stub backend deliberately emits the sentinel so the rest of the system can be tested without a model dependency.

For the agent-evaluation workflow, the fake agent strategy logs every request to disk, parses the prompt shape enough to keep the response structurally valid, and always returns the feedback text `No detail here`.

## How it is used

- Mass ingestion calls the writer for every scope.
- Diff refresh calls the writer only for the impacted scopes.
- Tests can inject the stub writer and assert the plumbing still works.

## Design pattern

**Strategy + Null Object + Adapter**

Why it fits:
- Strategy keeps the backend swappable
- Null Object represents the intentional no-op path
- Adapter isolates whatever future model API gets chosen

## Verification targets

- The caller can distinguish no-response from failure.
- The interface remains stable across backend swaps.
- The stub path keeps the indexing code testable from day one.
