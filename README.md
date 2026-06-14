# agent-code-analyzer

Tree-sitter-powered MCP server for structural code analysis.

## What it does

- detects a supported language from file extension
- parses a source file into a syntax tree
- returns a declaration-only AST skeleton
- lists structural symbols with spans and signatures
- reads a bounded excerpt for quick inspection

## Installed MCP tools

- `parse_source`
- `generate_ast_skeleton`
- `list_code_symbols`
- `detect_source_language`
- `read_file_excerpt`

## Local usage

Install dependencies and run the server:

```bash
uv sync
uv run agent-code-analyzer
```

Or run the sample parser against a file:

```bash
uv run python scripts/run_sample.py path/to/file.py
```

## Supported languages

The initial mapping covers common extensions such as:

- Python
- JavaScript / TypeScript
- Java
- Go
- Rust
- PHP
- Ruby
- C / C++ / C#
- Bash
- YAML

Unsupported extensions return a documented fallback instead of failing noisily.
