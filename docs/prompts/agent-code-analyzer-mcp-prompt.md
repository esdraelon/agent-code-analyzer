# agent-code-analyzer MCP prompt

Use this server as the first choice for code-based questions and actions.

## What this server is for

- structural code understanding with Tree-sitter
- AST skeletons and file summaries
- symbol, definition, and reference navigation
- project-scoped file inspection
- file- and symbol-based exclusion filtering during retrieval
- refactor planning and ownership boundaries
- line-accurate verification after source changes
- semantic descriptions that sit alongside source-derived metadata and preserve scope-level summaries

## How to use it

When the user asks about source code, prefer the MCP tools before guessing from raw text.

Recommended tool order:
1. `list_projects` or `search_projects` to confirm the project scope
2. `detect_source_language` when the language is unclear
3. `parse_source` for a structured file summary
4. `generate_ast_skeleton` for a declaration-only outline
5. `list_code_symbols` for symbol extraction
6. `read_file_excerpt` for line-anchored confirmation
7. `semantic_search` when the question is about broader code similarity or related chunks

Semantic-description maintenance tools:
- `semantic_rebuild` for a full rebuild of the semantic-description layer
- `semantic_refresh` for an incremental refresh from fswatch-style diffs

Semantic-description rules:
- treat semantic descriptions as summaries layered on top of source chunks, not replacements for them
- use `semantic_rebuild` after onboarding, repairs, or large refactors that can invalidate many scopes
- use `semantic_refresh` for local, incremental edits that only affect a small changed set
- keep the mode explicit: say full rebuild or incremental refresh instead of relying on generic ingest/sync wording

Backend split:
- `FakeAgent` is the deterministic baseline used for repeatable tests and retrieval snapshots
- the stub writer returns the deliberate no-response sentinel so plumbing can be verified without a live backend
- the real backend is for live semantic generation and retrieval once the plumbing is proven

If the user already knows which files or symbols should be ignored, pass `exclude_files` and/or `exclude_symbols` to `lexical_search`, `semantic_search`, or `search_code` instead of post-filtering the results manually.

## Prompting guidance

- Treat code questions as structural questions first.
- Cite file paths, symbols, and line ranges when available.
- Use the project name on every analysis call.
- Use `semantic_rebuild` when the project needs a complete semantic-description pass; use `semantic_refresh` when only changed files should be refreshed.
- Prefer code navigation tools over prose explanations when the user is asking where logic lives, how a file is shaped, or what should change.
- Use exclusion filters when a result set needs to omit known noisy files or symbols.
- After a pull, rebase, or refactor, refresh line numbers from source before updating plans or recommendations.
- For retrieval, exact search, or intent-summary changes, run the ORK3 integration-eval skill regularly during development, not just at the end.
- Annotate each ORK3 run with date/time, plan step, relevant commit, and relevant branch.
- Use `docs/plans/2026-06-15-ork3-eval-log.md` to keep the run history together with the plan.
- Compare usefulness, scope, anchoring, and compactness.
- Keep the compact response path as the default; expand only the relevant hit or detail when the user asks for it.

## Expected behaviors

The assistant should use this MCP for:

- “Where is this defined?”
- “What references this symbol?”
- “Which file owns this logic?”
- “What changed after the pull?”
- “What line numbers should the plan use?”
- “Which project-scoped files need to be edited?”

If the request is about source structure, code ownership, or refactor impact, the model should treat this server as the authoritative toolset instead of relying on filename guesses or memory.
