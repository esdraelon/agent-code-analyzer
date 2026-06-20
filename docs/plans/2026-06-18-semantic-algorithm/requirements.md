# Semantic Description Extension Requirements

> **For Hermes:** Use `subagent-driven-development` only for implementation after these requirements are approved.

**Goal:** Define the low-level requirements for the semantic description extension of `agent-code-analyzer`, milestone by milestone, so implementation can proceed without re-interpreting the plan.

**Scope:** This document covers the semantic-description layer that sits beside existing lexical and source-chunk retrieval. It does not replace source chunks; it adds plain-language summaries and the plumbing needed to generate, store, refresh, and query them.

**Architecture constraints:**
- Tree-sitter remains the structural boundary detector.
- Description text is plain language, not structured JSON.
- Structured metadata is stored alongside description text.
- The agent interface must remain narrow and swappable.
- Full rebuild and incremental refresh are both required operating modes.

---

## Milestone 0 — Agent abstraction and Hermes adapter POC

**Status:** complete

**Purpose:** Establish the normalized agent call surface and prove that the semantic pipeline can call either a fake backend or Hermes through two execution modes.

### Requirements
1. The system shall expose a normalized request object with at least:
   - prompt text
   - optional system prompt
   - arbitrary metadata
   - requested response format
2. The system shall expose a normalized response object with at least:
   - returned content
   - backend identity
   - raw backend output
   - parsed representation
   - response metadata
3. The caller shall interact with agents through a single wrapper/factory layer.
4. The factory shall support exactly these concrete backends for the POC:
   - `FakeAgent`
   - `HermesShellAgent`
   - `HermesLibAgent`
5. The fake backend shall be deterministic and shall return the placeholder text `No detail here`.
6. The fake backend shall write request traces to JSONL when a log directory is provided.
7. The Hermes shell adapter shall invoke Hermes via subprocess using the CLI boundary.
8. The Hermes library adapter shall import Hermes in-process and call the runtime directly.
9. Both Hermes adapters shall normalize their output into the same response shape used by the fake backend.
10. The wrapper shall be suitable for semantic-evaluation calls without requiring the rest of the indexing pipeline to know which backend was used.

### Acceptance criteria
- A caller can invoke all three backends through one wrapper.
- The fake backend is deterministic and traceable.
- The shell and library adapters both satisfy the same request/response contract.
- Tests cover the factory, wrapper, fake backend, shell backend, and library backend.

### Implementation surfaces
- `src/agent_code_analyzer/agents/`
- `tests/test_agents.py`
- `docs/plans/2026-06-18-semantic-algorithm/designs/agent-abstraction.md`

---

## Milestone 1 — Semantic record model and stable identities

**Status:** planned

**Purpose:** Define the canonical record shape for every semantic scope so all later steps can store, refresh, and search the same model.

### Requirements
1. The semantic record shall support these scope levels:
   - package
   - module
   - file
   - class
   - method
   - chunk
2. Every record shall carry a stable identity that can be used for idempotent upserts.
3. Every record shall include the source file path.
4. Every record shall include the symbol name when a symbol exists.
5. Every record shall include a start/end line range when line anchors exist.
6. Every record shall include a source fingerprint or content hash.
7. Every record shall include generated plain-language description text.
8. Every record shall include update-mode metadata identifying whether it was produced by:
   - `mass_ingestion`
   - `fswatch_diff`
9. Every record shall include lineage information linking the record to its parent semantic scope when nested.
10. The record model shall be storage-agnostic; storage mapping must stay separate from record construction.

### Acceptance criteria
- The schema can represent every required scope level.
- The schema can preserve parent/child lineage.
- The schema supports both rebuild and incremental refresh.
- The schema is suitable for retrieval and refresh without requiring code-specific special cases.

### Implementation surfaces
- `src/agent_code_analyzer/vector_index.py`
- `src/agent_code_analyzer/semantic_descriptions.py` if a dedicated model module is needed
- `docs/decisions/semantic-description-schema.md` if a decision record is desired

---

## Milestone 2 — Semantic writer abstraction with a stub implementation

**Status:** planned

**Purpose:** Add a narrow writer interface that can be swapped later, while keeping the current pipeline testable with a no-op sentinel.

### Requirements
1. The semantic writer shall accept a source unit and its metadata.
2. The writer shall return plain-language description text when available.
3. The writer shall support a deliberate no-response sentinel.
4. The writer shall distinguish a deliberate no-response from a transport or runtime failure.
5. The first implementation shall be a stub that returns the sentinel consistently.
6. The stub shall preserve the same call shape that a future real model-backed writer will use.
7. The stub shall be callable from the indexing path without crashing the pipeline.
8. The stub shall remain fully testable without a model dependency.
9. The stub path shall allow later replacement without changing the caller contract.

### Acceptance criteria
- Indexing code can call the writer with no special-case branches.
- Tests prove the sentinel path.
- Tests prove that the no-response case is not conflated with transport failure.
- The writer boundary is narrow enough to swap backends later.

### Implementation surfaces
- `src/agent_code_analyzer/semantic_agent.py` if created
- `src/agent_code_analyzer/vector_index.py`
- `tests/test_semantic_agent.py` if created

---

## Milestone 3 — Tree-sitter-aware chunking for long or complicated methods

**Status:** planned

**Purpose:** Break large or algorithmically dense method bodies into useful semantic chunks while preserving ownership and traceability.

### Requirements
1. Chunk boundaries shall prefer Tree-sitter AST boundaries over raw line counts.
2. Chunk boundaries shall split on meaningful control-flow regions when a method is long or complex.
3. Every chunk shall retain a reference to its parent method.
4. Every chunk shall retain file-level and line-level anchors.
5. Chunking shall avoid trivial fragments that do not add semantic value.
6. Chunking shall keep small methods whole when no split is needed.
7. Chunking shall preserve enough context to describe the algorithm without requiring the entire file.

### Acceptance criteria
- Long methods produce multiple chunks when warranted.
- Small methods remain a single chunk.
- Every chunk can be traced back to its parent method and file.
- Chunk spans remain line-accurate for later refreshes.

### Implementation surfaces
- `src/agent_code_analyzer/semantic_chunking.py` if created
- `src/agent_code_analyzer/vector_index.py`
- `tests/test_semantic_chunking.py`

---

## Milestone 4 — Full-project mass ingestion for all semantic levels

**Status:** planned

**Purpose:** Rebuild the entire semantic description layer in one pass.

### Requirements
1. The ingestion pipeline shall walk the project root once.
2. The pipeline shall derive semantic units from Tree-sitter structure and project metadata.
3. The pipeline shall generate descriptions for every supported semantic level.
4. The pipeline shall write descriptions and embeddings to persistent storage.
5. The pipeline shall be idempotent for the same input tree.
6. The pipeline shall not duplicate records on repeat runs.
7. The pipeline shall preserve stable identities across rebuilds when source content is unchanged.
8. The pipeline shall expose a clear path for later integration through the server layer.

### Acceptance criteria
- A full rebuild emits records for package, module, file, class, method, and chunk levels.
- Re-running mass ingestion does not create duplicate semantic records.
- Record counts are stable for the same input tree.
- The pipeline can be exercised in isolation by tests.

### Implementation surfaces
- `src/agent_code_analyzer/projects.py`
- `src/agent_code_analyzer/vector_index.py`
- `src/agent_code_analyzer/server.py`
- `tests/test_vector_index.py`
- `tests/test_server_helpers.py`

---

## Milestone 5 — Piecewise updates from fswatch diffs

**Status:** planned

**Purpose:** Refresh only impacted semantic records when files change, instead of rebuilding the entire project.

### Requirements
1. File-system events shall be batched into a short-lived update window.
2. Multiple edits to the same file shall be normalized into one contextual update record.
3. Related edits that share a subtree, method, or class shall be grouped into the smallest useful context bundle.
4. Each update record shall carry:
   - project
   - file path
   - change type (`add`, `modify`, `delete`, `move`)
   - old and new path when relevant
   - line range or anchor region
   - Tree-sitter/AST anchor
   - parent scope reference
   - prior description text when available
   - current source snippet or diff hunk
5. The updater shall map changed lines back to the owning package/module/file/class/method/chunk scope.
6. The updater shall invalidate affected records before writing replacements.
7. The updater shall preserve unchanged neighboring scopes.
8. The updater shall treat deletions as explicit record removals.
9. The updater shall treat moves and refactors as rename/remap events when possible.
10. The updater shall fall back conservatively when a change cannot be mapped confidently.

### Acceptance criteria
- Editing one method refreshes only that method and its dependent chunks.
- Editing a class boundary refreshes the owning class and affected children as needed.
- Unchanged files are not rewritten.
- Deletions remove the corresponding semantic records.
- Move/refactor cases preserve identity where possible.
- Multiple rapid saves collapse into one batch.

### Implementation surfaces
- `src/agent_code_analyzer/watcher.py`
- `src/agent_code_analyzer/projects.py`
- `src/agent_code_analyzer/vector_index.py`
- `tests/test_watcher.py`

---

## Milestone 6 — MCP surface for semantic description indexing

**Status:** planned

**Purpose:** Expose the semantic description pipeline through the server so operators can trigger rebuilds and incremental refreshes.

### Requirements
1. The server shall expose a command to trigger a full semantic rebuild.
2. The server shall expose a command to trigger a piecewise refresh for changed files.
3. The server shall present semantic-description mode clearly to callers.
4. The server shall keep the existing lexical and source-chunk paths intact.
5. The server shall remain backwards-compatible for existing tools unless a specific endpoint change is explicitly approved.
6. Prompt guidance shall explain when to use full rebuild versus diff refresh.

### Acceptance criteria
- The MCP surface can initiate both ingestion modes.
- Existing tools continue to function.
- Operators can tell which mode they are invoking.

### Implementation surfaces
- `src/agent_code_analyzer/server.py`
- `docs/prompts/agent-code-analyzer-mcp-prompt.md`

---

## Milestone 7 — Retrieval and quality checks for the semantic description layer

**Status:** complete

**Purpose:** Make the semantic descriptions searchable and verify that level-specific summaries are useful.

### Requirements
1. Retrieval shall prioritize fuzzy semantic intent before lexical matching when querying semantic descriptions.
2. Architecture-oriented queries shall prefer package/module/file descriptions.
3. Behavior- and algorithm-oriented queries shall prefer class/method/chunk descriptions.
4. The search surface shall remain project-scoped.
5. The system shall support tests or checks that validate retrieval quality.
6. The stub path shall remain acceptable during early development.
7. Retrieval shall work in both full-ingestion and incremental-refresh modes.
8. The repeatable retrieval quality harness shall use `FakeAgent` or another deterministic backend before real-provider variance is introduced.

### Acceptance criteria
- Package/module/file results emphasize architecture and intent.
- Class/method/chunk results emphasize algorithmic behavior.
- Project scoping is preserved.
- The stub path is still accepted during early development.
- Both ingestion modes remain searchable.

### Implementation surfaces
- `src/agent_code_analyzer/vector_index.py`
- `src/agent_code_analyzer/projects.py`
- `tests/test_vector_index.py`
- `tests/test_server_helpers.py`

---

## Milestone 8 — Documentation and operator guidance

**Status:** planned

**Purpose:** Make the semantic-description workflow understandable without reading implementation code.

### Requirements
1. Documentation shall define what a semantic description is.
2. Documentation shall explain how the stub agent behaves.
3. Documentation shall explain when to use mass ingestion.
4. Documentation shall explain when to use fswatch diff refresh.
5. Documentation shall explain how Tree-sitter chunking affects method-level summaries.
6. Documentation shall explain how scope levels differ in intent and granularity.
7. Documentation shall remain aligned with shipped behavior.

### Acceptance criteria
- The docs describe both operating modes clearly.
- The docs match the actual server behavior.
- A new developer can understand the workflow from the docs alone.

### Implementation surfaces
- `docs/prompts/agent-code-analyzer-mcp-prompt.md`
- `docs/decisions/semantic-algorithm-design.md` if needed
- `docs/complete/` when the branch graduates from active work

---

## Milestone 9 — Global agent rate limiting and semantic freshness lifecycle

**Status:** planned

**Purpose:** Protect the service from provider throttling while keeping search honest about semantic records that are dirty, obsolete, or in flight during fswatch-driven updates.

### Requirements
1. The service shall enforce one global rate limit across all agent calls.
2. The agent abstraction shall normalize provider-specific rate-limit signals into a common shape.
3. Each concrete agent backend shall implement its own retry-after, backoff, and quota-handling details.
4. Each semantic unit shall track freshness state and a relevance marker, at minimum distinguishing fresh, dirty, and obsolete records.
5. Fswatch deltas shall mark affected semantic units dirty or obsolete before refresh work begins.
6. Successful refresh shall mark a semantic unit fresh and relevant only when the observed source revision or content hash still matches the current source state.
7. The update path shall use revision/hash guards or equivalent compare-and-swap protection so an in-flight refresh cannot overwrite a newer dirty mark.
8. Search shall continue returning dirty or obsolete semantic units, but those results shall be marked as potentially inaccurate.

### Acceptance criteria
- Concurrent agent calls respect one shared service-wide limiter.
- Provider throttling is translated into a normalized retry signal at the abstraction boundary.
- Dirty or obsolete records remain searchable with an explicit stale warning.
- A later fswatch delta cannot be accidentally erased by an older refresh completion.
- Tests cover limiter behavior, freshness promotion, and stale-hit surfacing.

### Implementation surfaces
- `src/agent_code_analyzer/agents/base.py`
- `src/agent_code_analyzer/agents/fake.py`
- `src/agent_code_analyzer/agents/hermes.py`
- `src/agent_code_analyzer/watcher.py`
- `src/agent_code_analyzer/vector_index.py`
- `src/agent_code_analyzer/search_filters.py` if the result envelope needs a staleness flag
- `tests/test_agents.py`
- `tests/test_watcher.py`
- `tests/test_vector_index.py`

---

## Implementation order

1. Agent abstraction and Hermes adapter POC
2. Semantic record model and stable identities
3. Semantic writer abstraction with a stub implementation
4. Tree-sitter-aware chunking
5. Mass ingestion
6. Piecewise fswatch updates
7. MCP surface
8. Retrieval and quality checks
9. Documentation and operator guidance
10. Global agent rate limiting and semantic freshness lifecycle

---

## Global requirements

- The semantic layer shall remain separate from existing lexical search improvements.
- The system shall store semantic descriptions alongside source-derived metadata.
- The system shall not replace source chunks with summaries.
- The writer interface shall remain swappable.
- All record-level updates shall remain line-anchored where possible.
- The service shall apply a global rate limit to agent calls.
- Rate-limit signals from provider services shall be normalized at the agent abstraction boundary.
- Dirty and obsolete semantic records shall remain searchable and explicitly marked as potentially inaccurate.
- State promotion shall be guarded by source revision or content hash checks to avoid in-flight refresh races.
- The requirements doc shall stay milestone-oriented so future implementation work can be tracked against it.

---

## Definition of done

- Every requested scope level can be described.
- The description writer interface exists and can be stubbed.
- Full rebuild and incremental refresh both work.
- Tree-sitter chunking produces stable and useful chunks.
- Semantic retrieval works without breaking existing search paths.
- Agent calls honor a shared service-wide rate limit.
- Freshness transitions keep stale records searchable without pretending they are current.
- The documentation explains the workflow clearly enough for the next implementation pass.
