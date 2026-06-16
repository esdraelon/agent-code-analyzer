# Full-Codebase Embedding Search and Intent Analysis Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Keep Tree-sitter as the structural anchor and improve lexical + semantic retrieval as a high-signal addendum, so the model sees only the smallest relevant source slices instead of large grep/find dumps.

**Architecture:**
Use sqlite as the source of truth for project/file/symbol metadata, and use the vector layer as a project-scoped retrieval index on top of that data. Split retrieval into two paths: exact/lexical search for precise matching, and embedding search for semantic similarity. Trigger both incremental embedding refreshes and intent-analysis refreshes from filesystem change events so the index stays current without requiring manual reindexing.

**Tech Stack:**
- Python 3.11+
- sqlite3
- qdrant-client
- Tree-sitter parsing already in the repo
- filesystem watcher / fswatch integration
- pytest
- agent-driven analysis for intent summaries

---

## Background

The current vector index stores code snippets and metadata in Qdrant, but the vector values are deterministic placeholders derived from a hash of the text. That makes the index stable and testable, but it is not a true learned embedding model.

This plan introduces two new capabilities:

1. **Real embedding search**
   - produce actual learned vectors for code chunks
   - support project-scoped search across the whole codebase
   - preserve exact/lexical lookup for precise matches

2. **Intent analysis**
   - run a deeper semantic pass over each component
   - store component-level summaries, responsibilities, and boundaries
   - make those summaries queryable alongside structural code data

---

## Milestone 6: Full-codebase embedding search and intent analysis

**Status:** merged
**Note:** The initial ranking and hybrid-search pass landed and was merged on the feature branch; the remaining work below is now follow-up hardening and search-quality refinement.

**Development verification:**
- Run the ORK3 integration-eval skill during implementation, not just after the milestone lands.
- Record each ORK3 response with date/time, plan step, relevant commit, and relevant branch.
- Keep the running log in `docs/plans/2026-06-15-ork3-eval-log.md`.

**Objective:** Build a real vector-backed retrieval system for the full codebase and add intent-analysis artifacts that explain component purpose and ownership boundaries.

**Planned shape:**
- Keep Tree-sitter calls separate from retrieval: use structural tools to shortlist files/symbols, then apply lexical and semantic search as addenda.
- Replace the current hash-derived vectors with a real embedding model.
- Embed richer structural context, not just raw source, so file path, symbol name, signature, and skeleton all contribute to the vector.
- Rank lexical hits with exact identifier/token matches ahead of loose substring hits.
- Penalize generated/minified content so it does not swamp useful code.
- Index the entire codebase in project-scoped chunks.
- Reindex changed files automatically from filesystem events.
- Keep exact search and semantic search as separate retrieval modes.
- Add agent-produced intent summaries for modules, services, and other meaningful code units.
- Persist intent data so it can be queried by the MCP server and reused during analysis.

**Likely files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/server.py`
- Possibly create: `src/agent_code_analyzer/embedding_index.py`
- Possibly create: `src/agent_code_analyzer/intent_analysis.py`
- Add tests under `tests/`
- Possibly add docs under `docs/decisions/`

**Success criteria:**
- The whole codebase can be indexed and searched.
- File edits automatically refresh the affected retrieval data.
- Exact search can find precise symbols or snippets.
- Semantic search can find related code even when names differ.
- Intent summaries help explain what a component does and where it belongs.

---

### Task 1: Define the embedding and chunking model

**Objective:** Decide what gets embedded, how large each chunk should be, and what metadata each chunk must carry.

**Files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `docs/decisions/embedding-chunking.md`

**Discussion points to settle before coding:**
- Should the primary unit be a file, a symbol, a function/class, or all of the above?
- Should the system embed raw source text, AST skeletons, symbol signatures, or a mix?
- Should the index store one embedding per chunk, or both chunk-level and file-level embeddings?
- Do we want a sliding-window chunker for long files?
- What metadata must always be attached for project scoping and exact retrieval?

**Verification:**
- The chosen chunking strategy is documented.
- Every chunk has stable identifiers and project-scoped metadata.

---

### Task 2: Add a real embedding provider behind a narrow interface

**Objective:** Replace the hash-based vector generator with a real embedding implementation while preserving a testable interface.

**Files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `src/agent_code_analyzer/embedding_provider.py`
- Modify: `tests/test_vector_index.py`

**Step 1: Write failing test**

```python
def test_embedding_provider_returns_real_vector_shape():
    vector = embed_text("def hello(): pass")
    assert isinstance(vector, list)
    assert len(vector) > 0
```

**Step 2: Implement the provider interface**
- Keep the vector index calling a single embedding function.
- Make the provider swappable so tests can use a fake backend.

**Step 3: Verify**
- Unit tests confirm the provider returns consistent dimensions.
- The index still upserts points successfully.

---

### Task 3: Reindex the entire codebase from filesystem events

**Objective:** Ensure the watcher refreshes embeddings for all changed files and keeps the semantic index aligned with the sqlite source of truth.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/project_service.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `tests/test_watcher.py`
- Modify: `tests/test_vector_index.py`

**Step 1: Write failing tests**
- Confirm file changes enqueue reindex work.
- Confirm deleted files remove their vector records.
- Confirm unchanged files do not rewrite unnecessarily.

**Step 2: Implement incremental refresh**
- Use the watcher to trigger embedding refreshes.
- Keep project-scoped deletes before upserts for changed files.
- Preserve bootstrap behavior for cold starts.

**Step 3: Verify**
- Editing a file updates its vector records.
- Deleting a file removes all related points.
- A full project bootstrap rebuilds the semantic index.

---

### Task 4: Add exact/lexical search alongside semantic search

**Objective:** Give the server a direct exact-search path so users can find precise symbols, names, or snippets without relying on embeddings.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Possibly create: `src/agent_code_analyzer/text_search.py`
- Modify: `tests/test_server_helpers.py`

**Discussion points to settle before coding:**
- Should exact search scan sqlite, stored chunk text, or both?
- Should it support substring matching, token matching, or both?
- Should the result shape differ from semantic search or stay unified?
- Should exact search prefer symbols, files, or both by default?

**Step 1: Write failing tests**
- Confirm exact search returns symbol/file matches.
- Confirm project filters still apply.
- Confirm exact and semantic searches can coexist cleanly.

**Step 2: Implement the lexical search path**
- Search stored text and metadata directly.
- Preserve project scoping.
- Return results in a predictable rank order.

**Step 3: Verify**
- Exact matches surface the expected file or symbol.
- Search remains project-scoped.

---

### Task 5: Add intent analysis for components

**Objective:** Produce component-level semantic summaries that explain responsibilities, boundaries, and likely ownership.

**Phase:** defer this until the end of the milestone, after exact/semantic retrieval and the end-to-end validation pass.

**Files:**
- Possibly create: `src/agent_code_analyzer/intent_analysis.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under `tests/`

**Discussion points to settle before coding:**
- What counts as a component: file, module, class, service, or package?
- Should intent summaries be one per file, or one per meaningful unit inside the file?
- Should we store intent text in sqlite, Qdrant payloads, or both?
- Should intent analysis run synchronously on change, or be queued as a background pass?
- Do we want the intent layer to summarize architecture boundaries, dependencies, and risk areas?

**Step 1: Write failing tests**
- Confirm intent data can be stored and read back.
- Confirm intent queries return the right component-level summary.

**Step 2: Implement minimal intent storage**
- Store a stable summary for each analyzed component.
- Link the summary back to project, file, and symbol metadata.

**Step 3: Verify**
- A component returns a stable intent summary.
- The summary is project-scoped and queryable.

---

### Task 6: Expose retrieval and intent results through the MCP server

**Objective:** Make the new search and analysis features available through the existing server surface.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `docs/prompts/agent-code-analyzer-mcp-prompt.md`
- Modify: `tests/test_server_helpers.py`

**Step 1: Write failing tests**
- Confirm the server exposes the new retrieval tools.
- Confirm the prompt tells users when to use exact search, semantic search, and intent analysis.

**Step 2: Wire the tools**
- Keep existing structural tools intact.
- Add new endpoints for exact search and intent lookup if needed.

**Step 3: Verify**
- The MCP server exposes the new capabilities.
- The prompt reflects the new recommended workflow.

---

### Task 7: Validate the new indexing pipeline end to end

**Objective:** Prove the real embedding path, exact search path, and intent analysis path work together on a live project.

**Files:**
- Modify: `tests/test_vector_index.py`
- Modify: `tests/test_server_helpers.py`
- Possibly add integration tests under `tests/`

**Verification ladder:**
- run the focused unit tests for indexing and search
- run the server helper tests
- run the full test suite
- run the ORK3 integration-eval skill with the fixed benchmark queries and compare baseline versus candidate usefulness
- verify a sample project can be indexed, searched, and summarized

**Success criteria:**
- Search works after a fresh bootstrap.
- Search still works after file edits.
- Intent summaries remain attached to the right component.
- The whole pipeline is testable and repeatable.

---

## Completed Work

The following design decisions are already settled and should stay out of the forward-looking implementation flow:

1. **Embedding source**
   - raw source for sure
   - source + symbol signatures is strongly preferred
   - AST skeletons should be used as a *hierarchy signal*, not as a global standalone blob
   - the practical default is a hybrid: source text + symbol signature + lightweight structural outline

   **Preferred direction:**
   - keep source text so exact snippets remain selectable and refactorable
   - keep symbol signatures so the retriever can bias toward callable/renameable units
   - add a compact AST/skeleton summary only at the module/class/method level to express abstraction order
   - avoid a full repo-wide AST dump, which would be too noisy and could drown the agent in structural detail

   **Result typing:**
   - every record should declare what kind of unit it represents: `module`, `class`, `method`, or `file`
   - query results should surface that type so the agent can prefer higher-level abstractions when appropriate

2. **Chunk unit**
   - use *both* file-level and symbol-level records
   - file-level records preserve broad context and support whole-file retrieval
   - symbol-level records capture class/method/function-level precision
   - sliding windows are optional fallback chunks for long files or dense regions that do not map cleanly to a single symbol

   **Preferred direction:**
   - index every file as a whole-file record
   - index every meaningful symbol as a separate record
   - only add sliding-window chunks if a file is long, heavily procedural, or has important logic that crosses symbol boundaries

3. **Exact search behavior**
   - exact search is an *addendum* to semantic/vector responses, not a separate maze of tools
   - keep the tool surface flat: one retrieval call can return semantic hits plus attached exact-match candidates
   - exact matches may come from sqlite, stored payload text, or both
   - the response should make it obvious which hits are semantic and which are exact
   - it is acceptable to attach exact-match metadata to a semantic result as a companion list when that improves usefulness

   **Possible exact-match modes:**
   - substring matching
   - token/term matching
   - sqlite-backed lookup
   - search both sqlite and vector payload text

4. **Intent analysis scope**
   - intent analysis should exist at multiple abstraction levels:
     1. whole project
     2. individual modules
     3. class or file
     4. individual methods or functions
     5. chunks of methods or functions driven by tree-sitter / AST
   - the intent prompt should ask the agent to explain:
     - why the code exists
     - what the code does
     - why it is organized this way
     - how it interacts with other components in the codebase
   - onboarding must be controllable:
     - off
     - or pick a specificity level from 1 to 5
   - intent should be returned as *adjunct metadata* for normal searches, not as a separate destination the user must remember
   - if a fine-grained intent is not available, attach the nearest higher-level intent that exists
   - the fallback ladder should prefer the closest available abstraction level rather than returning nothing

5. **Refresh timing**
   - embedding updates should happen as part of the existing fswatch sync-on-change path
   - intent analysis should run through a queued, deduped update queue with debounce because it is slower and more expensive
   - the dedupe/debounce queue should be a reusable abstract primitive, so the same mechanism can back both embedding refreshes and intent refreshes where appropriate
   - the queue should collapse bursts of updates and reset its deadline on repeated changes
   - the queue should be generic enough that the embedding path and intent path can share the same behavior without duplicating orchestration logic

6. **Result shape**
   - support both a compact response model and a two-stage response model
   - default to the two-stage model (#3)
   - compact model (#1): a single semantic response with optional attached exact-match candidates and intent metadata
   - two-stage model (#3): first return compact candidates, then let the caller fetch deeper details for selected hits
   - primary semantic hits may carry attached exact-match candidates and intent summaries when useful
   - the flattened tool surface should keep the agent from having to pick between too many specialist endpoints
   - intent metadata should fall back to the nearest available abstraction level when the exact requested granularity is missing
   - the response contract should be designed to balance useful detail against token and context load

## Test Plan

The implementation should be covered at several levels so the agentic retrieval stack stays trustworthy as it grows.

### 1. Unit tests for chunking and metadata
- verify file-level chunks are created for each supported file
- verify symbol-level chunks are created for methods, classes, and functions
- verify each record declares its `unit_type`
- verify source text, symbol signatures, and structural outlines are attached correctly
- verify hierarchy ordering is preserved in payload metadata

### 2. Unit tests for embedding/provider seams
- verify the vector index calls the embedding provider through a narrow interface
- verify provider injection works with a fake backend
- verify the system can swap between real and fake embeddings without changing callers
- verify vectors are stable in shape and searchable in the test harness

### 3. Unit tests for exact search
- verify substring and token-style matching return the expected candidates
- verify sqlite-backed lookup returns the same structural target when present
- verify exact results can be attached to semantic results as companion metadata
- verify the response marks which hits are semantic vs exact

### 4. Unit tests for intent analysis
- verify intent requests can be stored and fetched at each supported level
- verify fallback to the nearest higher-level intent when a fine-grained intent is unavailable
- verify the intent prompt receives the required fields: why, what, organization, interaction
- verify onboarding level controls the breadth of analysis work

### 5. Queue and debounce tests
- verify the dedupe/debounce queue collapses bursts of updates
- verify repeated changes reset the deadline
- verify the generic queue can be reused for both embedding and intent updates
- verify the queue does not enqueue duplicate work for the same target

### 6. Watcher and sync tests
- verify file edits trigger immediate embedding refreshes through fswatch updates
- verify deleted files remove their associated vector records
- verify bootstrap still reindexes a full project cleanly
- verify intent work is queued rather than run synchronously on every change

### 7. Server and response-shape tests
- verify the MCP server exposes the retrieval and intent surfaces cleanly
- verify the compact response shape stays small and readable
- verify the two-stage response can expand selected hits on demand
- verify fallback intent metadata appears when fine-grained intent is missing

### 8. End-to-end integration tests
- index a sample project
- search for a file, class, and method
- confirm semantic hits include the expected metadata
- confirm exact matches can be attached to semantic results
- confirm intent fallbacks work when only higher-level intents exist
- confirm the full pipeline still passes after file edits and queued refreshes

### 9. Regression and load-safety tests
- verify large or repetitive updates do not flood the queues
- verify response payloads stay bounded enough to avoid runaway token growth
- verify the agent-facing defaults prefer the compact path unless deeper detail is requested
- verify the system remains deterministic enough for CI

---

## Recommended implementation order

1. Decide the embedding and chunking strategy.
2. Add the real embedding provider interface.
3. Add incremental reindexing from watcher events.
4. Add exact/lexical search.
5. Expose the retrieval features in the MCP server.
6. Validate the whole pipeline with tests.
7. Add intent analysis and persistence as the final production step.

---

## Implementation Notes

- Use lightweight dependency injection by constructor or function parameter for the embedding provider, intent analyzer, queue primitive, Qdrant client, and response-shaping logic.
- Avoid a heavyweight DI container or service-locator pattern.
- Keep module-level wrappers thin and use injected collaborators in the core code paths so the system remains testable and easy to swap backend behavior later.

## Post-merge search improvements

If we continue after the merge, the best next gains are search-quality improvements rather than more surface area:

**Current focus:** query normalization and expansion.

**Validation:** targeted unit tests and the full pytest suite passed on this branch.

1. **Query normalization and expansion**
   - normalize punctuation, camelCase, snake_case, and acronym variants
   - expand common aliases and domain terms before lexical lookup
   - preserve an exact-match fast path so normalization never hides literal hits

2. **Better hybrid ranking fusion**
   - fuse lexical, semantic, and structural scores with explicit weights
   - bias toward exact symbol matches for narrow queries
   - down-rank generated, vendored, and minified content more aggressively

3. **Tree-sitter-aware reranking**
   - prefer hits whose symbol kind matches the query intent
   - boost definitions over references when the user is looking for an implementation point
   - surface parent module/class context for small symbol hits

4. **Multi-stage retrieval**
   - shortlist files first, then expand to symbols and chunks inside those files
   - cap result fanout so the agent sees fewer, better candidates
   - keep the current “smallest relevant slice” principle intact

5. **Retrieval evaluation harness**
   - add a repeatable benchmark set for exact, lexical, semantic, and hybrid queries
   - measure precision on symbol/name lookups and recall on concept queries
   - track regressions when ranking weights or chunking rules change

6. **Intent-aware search integration**
   - attach intent summaries to search results as context, not a separate destination
   - use intent metadata to prioritize the most likely owning module or service
   - add fallback behavior when only coarse-grained intent is available

7. **Operational hardening**
   - cache hot queries and repeated project lookups
   - keep refreshes incremental and debounced
   - ensure the ranking path stays deterministic enough for CI and review
