from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .parsing import ast_skeleton, detect_language, list_symbols, parse_file

mcp = FastMCP(
    name="agent-code-analyzer",
    instructions="Parse source files with Tree-sitter and return structural summaries.",
)


@mcp.tool()
def parse_source(file_path: str) -> dict[str, object]:
    """Parse a source file and return basic metadata about the syntax tree."""
    try:
        parsed = parse_file(file_path)
    except ValueError as exc:
        return {
            "file_path": file_path,
            "supported": False,
            "language": "",
            "error": str(exc),
        }

    root = parsed.tree.root_node
    return {
        "file_path": parsed.file_path,
        "supported": True,
        "language": parsed.language,
        "root_type": root.type,
        "node_count": root.descendant_count,
        "has_error": root.has_error,
        "byte_length": len(parsed.source_code.encode("utf-8")),
    }


@mcp.tool()
def generate_ast_skeleton(file_path: str) -> str:
    """Return a compact structural outline of top-level declarations in a file."""
    try:
        return ast_skeleton(file_path)
    except ValueError:
        return ""


@mcp.tool()
def list_code_symbols(file_path: str) -> str:
    """Return a JSON string containing extracted structural symbols."""
    try:
        return json.dumps(list_symbols(file_path), indent=2, ensure_ascii=False)
    except ValueError:
        return "[]"


@mcp.tool()
def detect_source_language(file_path: str) -> str:
    """Return the Tree-sitter language name inferred from a file path."""
    return detect_language(file_path)


@mcp.tool()
def read_file_excerpt(file_path: str, start_line: int = 1, end_line: int = 200) -> str:
    """Read a bounded line range from a file for debugging and review."""
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if start_line < 1:
        start_line = 1
    if end_line < start_line:
        return ""
    start = start_line - 1
    end = min(end_line, len(lines))
    excerpt = lines[start:end]
    return "\n".join(f"{i}: {line}" for i, line in enumerate(excerpt, start=start_line))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
