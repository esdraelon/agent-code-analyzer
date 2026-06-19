# Semantic Algorithm Retrieval and Code Architecture Description Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Add a semantic description pipeline that produces plain-language architecture and algorithm summaries for package, module, file, class, method, and chunk units, then stores those descriptions for vector search and incremental refresh.

**Architecture:**
Use Tree-sitter as the structural boundary detector, then generate plain-language descriptions at progressively smaller scopes. Package, module, and file descriptions should emphasize intent, structure, and ownership; class, method, and chunk descriptions should emphasize algorithmic behavior and control flow. The semantic layer should sit beside the existing lexical and chunk retrieval paths, not replace them.

The description generator must be isolated behind a narrow agent interface so the implementation can start with an abstract stub that returns a semaphore/no-response sentinel. That keeps the plumbing testable while the real agent is still being designed. The indexing pipeline needs two operating modes: a full mass-ingestion mode that rebuilds everything from scratch, and a piecewise mode that consumes filesystem diffs from `fswatch` so only changed regions are regenerated.

**Detailed implementation strategy:**
Use Tree-sitter as the context shaper for ingestion. Instead of sending whole files blindly, build annotated structural slices that include a source segment, the subtree it represents, and a compact lineage path. Target a context budget of roughly 50k tokens as an upper bound, not a fixed size; most calls should be smaller and centered on one meaningful Tree-sitter region. The agent should receive enough local structure to explain the code without needing the entire repository.

For each ingestion call, send:
- the source slice for the current subtree
- the annotated Tree-sitter outline for that subtree
- the file path, symbol path, and line range metadata
- parent/child lineage for nested scopes
- a short instruction prompt that explains the output contract

The agent should return plain-language description text only. It does not need to emit JSON. The internal MCP endpoint will accept the description together with structured metadata and store both the payload and the embedding input. That keeps the language model focused on semantic explanation while the server enforces schema, lineage, and storage rules.

The internal semantic-description endpoint should accept a structured record with fields such as project, scope type, scope identifier, file path, symbol path, line range, Tree-sitter/AST anchor, parent scope reference, and description text. The description text is what gets embedded. The metadata is what lets search return the file, class, method, and lines that correspond to a fuzzy query like "database read" without requiring a lexical match.

Package/module/file descriptions should emphasize architecture, intent, ownership, and dependencies. Class/method/chunk descriptions should emphasize behavior, control flow, and algorithmic detail. The pipeline should avoid repeating the same source in multiple prompts. Higher-level summaries should be derived from Tree-sitter structure, symbol signatures, imports, and child digests whenever possible. Lower-level summaries should receive the exact subtree and its local surroundings. If a subtree is too large, the chunker should split it further by AST boundaries and then by control-flow regions.

The agent interface should remain narrow and swappable. The first implementation can be an abstract stub that returns a semaphore/no-response sentinel, which keeps the plumbing testable before a real model-backed writer exists. The semantic writer contract must distinguish a deliberate no-response from a transport failure.

This design should support two operating modes:
- **Mass ingestion:** walk the whole project, generate descriptions for every semantic unit, and write the resulting records and embeddings in one rebuild pass.
- **Piecewise diff updates:** consume filesystem diffs from `fswatch`, identify the smallest affected semantic units, and regenerate only the impacted descriptions and embeddings.

Search should prioritize fuzzy semantic intent first and lexical matching second. A query like "database read" should resolve to relevant files, classes, methods, and line ranges through the embedding layer even when the exact words do not appear in source.
**Tech Stack:**
- Python 3.11+
- Tree-sitter parsing already present in the repo
- sqlite3 for metadata/source-of-truth storage
- qdrant-client for vector search storage
- filesystem watcher / fswatch integration
- pytest
- agent abstraction for semantic description generation

---

## Background

The current retrieval stack already has project-scoped lexical and semantic search plumbing, but it is oriented around source snippets and search ranking. This branch introduces a new layer: a plain-language semantic description model of the codebase that is generated by an agent and indexed as embeddings.

This is not the same as raw source chunking. The new layer should produce human-readable summaries that explain what the code does, then embed those summaries so retrieval can answer questions about architecture, algorithm intent, and structure at multiple levels.

The implementation must support two update styles:

1. **Mass ingestion**
   - walk the whole project
   - generate descriptions for every semantic unit
   - write the resulting records and embeddings in one rebuild pass

2. **Piecewise diff updates**
   - consume filesystem diffs from `fswatch`
   - batch them into contextual update records instead of firing one ingestion call per file event
   - identify the smallest affected semantic units
   - regenerate only impacted descriptions and embeddings
   - allow the agent to return either a no-op sentinel or updated plain-language text for each record

---

## Milestone 7: Semantic algorithm description indexing

**Status:** planned

**Objective:** Build a new semantic description pipeline that indexes plain-language summaries for package, module, file, class, method, and chunk scopes.

**Planned shape:**
- Keep Tree-sitter as the boundary detector for files, classes, methods, and complicated method regions.
- Generate descriptions from source structure rather than from raw text alone.
- Use an agent abstraction that can later be replaced by a real model-backed writer.
- Start with a stub implementation that returns a semaphore/no-response sentinel so the rest of the pipeline can be tested first.
- Store separate descriptions for different semantic levels so retrieval can target intent, structure, or algorithmic behavior as needed.
- Treat package/module/file descriptions as architecture and intent summaries.
- Treat class/method/chunk descriptions as algorithmic summaries focused on control flow, responsibilities, and behavior.
- Support a full rebuild path and an incremental diff-based refresh path.

**Likely files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `src/agent_code_analyzer/semantic_descriptions.py`
- Possibly create: `src/agent_code_analyzer/semantic_agent.py`
- Possibly create: `src/agent_code_analyzer/semantic_chunking.py`
- Modify: `src/agent_code_analyzer/watcher.py`
- Add tests under `tests/`
- Update docs/prompt material under `docs/prompts/`

**Success criteria:**
- The system can describe code at package, module, file, class, method, and chunk level.
- The description generator can be stubbed out and still let indexing flow complete.
- Mass ingestion can rebuild the entire semantic layer.
- Diff-based updates can refresh only the affected units from filesystem events.
- Tree-sitter chunking splits long or complicated methods into smaller semantic chunks.

---

### Task 1: Define the semantic description record model

**Objective:** Decide what fields every semantic description record must carry so the different levels can be indexed and refreshed consistently.

**Files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Possibly create: `src/agent_code_analyzer/semantic_descriptions.py`
- Possibly create: `docs/decisions/semantic-description-schema.md`

**Model requirements:**
- `project`
- `package`, `module`, `file`, `class`, `method`, or `chunk` level tag
- stable identity for the unit being described
- source file path
- symbol name when applicable
- start/end line range when applicable
- raw source fingerprint or content hash
- generated plain-language description text
- update mode metadata: `mass_ingestion` or `fswatch_diff`
- lineage back to the parent unit for nested scopes

**Verification:**
- The schema can represent every required level.
- The schema supports both rebuild and incremental refresh.
- The schema can preserve parent/child relationships between file, class, method, and chunk records.

---

### Task 2: Add the semantic writer abstraction with a stub implementation

**Objective:** Create a narrow agent interface for semantic description generation, then implement the first version as an abstract stub that returns a semaphore/no-response sentinel.

**Files:**
- Possibly create: `src/agent_code_analyzer/semantic_agent.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `tests/test_semantic_agent.py`

**Stub behavior:**
- accept a source unit and its metadata
- return a sentinel indicating “no generated response yet”
- keep the call shape stable so a real agent can be swapped in later
- allow callers to distinguish between a deliberate no-response stub and a transport failure

**Verification:**
- The stub can be called from the indexing path without crashing.
- The caller can detect the no-response sentinel.
- The pipeline remains testable with no model dependency.

---

### Task 3: Add Tree-sitter-aware chunking for long or complicated methods

**Objective:** Split method bodies into semantically useful chunks so the algorithmic description layer can focus on digestible units.

**Files:**
- Possibly create: `src/agent_code_analyzer/semantic_chunking.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Add tests under: `tests/test_semantic_chunking.py`

**Chunking rules:**
- prefer AST-aware boundaries over raw line counts
- split on logical control-flow regions when a method is long or complex
- preserve parent method identity for every chunk
- keep chunk spans line-accurate for later refreshes
- avoid producing trivial fragments that have no algorithmic value

**Verification:**
- A long method produces multiple chunk records.
- A small method remains a single chunk.
- Every chunk can be traced back to its parent method and file.

---

### Task 4: Implement mass ingestion for all semantic levels

**Objective:** Build a full-project refresh path that generates and stores descriptions for package, module, file, class, method, and chunk units.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add tests under: `tests/test_vector_index.py`
- Add tests under: `tests/test_server_helpers.py`

**Implementation notes:**
- traverse the project once
- derive the semantic unit list from Tree-sitter and project metadata
- call the semantic writer for each unit
- write the resulting descriptions and embeddings into the vector store
- keep the operation idempotent so a rebuild does not duplicate records

**Verification:**
- A full rebuild emits records for every supported level.
- Re-running mass ingestion does not create duplicate semantic records.
- The generated record counts are stable for the same input tree.

---

### Task 5: Implement piecewise updates from fswatch diffs

**Objective:** Refresh only impacted semantic records when files change, instead of rebuilding the entire project.

**Files:**
- Modify: `src/agent_code_analyzer/watcher.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/vector_index.py`
- Add tests under: `tests/test_watcher.py`

**Batching strategy:**
- collect file system events into a short-lived batch window instead of calling the agent once per event
- normalize multiple edits to the same file into one update record
- group related edits that share the same subtree, method, or class so the agent sees the smallest useful context bundle
- attach the diff hunk, source anchor, and current semantic lineage to each update record
- if a batch spans multiple unrelated files, split it into separate contextual records before calling the agent

**Update record shape:**
- project
- file path
- change type: `add`, `modify`, `delete`, or `move`
- old path and new path when applicable
- start/end line range for the diff or anchor region
- tree-sitter/AST anchor for the affected unit
- parent scope reference
- prior description text when available
- current source snippet or diff hunk

**Diff update behavior:**
- receive changed file paths and diff metadata from fswatch
- batch related file events into contextual update records before sending them to the semantic writer
- map changed lines back to the owning method/class/file/module/package scope
- invalidate old semantic records for the affected region
- regenerate only the changed semantic units and their dependent chunks
- let the writer return either a no-op sentinel or updated plain-language text for each record
- preserve unchanged neighboring units
- treat deletions as explicit removals of the affected semantic records
- treat moves and refactors as rename/move events where lineage and source anchors may need remapping rather than a full re-describe

**Special handling:**
- deletions should remove the semantic records for the deleted subtree and any dependent child records
- pure renames should prefer path/identity remapping when the source content is unchanged
- refactors that move code between files or classes may require rebuilding lineage even if the text is similar
- if an update record cannot be mapped confidently, fall back to a conservative re-describe of the smallest enclosing semantic unit

**Verification:**
- Editing one method only refreshes that method and its affected chunks.
- Editing a class-level boundary refreshes the owning class and the contained methods/chunks as needed.
- Unchanged files do not get rewritten during a diff update.
- Deletions remove the associated semantic records cleanly.
- Move/refactor events preserve identity where possible and remap anchors where necessary.
- Multiple rapid saves on the same file collapse into one batch update.

---

### Task 6: Expose semantic description indexing through the MCP surface

**Objective:** Add the operational hooks needed to trigger mass ingestion and diff-based refreshes from the server.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: `docs/prompts/agent-code-analyzer-mcp-prompt.md`
- Possibly modify: `docs/plans/2026-06-18-semantic-algorithm-plan.md` as the implementation evolves

**Expected server responsibilities:**
- trigger a full semantic rebuild
- trigger a piecewise refresh for changed files
- expose the semantic-description mode clearly to callers
- keep the old lexical and chunk retrieval paths intact

**Verification:**
- The MCP surface can initiate both ingestion modes.
- The server surface remains backwards-compatible for existing tools.

---

### Task 7: Add retrieval and quality checks for the semantic description layer

**Objective:** Make the new semantic descriptions searchable and prove that the level-specific summaries are useful.

**Files:**
- Modify: `src/agent_code_analyzer/vector_index.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Add tests under: `tests/test_vector_index.py`
- Add tests under: `tests/test_server_helpers.py`

**Verification targets:**
- package/module/file results emphasize architecture and intent
- class/method/chunk results emphasize algorithmic behavior
- the stub path is still accepted during early development
- the indexing and refresh paths work in both full and incremental modes

---

### Task 8: Update docs and operator guidance

**Objective:** Document how semantic descriptions are generated, refreshed, and queried so the next developer does not have to reconstruct the design from code.

**Files:**
- Modify: `docs/prompts/agent-code-analyzer-mcp-prompt.md`
- Possibly create: `docs/decisions/semantic-algorithm-design.md`
- Possibly create: `docs/complete/` entry later when the branch ships

**Documentation should explain:**
- what a semantic description is
- how the stub agent behaves
- when mass ingestion should be used
- when fswatch diff refresh should be used
- how Tree-sitter chunking affects method-level summaries
- how level-specific descriptions differ by scope

**Verification:**
- The docs describe both operating modes clearly.
- The docs match the actual server behavior.

---

## Implementation order

1. Record model
2. Stub agent abstraction
3. Tree-sitter chunking
4. Mass ingestion pipeline
5. fswatch diff updates
6. MCP hooks
7. Retrieval and tests
8. Documentation

---

## Notes on scope

- Keep the new semantic layer separate from the existing lexical search improvements.
- Do not replace source chunks with summaries; store both where useful.
- Treat the stub agent as a plumbing milestone, not as the final intelligence layer.
- Prefer line-accurate source anchoring wherever a semantic unit can be traced back to code.

## Definition of done

- Every requested scope level can be described.
- The description writer interface exists and can be stubbed.
- Full rebuild and incremental refresh both work.
- Tree-sitter chunking produces stable, useful chunks.
- The vector search layer can query the new descriptions without breaking existing search paths.

