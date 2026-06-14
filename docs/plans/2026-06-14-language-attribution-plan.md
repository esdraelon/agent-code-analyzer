# Language Attribution for Mixed-Language Tree-sitter Index Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Give each indexed scope a list of the languages it covers so mixed-language projects such as PHP+SQL or HTML+CSS+JavaScript can be represented accurately.

**Architecture:**
Keep sqlite as the source of truth, but extend the per-file/per-symbol records with explicit language coverage metadata. Language coverage should be derived from the parsed tree and any embedded-language nodes, then attached to each scoped entry in a deterministic way. The index should still be queryable by project and path, but the stored representation must support mixed-language scopes without losing the primary language of the file.

**Tech Stack:**
- Python 3.11+
- Tree-sitter bindings already in the repo
- sqlite3
- pytest

---

## Milestone 1: Model language coverage in the parsed payload

### Task 1: Define a language-coverage shape for file and symbol records

**Objective:** Add a stable data shape for language coverage that can be stored and serialized.

**Files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add/modify tests under `tests/`

**Planned shape:**
- Each file summary returns a `languages` list ordered by dominance or appearance.
- Each symbol or scoped entry returns its own `languages` list.
- Primary language remains available for compatibility.
- Coverage should be deduplicated and deterministic.

**Expected rules:**
- A pure PHP file may return `['php']`.
- A PHP file with embedded SQL should return `['php', 'sql']` at the file level.
- A nested HTML file with `<style>` and `<script>` blocks should expose `['html', 'css', 'javascript']` where appropriate.
- A scoped entry should list the languages that can reasonably apply to that scope, not every language in the repository.

### Task 2: Extend parsing to detect embedded language scopes

**Objective:** Collect language attribution from Tree-sitter structure instead of guessing from file extension alone.

**Planned shape:**
- Traverse relevant nodes for embedded language regions.
- Map embedded blocks to their language names.
- Attach language coverage to each symbol/scope record.
- Preserve current AST skeleton and symbol extraction behavior.

**Likely files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Add tests such as `tests/test_language_attribution.py`

**Success criteria:**
- The parser can explain mixed-language files without collapsing them into a single extension-based label.
- Output stays deterministic across repeated parses.

---

## Milestone 2: Persist coverage in sqlite

### Task 3: Add sqlite columns or normalized tables for language coverage

**Objective:** Store per-scope language coverage in a queryable way.

**Possible shapes:**
- a JSON column on files/symbols
- a normalized `languages` table with join tables
- a hybrid approach if it stays simple and performant

**Recommendation:**
Prefer the smallest schema that supports exact queries by project, path, and symbol scope while keeping migrations safe.

**Likely files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Add migration tests under `tests/`

**Success criteria:**
- Existing indexes continue to work.
- New language coverage data survives reindexing and incremental sync.
- Queries can retrieve language coverage without expensive recomputation.

### Task 4: Surface language coverage through the MCP tools

**Objective:** Make the new language metadata visible to agents.

**Files:**
- Modify: `src/agent_code_analyzer/server.py`
- Modify: any project query helpers that return summaries

**Success criteria:**
- File summary responses include languages.
- Symbol/scope responses include languages.
- The response format remains backward-compatible enough for existing callers.

---

## Milestone 3: Handle mixed-language examples and regressions

### Task 5: Add coverage tests for representative mixed-language files

**Objective:** Prove the implementation handles the target file types.

**Suggested fixtures:**
- PHP file with inline SQL strings or embedded SQL parsing behavior
- HTML with embedded CSS and JavaScript
- JavaScript file with template literals or embedded HTML patterns if supported by the parser

**Success criteria:**
- Tests assert the exact language coverage lists.
- False positives are avoided.
- Existing symbol and health tests keep passing.

---

## Success criteria

- Each scoped entry in the Tree-sitter DB has an explicit list of covered languages.
- Mixed-language files are represented without flattening them to a single language label.
- Coverage is deterministic, test-covered, and compatible with incremental indexing.
- The schema and MCP surface remain understandable to an agent reading the index.
