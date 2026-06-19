# Design: Retrieval and Quality Verification

## Purpose

Make the new semantic descriptions searchable and prove that they answer the right kind of questions.

## How it works

Retrieval should treat semantic descriptions as a project-scoped search index over natural-language summaries. Queries that ask about architecture should prefer higher-level scopes; queries about behavior or algorithms should prefer class, method, or chunk scopes.

Quality checks should verify that the scope type shown in the result matches the query intent.

## How it is used

- Search for “what owns X?” and get package/module/file summaries.
- Search for “how does Y work?” and get method/chunk summaries.
- Use verification tests to ensure the rankings stay sensible as the branch evolves.

## Design pattern

**Specification + Strategy**

Why it fits:
- the query filter rules should be explicit and testable
- the ranking policy may change as signal quality improves
- the result shape should remain consistent even if the score policy changes

## Verification targets

- Architecture queries return high-level summaries.
- Algorithm queries return detailed scopes.
- Project boundaries are respected.
- The stub writer path remains valid while the real backend is still pending.
