# Lexical Search Architecture and Algorithmic Overview

> **Status:** draft for review

## Goal

Improve lexical ranking quality without changing the public MCP/API surface, while reducing the amount of work done per query where possible.

The current work keeps the existing search endpoints intact and focuses on the internal lexical path used by `search_code` and `lexical_search`.

## Architectural placement

The lexical path sits inside the existing agent-code-analyzer retrieval stack:

- `src/agent_code_analyzer/parsing.py` extracts symbols, skeletons, and source text.
- `src/agent_code_analyzer/lexical_repository.py` persists that analysis into sqlite as the source of truth.
- `src/agent_code_analyzer/lexical_index.py` performs lexical retrieval over the stored documents.
- `src/agent_code_analyzer/search_scoring.py` centralizes the ranking heuristics.
- `src/agent_code_analyzer/projects.py` exposes the lexical search path to the rest of the service and merges it with semantic search.
- `src/agent_code_analyzer/server.py` keeps the MCP surface stable.

This means the new work is a refinement of the existing retrieval pipeline, not a new external feature.

## What changed

### 1. Candidate pruning in sqlite

`LexicalRepository.fetch_candidate_documents()` adds a narrow prefilter over the `lexical_terms` table.

Instead of scanning every lexical document up front, the query now first asks:

- does the document contain at least one normalized query term?
- does it match the requested project and scope filters?

That gives the scorer a smaller candidate set for the common case where the query has at least one useful token.

### 2. Stronger ranking for exact lexical matches

`SearchScoringStrategy` and the lexical search helper now emphasize:

- exact token overlap
- exact phrase overlap
- symbol-name overlap
- path overlap

Generated/minified content is still penalized so it does not crowd out source files that are more likely to answer a query well.

### 3. No slow fallback

If candidate pruning produces no result, the search path now returns fewer or no lexical hits rather than falling back to a full scan.

That is intentional: for lexical analysis, predictable latency matters more than exhaustive recall. When the query is too broad or unusual, the agent should proceed with weaker lexical results or manual inspection rather than waiting on an expensive scan.

### 4. Timing instrumentation

The lexical search path now records timing for the main phases of the algorithm:

- candidate retrieval
- scoring
- fallback scan, when used
- sort / total search time

The instrumentation is internal and does not change the public return shape of the search API.

## Algorithmic flow

1. Normalize the query into token terms plus a lower-cased phrase string.
2. If the query is empty, return no results.
3. Fetch candidate documents through `lexical_terms` where possible.
4. Score each candidate with a weighted model:
   - exact terms contribute most
   - exact phrase matches add a large bonus
   - symbol/path matches add secondary bonuses
   - generated/minified content is discounted
5. If no document survives scoring, return the candidate-limited result set as-is.
6. Sort by score, then by symbol/file preference.

## Why this keeps the API surface unchanged

- The search endpoints still accept the same parameters.
- The returned search result structure is unchanged for callers.
- The new timing information is emitted as instrumentation, not as a contract change.

That makes the change safe for existing MCP clients while still giving us visibility into performance.

## Quality and performance tradeoff

The intended quality improvement is straightforward:

- exact identifier hits should rank above loose substring matches
- query phrases should be rewarded when they appear intact
- file and symbol hints should reinforce the ranking

- The common case should be cheaper because it scans fewer candidate rows.
- The worst case should remain bounded because there is no full lexical-scan fallback.

This favors latency over exhaustiveness, which is the right tradeoff for agent-side lexical analysis.

## Integration notes

- `projects.lexical_search()` continues to call the lexical helper and expose the result to the MCP layer.
- `projects.search_code()` still merges lexical and semantic results, so this work only changes how the lexical side is ranked.
- Tests should validate both the quality gain and the instrumentation visibility.

## Verification targets

- exact lexical hits outrank looser matches
- acronym and split-identifier queries still resolve correctly
- generated/minified content is discounted
- timing logs show candidate retrieval and scoring durations during lexical matching tests
