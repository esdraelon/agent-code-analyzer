# Semantic Algorithm Architecture Description Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Build a plain-language semantic description layer for code structure and algorithm intent, then index it for retrieval and incremental refresh.

**Architecture:**
Treat Tree-sitter as the structural boundary detector and semantic scopes as immutable records with stable identity. Generate human-readable descriptions for package, module, file, class, method, and chunk scopes, then store the description text plus metadata for semantic retrieval. Keep the semantic layer additive: it sits beside the lexical and source-chunk paths instead of replacing them.

The system has two operating modes:
- **Mass ingestion**: walk the whole project and rebuild all semantic records.
- **Piecewise diff refresh**: consume batched filesystem changes, map them to the smallest affected semantic scopes, and refresh only those records.

**Design pattern map:**
- record model: **Value Object + Data Mapper**
- writer abstraction: **Strategy + Null Object + Adapter**
- Tree-sitter chunking: **Composite + Recursive Descent + Strategy**
- mass ingestion: **Template Method + Coordinator**
- fswatch refresh: **Unit of Work + Command + Event Aggregator**
- MCP surface: **Facade + Command**
- retrieval and quality checks: **Specification + Strategy**
- operator guidance: **Runbook / Playbook**

**Tech Stack:**
- Python 3.11+
- Tree-sitter parsing already in the repo
- sqlite3 for authoritative metadata storage
- qdrant-client for vector payloads / semantic search
- filesystem watcher / fswatch integration
- pytest
- narrow agent interface for description generation

---

## Milestone 0: Agent abstraction and Hermes adapter POC

**Status:** planned

**Objective:** Introduce the layered agent interfaces and prove both Hermes execution modes can be called through the same normalized wrapper.

**Pattern:** **Strategy + Facade + Adapter + Null Object**

**Why this pattern fits:**
The caller needs one general contract, while Hermes-specific concerns belong behind a lower-level adapter boundary. The fake backend keeps the flow deterministic for tests and plan-building, and the shell/lib split lets us compare a subprocess boundary against a direct Python import without changing the caller.

**Deliverables:**
- general agent request / response abstraction
- lower-level Hermes abstraction shared by shell and library adapters
- fake agent backend that returns `No detail here` and logs requests
- Hermes shell adapter that shells out to `hermes chat`
- Hermes library adapter that imports and calls Hermes `AIAgent` in-process
- calling wrapper / factory that selects among the three concrete strategies
- traceable JSONL logs for evaluation requests

**Likely files:**
- Create: `src/agent_code_analyzer/agents/`
- Create: `tests/test_agents.py`
- Modify: `docs/plans/2026-06-18-semantic-algorithm/designs/agent-abstraction.md`
- Modify: `src/agent_code_analyzer/server.py` (later integration point)

**Success criteria:**
- Callers can invoke fake, shell, and library backends through one wrapper.
- The Hermes shell and Hermes library adapters both satisfy the same normalized request / response shape.
- The fake backend remains deterministic and writes request logs to disk.
- The wrapper can be used later as the semantic evaluation POC boundary.

---

## Milestone 1: Semantic record model and stable identities

**Status:** planned

**Objective:** Define the canonical record shape for every semantic scope so every later pipeline stage can read, refresh, and query the same structure.

**Pattern:** **Value Object + Data Mapper**

**Why this pattern fits:**
The record itself should be immutable and easy to compare; the mapping to sqlite/Qdrant should live outside the record so storage concerns do not leak into semantic logic.

**Deliverables:**
- stable record identity for package/module/file/class/method/chunk scopes
- source path, symbol path, and line-range anchors
- parent/child lineage for nested scopes
- description text plus update-mode metadata
- a source fingerprint for refresh detection

**Likely files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `src/agent_code_analyzer/semantic_descriptions.py`
- Possibly create: `docs/decisions/semantic-description-schema.md`

**Success criteria:**
- Every supported scope fits the same record model.
- Records can be compared by stable identity.
- Storage mapping is separate from record creation.

---

## Milestone 2: Semantic writer abstraction with a stub backend

**Status:** planned

**Objective:** Add the narrow write interface that produces semantic descriptions, but start with a sentinel-returning stub so the rest of the plumbing can be tested first.

**Pattern:** **Strategy + Null Object + Adapter**

**Why this pattern fits:**
The caller should talk to a stable writer interface, while the backend can be replaced later. The stub is a Null Object that intentionally does nothing but still distinguishes “no response” from “transport failure.”

**Deliverables:**
- semantic writer interface with one narrow call shape
- stub implementation that returns a no-response sentinel
- error handling that separates deliberate no-op from runtime failure
- swap-ready boundary for a future model-backed backend
- fake agent strategy implementation for evaluation runs that logs requests to disk
- placeholder responses that always preserve valid output shape while returning `No detail here`

**Likely files:**
- Possibly create: `src/agent_code_analyzer/semantic_agent.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `tests/test_semantic_agent.py`

**Success criteria:**
- Indexing code can call the writer without special-case branches.
- Tests can prove the sentinel path without a model dependency.

---

## Milestone 3: Tree-sitter chunking and scope partitioning

**Status:** planned

**Objective:** Split long or complex regions into useful semantic chunks without losing the parent scope.

**Pattern:** **Composite + Recursive Descent + Strategy**

**Why this pattern fits:**
The code tree is already hierarchical, so chunking should follow the AST. Recursive descent chooses where to split, while a chunking strategy decides whether to split by class, method, control flow, or fallback line spans.

**Deliverables:**
- AST-aware scope traversal
- chunk splitting for long methods and complex branches
- parent method / class lineage retained for each chunk
- line-accurate anchors for refreshes

**Likely files:**
- Possibly create: `src/agent_code_analyzer/semantic_chunking.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Add tests: `tests/test_semantic_chunking.py`

**Success criteria:**
- Small methods stay whole.
- Long methods split only where the AST says it makes sense.
- Every chunk can be traced back to its owning scope.

---

## Milestone 4: Full-project mass ingestion pipeline

**Status:** complete

**Objective:** Rebuild the entire semantic description layer in one pass when the project needs a clean refresh.

**Pattern:** **Template Method + Coordinator**

**Why this pattern fits:**
The ingestion flow has a stable order: scan scopes, build context, generate description, map to storage, persist. The template keeps the order fixed while helper steps remain swappable.

**Deliverables:**
- project-wide traversal
- semantic scope extraction from Tree-sitter and metadata
- description generation for every supported scope
- idempotent upserts into the vector layer

**Likely files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests: `tests/test_vector_index.py`
- Add tests: `tests/test_server_helpers.py`

**Success criteria:**
- A full rebuild produces the expected set of records.
- Re-running the rebuild does not duplicate records.
- The pipeline remains testable in isolation.

---

## Milestone 5: Incremental fswatch diff refresh pipeline

**Status:** complete

**Objective:** Refresh only the impacted semantic records when files change, instead of rebuilding the whole project.

**Pattern:** **Unit of Work + Command + Event Aggregator**

**Why this pattern fits:**
File changes arrive as noisy events; they should be aggregated into a unit of work, then converted into explicit commands such as add, modify, delete, or move.

**Deliverables:**
- short-lived batching window for filesystem events
- normalized update records per affected semantic scope
- explicit handling for add / modify / delete / move
- conservative fallback when scope mapping is ambiguous
- early integration coverage for leaf-only edits, refactors, and parent-meaning drift

**Likely files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Add tests: `tests/test_watcher.py`

**Success criteria:**
- Multiple rapid saves collapse into one batch.
- Deletes remove semantic records cleanly.
- Unchanged neighboring scopes are preserved.
- Move/refactor events remap lineage where possible.
- Leaf-only mutations keep unaffected semantic records stable.
- Refactors update every affected semantic description and retire stale locations.
- If a leaf change alters parent meaning, the parent chain is invalidated and regenerated.
- If a leaf change is cosmetic, parent semantic descriptions remain unchanged.

---

## Milestone 6: MCP surface for semantic refresh operations

**Status:** planned

**Objective:** Expose the full refresh workflow through the server so operators can trigger mass rebuilds and diff refreshes from the MCP surface.

**Pattern:** **Facade + Command**

**Why this pattern fits:**
The server should present a small, stable facade, while each operation maps to a clear command: rebuild, refresh changed files, or query semantic descriptions.

**Deliverables:**
- semantic rebuild command
- incremental refresh command
- backwards-compatible behavior for existing tools
- prompt guidance that explains when to use each mode

**Likely files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `docs/prompts/agent-code-analyzer-mcp-prompt.md`

**Success criteria:**
- Callers can initiate both refresh modes.
- The legacy retrieval paths remain available.

---

## Milestone 7: Retrieval and quality verification

**Status:** planned

**Objective:** Make the new descriptions searchable and prove that the summaries are useful for intent-level questions.

**Pattern:** **Specification + Strategy**

**Why this pattern fits:**
Retrieval needs explicit query rules, but ranking policy may change. A specification can filter the candidate set, and a strategy can score the survivors.

**Deliverables:**
- project-scoped semantic search over description text and metadata
- level-aware retrieval that differentiates architecture vs algorithmic behavior
- quality checks for package/module/file/class/method/chunk outputs

**Likely files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Add tests: `tests/test_vector_index.py`
- Add tests: `tests/test_server_helpers.py`

**Success criteria:**
- Architecture questions return high-level scope summaries.
- Algorithm questions return the more detailed scopes.
- The stub writer path remains accepted during early development.

---

## Milestone 8: Operator guidance and documentation

**Status:** planned

**Objective:** Document how the semantic layer works, how to use it, and how to verify it so the next maintainer does not have to reverse-engineer the branch.

**Pattern:** **Runbook / Playbook**

**Why this pattern fits:**
This section is operational rather than algorithmic. The important design choice is to keep the instructions ordered by lifecycle: what gets built, how it is refreshed, and how it is queried.

**Deliverables:**
- a clear explanation of semantic descriptions
- when to use mass ingestion vs diff refresh
- how Tree-sitter chunking affects scope boundaries
- how operators should interpret retrieval output

**Likely files:**
- Modify: `docs/prompts/agent-code-analyzer-mcp-prompt.md`
- Possibly create: `docs/decisions/semantic-algorithm-design.md`

**Success criteria:**
- The docs match the actual server behavior.
- The docs explain both user-facing use and implementation intent.

---

## Implementation order

1. Semantic record model and stable identities
2. Semantic writer abstraction
3. Tree-sitter chunking and scope partitioning
4. Full-project mass ingestion
5. Incremental fswatch diff refresh
6. MCP surface commands
7. Retrieval and quality verification
8. Operator guidance and documentation

## Definition of done

- Every supported scope can be described.
- The writer can be swapped without changing callers.
- Full rebuild and incremental refresh both work.
- Chunking remains stable and line-accurate.
- The semantic layer can be queried without breaking existing search paths.
