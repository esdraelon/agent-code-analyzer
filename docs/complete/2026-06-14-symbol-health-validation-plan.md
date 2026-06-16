# Symbol Health and Validation Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Add deterministic symbol-health validation so Tree-sitter parsing can distinguish "parsed successfully" from "structurally healthy" across projects.

**Architecture:**
Keep parsing and validation in `parsing.py`, but return a richer analysis payload that includes both raw symbol extraction and a structured health report. Store the report alongside file summaries so the MCP can surface warnings to agents without changing the sqlite source-of-truth model. Validation should stay deterministic, cheap, and based only on the parsed tree and symbol list.

**Tech Stack:**
- Python 3.11+
- Tree-sitter bindings already in the repo
- sqlite3
- pytest

---

## Milestone 1: Symbol health validation

### Task 1: Define symbol-health rules and payload shape

**Objective:** Establish a small, deterministic validation contract for file-level symbol health.

**Files:**
- Modify: `src/agent_code_analyzer/parsing.py`
- Modify: `src/agent_code_analyzer/projects.py`
- Modify: `src/agent_code_analyzer/server.py`
- Add/modify tests under `tests/`

**Validation rules:**
- mark files unhealthy when the parse tree has error nodes
- mark files unhealthy when a symbol name is missing
- mark files unhealthy when duplicate symbol names appear in the same file/scope
- mark files unhealthy when class/method nesting exceeds a configurable depth threshold
- keep the report deterministic and easy to serialize

**Payload shape:**
- `symbol_health`: `{ "healthy": bool, "issues": [str], "max_depth": int, "symbol_count": int }`
- preserve existing `parsed`, `skeleton`, and `symbols` keys
- include health data in `project_file_summary`

**Step 1: Write failing tests**
- assert that a file with duplicate symbols is reported unhealthy
- assert that an empty/missing symbol name is reported unhealthy
- assert that nested symbols beyond the threshold are reported unhealthy
- assert that healthy files report `healthy=True` with no issues

**Step 2: Run tests to verify failure**
- Run focused pytest targets for the new validation behavior
- Confirm the tests fail because the report does not yet exist

**Step 3: Write minimal implementation**
- add a small validator helper in `parsing.py`
- thread the new report through `analyze_file()` and `project_file_summary()`
- surface it through the MCP wrapper in `server.py`

**Step 4: Run tests to verify pass**
- Run the focused tests again
- Run the full suite

**Step 5: Commit**
- Commit the validation layer and tests together once green

### Task 2: Update project indexing to preserve health metadata

**Objective:** Make project summaries carry the health report without changing the sqlite ownership model.

**Files:**
- Modify: `src/agent_code_analyzer/projects.py`
- Add/modify tests under `tests/`

**Expected behavior:**
- `project_file_summary()` returns the health report alongside symbols and skeleton
- `parse_source()` returns the same health details via the server wrapper
- indexing remains deterministic and unaffected for healthy files

**Verification:**
- a healthy file indexes normally and reports healthy
- a bad file indexes normally but reports unhealthy with specific issues
- existing ingest/sync behavior still passes

---

## Success criteria

- Healthy files are distinguished from structurally suspicious files.
- Validation is deterministic and covered by tests.
- The MCP surface exposes the health information clearly enough to guide an agent.
- Existing indexing, ingest, and sync behavior remains intact.
