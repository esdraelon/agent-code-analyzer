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

### 2026-06-17 07:59 CDT

- **Date/time:** `2026-06-17 07:59 CDT`
- **Plan step:** `Repeatable ORK3 lexical snapshot capture`
- **Relevant commit:** `55b1bdaabb94e7df942496caa9a4a2eef499ed8b`
- **Relevant branch:** `fix/investigate-semantic`
- **Project:** `ORK3`
- **Query:** `mysql_real_escape_string`; `startup.php`; `common helper`
- **Tool call:** `uv run python scripts/ork3_eval_snapshot.py`
- **Baseline notes:** `This is the current snapshot in the time series; compare it to the previous entries for trend analysis.`
- **Candidate notes:** `Captured live retrieval results, timing logs, and top hits for the fixed ORK3 lexical benchmark set.`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass`
- **Follow-up needed:** `Repeat the same command after each lexical milestone so the trend line stays comparable.`

**Benchmark details**
- `mysql_real_escape_string`
  - elapsed_ms: `9727.345`
  - result_count: `5`
  - timing: `{'query': 'mysql_real_escape_string', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 1055, 'matched': 1055, 'candidate_ms': 592.214, 'scoring_ms': 861.235, 'sort_ms': 0.926, 'total_ms': 1454.627}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2667/symbols/0', 'symbol_name': 'Controller_Admin', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.9000000000000004, 'file_path': 'orkui/controller/controller.Admin.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2678/symbols/0', 'symbol_name': 'Controller_KingdomAjax', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.4000000000000004, 'file_path': 'orkui/controller/controller.KingdomAjax.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2681/symbols/0', 'symbol_name': 'Controller_Park', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.233333333333334, 'file_path': 'orkui/controller/controller.Park.php'}]`
- `startup.php`
  - elapsed_ms: `232.096`
  - result_count: `5`
  - timing: `{'query': 'startup.php', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 666, 'matched': 666, 'candidate_ms': 85.119, 'scoring_ms': 94.934, 'sort_ms': 0.723, 'total_ms': 180.846}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2695/symbols/0', 'symbol_name': 'required_parameter_count', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.9000000000000004, 'file_path': 'orkui/index.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2680/symbols/1', 'symbol_name': '__construct', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.42775176, 'file_path': 'orkui/controller/controller.Login.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2583/symbols/2', 'symbol_name': 'AddAuthorization', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.25, 'file_path': 'orkservice/Authorization/AuthorizationService.function.php'}]`
- `common helper`
  - elapsed_ms: `330.731`
  - result_count: `5`
  - timing: `{'query': 'common helper', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 339, 'matched': 339, 'candidate_ms': 118.33, 'scoring_ms': 112.983, 'sort_ms': 0.475, 'total_ms': 231.857}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/8', 'symbol_name': 'Datepicker', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.1, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/17', 'symbol_name': '_normalizeArguments', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.5999999999999999, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2901/symbols/25', 'symbol_name': 'addToPrefiltersOrTransports', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.4333333333333333, 'file_path': 'orkui/template/default/script/development-bundle/jquery-1.7.1.js'}]`

### 2026-06-17 06:12 CDT

- **Date/time:** `2026-06-17 06:12 CDT`
- **Plan step:** `Repeatable ORK3 lexical snapshot capture`
- **Relevant commit:** `55b1bdaabb94e7df942496caa9a4a2eef499ed8b`
- **Relevant branch:** `main`
- **Project:** `ORK3`
- **Query:** `mysql_real_escape_string`; `startup.php`; `common helper`
- **Tool call:** `uv run python scripts/ork3_eval_snapshot.py`
- **Baseline notes:** `This is the current snapshot in the time series; compare it to the previous entries for trend analysis.`
- **Candidate notes:** `Captured live retrieval results, timing logs, and top hits for the fixed ORK3 lexical benchmark set.`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass`
- **Follow-up needed:** `Repeat the same command after each lexical milestone so the trend line stays comparable.`

**Benchmark details**
- `mysql_real_escape_string`
  - elapsed_ms: `10075.608`
  - result_count: `5`
  - timing: `{'query': 'mysql_real_escape_string', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 1055, 'matched': 1055, 'candidate_ms': 580.304, 'scoring_ms': 842.185, 'sort_ms': 0.918, 'total_ms': 1423.67}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2667/symbols/0', 'symbol_name': 'Controller_Admin', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.9000000000000004, 'file_path': 'orkui/controller/controller.Admin.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2678/symbols/0', 'symbol_name': 'Controller_KingdomAjax', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.4000000000000004, 'file_path': 'orkui/controller/controller.KingdomAjax.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2681/symbols/0', 'symbol_name': 'Controller_Park', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.233333333333334, 'file_path': 'orkui/controller/controller.Park.php'}]`
- `startup.php`
  - elapsed_ms: `247.247`
  - result_count: `5`
  - timing: `{'query': 'startup.php', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 666, 'matched': 666, 'candidate_ms': 92.577, 'scoring_ms': 100.325, 'sort_ms': 0.803, 'total_ms': 193.786}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2695/symbols/0', 'symbol_name': 'required_parameter_count', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.9000000000000004, 'file_path': 'orkui/index.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2583/symbols/2', 'symbol_name': 'AddAuthorization', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.25, 'file_path': 'orkservice/Authorization/AuthorizationService.function.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2573/symbols/32', 'symbol_name': 'AddCacheLine', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.0833333333333333, 'file_path': 'import/import.primary.php'}]`
- `common helper`
  - elapsed_ms: `292.819`
  - result_count: `5`
  - timing: `{'query': 'common helper', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 339, 'matched': 339, 'candidate_ms': 116.505, 'scoring_ms': 115.428, 'sort_ms': 0.349, 'total_ms': 232.374}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/8', 'symbol_name': 'Datepicker', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.1, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/17', 'symbol_name': '_normalizeArguments', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.5999999999999999, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2901/symbols/25', 'symbol_name': 'addToPrefiltersOrTransports', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.4333333333333333, 'file_path': 'orkui/template/default/script/development-bundle/jquery-1.7.1.js'}]`

### 2026-06-16 13:53 CDT

- **Date/time:** `2026-06-16 13:53 CDT`
- **Plan step:** `Repeatable ORK3 lexical snapshot capture`
- **Relevant commit:** `06dfd94c335a873f9942b9cbc4eae881adadf22d`
- **Relevant branch:** `main`
- **Project:** `ORK3`
- **Query:** `mysql_real_escape_string`; `startup.php`; `common helper`
- **Tool call:** `uv run python scripts/ork3_eval_snapshot.py`
- **Baseline notes:** `This is the current snapshot in the time series; compare it to the previous entries for trend analysis.`
- **Candidate notes:** `Captured live retrieval results, timing logs, and top hits for the fixed ORK3 lexical benchmark set.`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Usefulness score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass`
- **Follow-up needed:** `Repeat the same command after each lexical milestone so the trend line stays comparable.`

**Benchmark details**
- `mysql_real_escape_string`
  - elapsed_ms: `9997.858`
  - result_count: `5`
  - timing: `{'query': 'mysql_real_escape_string', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 1055, 'matched': 1055, 'candidate_ms': 593.604, 'scoring_ms': 855.147, 'sort_ms': 0.974, 'total_ms': 1449.869}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2667/symbols/0', 'symbol_name': 'Controller_Admin', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.9000000000000004, 'file_path': 'orkui/controller/controller.Admin.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2678/symbols/0', 'symbol_name': 'Controller_KingdomAjax', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.4000000000000004, 'file_path': 'orkui/controller/controller.KingdomAjax.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2681/symbols/0', 'symbol_name': 'Controller_Park', 'scope_type': 'symbol', 'unit_type': 'class', 'score': 2.233333333333334, 'file_path': 'orkui/controller/controller.Park.php'}]`
- `startup.php`
  - elapsed_ms: `253.159`
  - result_count: `5`
  - timing: `{'query': 'startup.php', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 666, 'matched': 666, 'candidate_ms': 86.17, 'scoring_ms': 94.675, 'sort_ms': 0.786, 'total_ms': 181.714}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2695/symbols/0', 'symbol_name': 'required_parameter_count', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.9000000000000004, 'file_path': 'orkui/index.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2583/symbols/2', 'symbol_name': 'AddAuthorization', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.25, 'file_path': 'orkservice/Authorization/AuthorizationService.function.php'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2573/symbols/32', 'symbol_name': 'AddCacheLine', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.0833333333333333, 'file_path': 'import/import.primary.php'}]`
- `common helper`
  - elapsed_ms: `276.872`
  - result_count: `5`
  - timing: `{'query': 'common helper', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 339, 'matched': 339, 'candidate_ms': 118.306, 'scoring_ms': 113.569, 'sort_ms': 0.386, 'total_ms': 232.335}`
  - top_hits: `[{'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/8', 'symbol_name': 'Datepicker', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 2.1, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2999/symbols/17', 'symbol_name': '_normalizeArguments', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.5999999999999999, 'file_path': 'orkui/template/default/script/development-bundle/ui/jquery-ui-1.8.18.custom.js'}, {'sqlite_uri': 'sqlite://projects/ORK3/files/2901/symbols/25', 'symbol_name': 'addToPrefiltersOrTransports', 'scope_type': 'symbol', 'unit_type': 'method', 'score': 1.4333333333333333, 'file_path': 'orkui/template/default/script/development-bundle/jquery-1.7.1.js'}]`

### 2026-06-16 13:52 CDT

- **Project:** `ORK3`
- **Branch:** `main`
- **Commit:** `06dfd94c335a873f9942b9cbc4eae881adadf22d`
- **Dirty:** `True`
- **Scope type:** `symbol`
- **Limit:** `5`
- **Queries:**
  - `mysql_real_escape_string`
    - elapsed_ms: `10233.307`
    - result_count: `5`
    - timing: `{'query': 'mysql_real_escape_string', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 1055, 'matched': 1055, 'candidate_ms': 653.659, 'scoring_ms': 874.989, 'sort_ms': 0.962, 'total_ms': 1529.763}`
  - `startup.php`
    - elapsed_ms: `255.342`
    - result_count: `5`
    - timing: `{'query': 'startup.php', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 666, 'matched': 666, 'candidate_ms': 88.266, 'scoring_ms': 100.243, 'sort_ms': 0.714, 'total_ms': 189.342}`
  - `common helper`
    - elapsed_ms: `289.257`
    - result_count: `5`
    - timing: `{'query': 'common helper', 'project': 'ORK3', 'scope_type': 'symbol', 'candidates': 339, 'matched': 339, 'candidate_ms': 114.943, 'scoring_ms': 111.713, 'sort_ms': 0.388, 'total_ms': 227.141}`

### 2026-06-16

- **Date/time:** `2026-06-16 13:43 CDT`
- **Plan step:** `Verify live ORK3 lexical integration logging after timing instrumentation`
- **Relevant commit:** `working tree`
- **Relevant branch:** `main`
- **Project:** `ORK3`
- **Query:** `mysql_real_escape_string`; `common helper`
- **Tool call:** `uv run python -c '... projects.search_code(...) ...'`
- **Baseline notes:** `Captured live lexical timing output from the integrated search path against ORK3 while running two benchmark queries.`
- **Candidate notes:** `Two INFO log lines were captured by the temporary logging handler, one per query, including candidate_ms, scoring_ms, sort_ms, and total_ms. The ORK3 results were also returned normally, confirming the logging path did not break retrieval.`
- **Usefulness score:** `2`
- **Scope score:** `2`
- **Anchoring score:** `2`
- **Compactness score:** `2`
- **Decision:** `pass`
- **Follow-up needed:** `Repeat the same benchmark after later lexical-ranking changes to compare timing deltas over time.`

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
