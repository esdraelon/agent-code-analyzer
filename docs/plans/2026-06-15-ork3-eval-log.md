# ORK3 Integration Evaluation Log

Use this file to track ORK3 benchmark responses during development of the agent-code-analyzer retrieval and intent changes.

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

- **Date/time:** `2026-06-15 11:07 CDT`
- **Plan step:** `First ORK3 integ comparison / vector round-trip smoke`
- **Relevant commit:** `9f1e6e9`
- **Relevant branch:** `feat/vector-round-trip-test`
- **Query:** `startup.php mysql_real_escape_string setup guard`; `common helper barrel DB LOG`; `weather forecast for date`; `audit second change`
- **Tool call:** `uv run pytest -q tests/test_vector_index.py tests/test_server_helpers.py`; `mcp_agent_code_analyzer_semantic_search(..., project="ORK3")`
- **Baseline notes:** `Baseline log on docs/ork3-preflight-baseline was structural only: startup.php and system/lib/ork3/common.php were captured as a known starting snapshot before the first comparison.`
- **Candidate notes:** `Vector payload round-trip is working: search results now carry normalized unit_type plus sqlite_uri/sqlite_file_uri/sqlite_project_uri and preserve file/symbol scope metadata. The focused ORK3 queries returned usable anchors, but broad semantic queries were still noisy, so retrieval tuning may still be worth a follow-up pass.`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `1`
- **Compactness score:** `2`
- **Decision:** `pass with follow-up`
- **Follow-up needed:** `Consider improving semantic ranking/query phrasing for broader ORK3 intent queries if we want fewer off-target hits.`
