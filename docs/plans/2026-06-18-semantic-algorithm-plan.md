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

## Gap Analysis Overview

**Goal:** Every major part of a method, every method, class, module, file, and package should have a semantic description that captures both *what it does* and *why it exists*.

**Cross-reference target:** Each semantic record should be tied back to stable structural anchors so a query can resolve to:
- project and package context
- file path and line range
- symbol signature and symbol path
- AST node identity or subtree boundary
- Tree-sitter node / chunk boundary
- parent scope and child scope lineage

**Desired lookup flow:**
1. semantic query returns intent-level candidates first
2. candidates map to the relevant semantic scope records
3. each scope record resolves to source file, lines, symbol, and hierarchy metadata
4. the UI / API can expose the result as a cross-reference bundle rather than a single fuzzy hit

**Current state:**
- file-level semantic descriptions exist and are written during indexing
- method chunking exists for long/complex methods
- the semantic writer boundary exists, including a stub/no-response path
- the record model already accepts package, module, file, class, method, and chunk scope types
- the current ingestion path does *not yet* populate the full organizational tree from package down through chunks in a complete, consistent way

**Gap summary:**
- package and module summaries are not emitted as dedicated semantic records
- class-level semantic coverage is present only where symbol traversal reaches it; it is not yet an explicit tree-wide pass
- method-level descriptions exist, but the “major parts of a method” cross-reference layer needs clearer anchoring and retrieval behavior
- chunking is limited to method bodies, so the hierarchy is not yet uniform from package to chunk
- semantic results need a stronger contract for linking embeddings to source anchors, AST entries, and Tree-sitter nodes

**Planned outcome:**
- query semantic intent once, then fan out to the best matching file/class/method/chunk records
- preserve the structural breadcrumb trail needed to navigate back to source
- make the semantic layer usable for both architectural questions and algorithmic questions
- keep the retrieval output suitable for review, debugging, and code navigation

**Gap analysis workstreams:**
1. **Coverage audit** — verify which scope levels are actually emitted today, and which are only representable in the schema.
2. **Anchor audit** — verify which records carry stable file, line, symbol, AST, and Tree-sitter references.
3. **Hierarchy audit** — verify whether each child scope can point back to its parent scope without losing context.
4. **Query audit** — verify the shape of a semantic result when the lookup should return multiple cross-referenced locations instead of one hit.
5. **Refresh audit** — verify how full rebuild and incremental refresh differ in scope, and which levels are refreshed by each path.

## Gap Analysis Requirements

The following requirements are the normative output of the gap analysis. They define what the development plan must deliver.

### R1. Semantic scope coverage
- The system must generate dedicated semantic records for package, module, file, class, method, and chunk scopes.
- Package and module records must be distinct from file records.
- File records must remain available even when higher-level package or module records exist.
- Class records must be generated as first-class semantic records for class-like symbols.
- Method records must be generated as first-class semantic records for method and function symbols.
- Chunk records must be generated for major parts of long or complex methods.
- The system must distinguish a whole method from the chunks inside that method.

### R2. Stable semantic identity and anchors
- Every semantic record must have a stable scope identity that survives rebuilds for unchanged code.
- Every semantic record must store the source file path.
- Every semantic record that is line-bound must store start and end line numbers.
- Every symbol-based semantic record must store a signature or symbol path.
- Every semantic record must store an AST or Tree-sitter anchor, or an equivalent structural pointer.
- Every child scope must store a parent scope reference when one exists.
- Every semantic record must include a fingerprint or content hash for refresh and deduplication.

### R3. Semantic meaning by scope level
- Package and module descriptions must emphasize intent, ownership, and dependencies.
- File descriptions must explain the file’s role in the system.
- Class descriptions must explain responsibilities and state boundaries.
- Method descriptions must explain algorithmic behavior and control flow.
- Chunk descriptions must explain the major semantic parts of a method.
- All descriptions must be plain-language text suitable for semantic search and retrieval.

### R4. Cross-reference query behavior
- A single semantic query must be able to return multiple scope levels for the same code region.
- Results must be groupable by source file.
- Results must be groupable by symbol hierarchy.
- Results must expose the source line range for each match.
- Results must expose the structural path for each match.
- Results must support upward navigation from chunk to method to class to file to module to package.
- Results must support downward navigation from package to module to file to class to method to chunk.

### R5. Refresh and invalidation behavior
- A full rebuild must regenerate all supported semantic levels.
- An incremental refresh must regenerate only impacted scopes.
- Unrelated files and scopes must remain untouched during an incremental refresh.
- Parent scopes must be refreshed when child changes alter the parent’s meaning.
- Method chunking must be recomputed when a method changes shape or size.
- Each generated semantic record must record whether it came from mass ingestion or fswatch-driven refresh.

### R6. Verification requirements
- The implementation plan must include tests proving package, module, class, method, and chunk records can all be represented.
- The implementation plan must include tests proving semantic results preserve file, line, symbol, and parent-scope anchors.
- The implementation plan must include tests proving method chunking splits long methods into multiple semantic chunks.
- The implementation plan must include tests proving a semantic query can cross-reference multiple levels for one source region.
- The implementation plan must include tests proving full rebuild and incremental refresh behave differently.
- The implementation plan must include tests proving descriptions remain plain-language and search-oriented.

### R7. Development-plan implications
- The development plan must treat package/module emission as a separate work item, not an implied side effect of file indexing.
- The development plan must treat hierarchy and anchor preservation as first-class requirements, not implementation details.
- The development plan must treat cross-reference retrieval as a deliverable, not a UI-only concern.
- The development plan must treat refresh invalidation as part of the semantic contract.
- The development plan must include explicit acceptance criteria for each requirement above.

## Requirements-by-milestone breakdown

Use this map to translate the requirements above into implementation checkpoints without re-interpreting the scope.

- **Task 1 — Record model**: satisfies R1, R2, and the schema-related part of R6.
- **Task 2 — Stub writer abstraction**: satisfies R3 and the writer-boundary part of R6.
- **Task 3 — Tree-sitter chunking**: satisfies R1, R3, R4, and the chunking part of R6.
- **Task 4 — Mass ingestion**: satisfies R1, R2, R5, and the rebuild-related part of R6.
- **Task 5 — fswatch diff updates**: satisfies R2, R4, R5, and the incremental-refresh part of R6.
- **Task 6 — MCP surface hooks**: satisfies R5, R6, and the plan-implication part of R7.
- **Task 7 — Retrieval and quality checks**: satisfies R4 and the verification part of R6.
- **Task 8 — Docs and operator guidance**: satisfies R3, R6, and the explicit-documentation part of R7.

## Milestone checklist

Use this checklist as the implementation gate. A task is not complete until every box in its checklist is satisfied and verified.

### Task 1 — Record model
- [ ] The schema represents package, module, file, class, method, and chunk records.
- [ ] Each record has a stable identity suitable for idempotent upserts.
- [ ] Each record includes file path, symbol name when applicable, line anchors when applicable, content hash, description text, update mode, and lineage.
- [ ] Tests prove the schema can preserve parent/child relationships and support rebuild plus incremental refresh.

### Task 2 — Stub writer abstraction
- [ ] The writer accepts a source unit and metadata through a narrow interface.
- [ ] The stub returns a deliberate no-response sentinel consistently.
- [ ] The caller can distinguish no-response from transport failure.
- [ ] Tests prove the stub is callable from indexing without a model dependency.

### Task 3 — Tree-sitter chunking
- [ ] Chunk boundaries prefer AST structure over raw line counts.
- [ ] Long or complex methods split into meaningful chunks.
- [ ] Small methods stay whole.
- [ ] Each chunk preserves parent method identity and line-accurate anchors.
- [ ] Tests prove chunking produces useful, traceable units.

### Task 4 — Mass ingestion
- [ ] The pipeline walks the project root once per rebuild.
- [ ] The pipeline derives units from Tree-sitter structure and project metadata.
- [ ] Descriptions and embeddings are written for every supported semantic level.
- [ ] Re-running ingestion does not duplicate records.
- [ ] Tests prove counts and identities remain stable for unchanged input.

### Task 5 — fswatch diff updates
- [ ] File-system events are batched into a short-lived update window.
- [ ] Related edits are grouped into the smallest useful context bundle.
- [ ] Update records carry change type, paths, anchors, parent scope, and diff context.
- [ ] Affected records are invalidated before replacements are written.
- [ ] Deletions, moves, and refactors behave conservatively and preserve identity where possible.
- [ ] Tests prove one-file edits refresh only the affected scopes.

### Task 6 — MCP surface hooks
- [ ] The server exposes a full rebuild command.
- [ ] The server exposes a piecewise refresh command.
- [ ] The server makes semantic-description mode obvious to callers.
- [ ] Existing lexical and source-chunk paths remain intact.
- [ ] Prompt guidance explains when to use rebuild versus diff refresh.

### Task 7 — Retrieval and quality checks
- [ ] Semantic retrieval prefers intent before lexical matching.
- [ ] Architecture queries favor package/module/file descriptions.
- [ ] Behavior and algorithm queries favor class/method/chunk descriptions.
- [ ] Retrieval stays project-scoped.
- [ ] Tests prove both ingestion modes remain searchable and the stub path still works.

### Task 8 — Docs and operator guidance
- [ ] Docs define the semantic-description workflow clearly.
- [ ] Docs explain the stub agent, mass ingestion, and fswatch refresh modes.
- [ ] Docs explain how chunking changes method-level summaries.
- [ ] Docs match the shipped behavior.

---

## Milestone 7: Semantic algorithm description indexing

**Status:** planned

**Objective:** Build a new semantic description pipeline that indexes plain-language summaries for package, module, file, class, method, and chunk scopes, with explicit source anchors for semantic search and cross-reference.

**Planned shape:**
- Keep Tree-sitter as the boundary detector for files, classes, methods, and complicated method regions.
- Generate descriptions from source structure rather than from raw text alone.
- Use an agent abstraction that can later be replaced by a real model-backed writer.
- Start with a stub implementation that returns a semaphore/no-response sentinel so the rest of the pipeline can be tested first.
- Store separate descriptions for different semantic levels so retrieval can target intent, structure, or algorithmic behavior as needed.
- Treat package/module/file descriptions as architecture and intent summaries.
- Treat class/method/chunk descriptions as algorithmic summaries focused on control flow, responsibilities, and behavior.
- Attach each description to stable anchors: file path, line span, signature, symbol path, and AST / Tree-sitter lineage.
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

