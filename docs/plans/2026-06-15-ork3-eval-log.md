# Code Analyzer Integration Evaluation Log

Use this file to track benchmark responses during development of the agent-code-analyzer retrieval and intent changes.

## Entry format

- **Date/time:** `YYYY-MM-DD HH:MM America/Chicago`
- **Plan step:** `Task N / milestone / feature slice`
- **Relevant commit:** `git commit SHA` or `working tree`
- **Relevant branch:** `git branch --show-current`
- **Query:** `...`
- **Tool call:** `...`
- **Baseline notes:** `...`
- **Candidate notes:** `...`
- **Scope score:** `0-2`
- **Anchoring score:** `0-2`
- **Usefulness score:** `0-2`
- **Compactness score:** `0-2`
- **Decision:** `pass / fail / needs follow-up`
- **Follow-up needed:** `...`

## Current benchmark set

- Structural lookup: where a symbol or behavior is defined
- Ownership boundary: which file/module owns the behavior
- Refactor seam: what should be extracted first
- Intent summary: what a component is for
- Response shape: whether the default answer stays compact and expandable

## Operational note

- Cold start can be a recurring issue during development runs and should be treated primarily as a development concern, not a production concern.
- Always include proof-of-life preflight checks before judging retrieval or integration behavior.

## Log

### 2026-06-15

- **Date/time:** `2026-06-15 19:51 CDT`
- **Plan step:** `Hybrid ranking + Tree-sitter isolation update on current dev branch`
- **Relevant commit:** `working tree @ 6bab01c`
- **Relevant branch:** `feat/hybrid-ranking-tuning`
- **Query:** `mysql_real_escape_string`; `startup.php`; `common helper`
- **Tool call:** `uv run pytest -q`; `uv run python ... search_code`; `mcp_agent_code_analyzer_semantic_search(...)`
- **Baseline notes:** `Live MCP semantic_search was still noisy on the same queries: broad minified-symbol hits and weak anchoring remained visible in the top 5 for mysql_real_escape_string/setup guard and common helper barrel DB LOG.`
- **Candidate notes:** `Current working-tree search_code is materially better: mysql_real_escape_string now ranks Controller_Admin / Controller_KingdomAjax / Controller_Park ahead of unrelated minified blobs, startup.php now resolves to orkui/index.php and related entrypoints, and common helper stays on jquery-ui / ajax support code rather than stray fullcalendar internals.`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass with follow-up`
- **Follow-up needed:** `Reload the live MCP server against this branch and re-run the same queries to confirm the improved ranking is reflected outside the local terminal run.`

- **Date/time:** `2026-06-15 10:57 CDT`
- **Plan step:** `Milestone 6 / Task 7 preflight baseline`
- **Relevant commit:** `9f1e6e9`
- **Relevant branch:** `docs/preflight-baseline`
- **Query:** `Establish a preflight structural snapshot for startup.php and system/lib/ork3/common.php before the first comparison.`
- **Tool call:** `parse_source(startup.php); list_code_symbols(system/lib/ork3/common.php); read_file_excerpt(startup.php:1-20); read_file_excerpt(system/lib/ork3/common.php:96-118)`
- **Baseline notes:** `startup.php currently exposes only mysql_real_escape_string() and the system setup guard; system/lib/ork3/common.php opens with global DB/LOG wiring, Yapo table handles, and a large Common helper barrel. This is a useful known baseline for later boundary comparisons.`
- **Candidate notes:** `N/A — baseline only`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass`
- **Follow-up needed:** `Rerun the same structural snapshot after the next candidate change, and retry semantic_search once the analyzer wrapper is healthy enough to produce retrieval results.`
