---
name: agent-code-analyzer-mcp-skill
description: Use the agent-code-analyzer MCP for Tree-sitter-backed code questions, structural analysis, and line-accurate refactor planning.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [mcp, tree-sitter, code-analysis, refactor, prompt]
---

# agent-code-analyzer MCP skill

Use this skill when the user’s request is about code structure, ownership, or code changes that should be grounded in real source rather than guesses.

## When to use

- answering “where is this defined?”
- finding references, symbols, or call sites
- mapping controller/model/service/template ownership
- refreshing line numbers after a pull, rebase, or refactor
- planning code changes that need source-level evidence

## Best practice

1. Start with the project scope.
2. Prefer Tree-sitter-backed tools before raw file reading.
3. Use `parse_source`, `generate_ast_skeleton`, `list_code_symbols`, `detect_source_language`, and `read_file_excerpt` to gather evidence.
4. Cite file paths and line numbers in the final answer when possible.
5. Re-check the source before updating plans, because line numbers drift after upstream changes.

## Tooling mindset

This MCP is strongest when the task is code-first:

- project-scoped inspection
- structural summaries
- symbol extraction
- definition/reference lookup
- refactor boundary analysis
- verification after a pull or merge

For broad similarity or code-discovery work, use semantic search only after the structural tools have narrowed the field.

## Good response shape

A strong answer from this workflow should usually include:

- the relevant project name
- the files that matter
- the important symbols or methods
- exact line ranges when known
- a short recommendation for the next code action

## Pitfalls

- Don’t answer code-structure questions from memory alone.
- Don’t use filename similarity as a substitute for AST/symbol evidence.
- Don’t update a plan’s line numbers without re-reading the file after a pull or rebase.
- Don’t treat unscoped analysis as authoritative when the server expects a project name.
