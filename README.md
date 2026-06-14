# agent-code-analyzer

Tree-sitter-powered MCP server for project-scoped structural code analysis.

## Core model

This server now treats *projects* as the primary unit of work.

- register a project with a root directory
- every analysis call must include the project name
- optionally ingest a whole project tree recursively for fast project-level analysis

## MCP tools

Project management:

- `add_project`
- `list_projects`
- `search_projects`
- `ingest_project_tree`

Project-scoped analysis:

- `parse_source`
- `generate_ast_skeleton`
- `list_code_symbols`
- `detect_source_language`
- `read_file_excerpt`

## Usage

```bash
uv sync
uv run agent-code-analyzer
```

### Add a project

```text
add_project(project="demo", root_path="/path/to/repo", mode="directory")
```

### Analyze a file in a project

```text
parse_source(project="demo", file_path="src/main.py")
```

### Ingest a whole project recursively

Use `mode="directory"` when adding a project, or call:

```text
ingest_project_tree(project="demo", refresh=true)
```

That indexes all supported source files under the project root, recursively.

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
