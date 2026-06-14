from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .projects import (
    add_project as add_project_record,
    get_project,
    ingest_project_tree as ingest_project_index,
    list_projects as list_project_records,
    project_file_summary,
    resolve_project_path,
    search_projects as search_project_records,
)
from .watcher import ProjectWatcherService

mcp = FastMCP(
    name="agent-code-analyzer",
    instructions=(
        "Parse source files with Tree-sitter and return structural summaries. "
        "All code-analysis calls are project-scoped."
    ),
)


@dataclass(frozen=True)
class ToolResponseFactory:
    """Normalize the MCP tool fallback payloads in one place."""

    @staticmethod
    def parse_source_error(project: str, file_path: str, error: Exception) -> dict[str, object]:
        return {
            "project": project,
            "file_path": file_path,
            "supported": False,
            "language": "",
            "languages": [],
            "error": str(error),
        }

    @staticmethod
    def empty_symbol_list() -> str:
        return "[]"

    @staticmethod
    def empty_language() -> str:
        return ""


@dataclass(frozen=True)
class FileExcerptRenderer:
    """Render bounded file excerpts with normalized line numbers."""

    def render(self, path: Path, start_line: int = 1, end_line: int = 200) -> str:
        lines = path.read_text(encoding="utf-8").splitlines()
        if start_line < 1:
            start_line = 1
        if end_line < start_line:
            return ""
        start = start_line - 1
        end = min(end_line, len(lines))
        excerpt = lines[start:end]
        return "\n".join(f"{i}: {line}" for i, line in enumerate(excerpt, start=start_line))


TOOL_RESPONSES = ToolResponseFactory()
EXCERPT_RENDERER = FileExcerptRenderer()


@mcp.tool()
def add_project(
    project: str,
    root_path: str,
    mode: str = "file",
    description: str = "",
) -> dict[str, object]:
    """Register a project namespace and optionally ingest a directory tree."""
    return add_project_record(project, root_path=root_path, mode=mode, description=description)


@mcp.tool()
def list_projects() -> list[dict[str, object]]:
    """List all registered projects."""
    return list_project_records()


@mcp.tool()
def search_projects(query: str) -> list[dict[str, object]]:
    """Search registered projects by name, root path, mode, or description."""
    return search_project_records(query)


@mcp.tool()
def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, object]:
    """Recursively ingest a project's directory into a cached Tree-sitter index."""
    get_project(project)
    return ingest_project_index(project, refresh=refresh)


@mcp.tool()
def parse_source(project: str, file_path: str) -> dict[str, object]:
    """Parse a source file within a project and return basic tree metadata."""
    try:
        return project_file_summary(project, file_path)
    except ValueError as exc:
        return TOOL_RESPONSES.parse_source_error(project, file_path, exc)


@mcp.tool()
def generate_ast_skeleton(project: str, file_path: str) -> str:
    """Return a compact structural outline of a file inside a project."""
    try:
        return project_file_summary(project, file_path)["skeleton"]
    except ValueError:
        return ""


@mcp.tool()
def list_code_symbols(project: str, file_path: str) -> str:
    """Return a JSON string containing extracted structural symbols."""
    try:
        symbols = project_file_summary(project, file_path)["symbols"]
        return json.dumps(symbols, indent=2, ensure_ascii=False)
    except ValueError:
        return TOOL_RESPONSES.empty_symbol_list()


@mcp.tool()
def detect_source_language(project: str, file_path: str) -> str:
    """Return the Tree-sitter language name inferred from a file path."""
    try:
        return project_file_summary(project, file_path)["language"]
    except ValueError:
        return TOOL_RESPONSES.empty_language()


@mcp.tool()
def read_file_excerpt(
    project: str,
    file_path: str,
    start_line: int = 1,
    end_line: int = 200,
) -> str:
    """Read a bounded line range from a project file for debugging and review."""
    path = resolve_project_path(project, file_path)
    return EXCERPT_RENDERER.render(path, start_line=start_line, end_line=end_line)


def main() -> None:
    watcher = ProjectWatcherService().start()
    try:
        mcp.run(transport="stdio")
    finally:
        watcher.stop()


if __name__ == "__main__":
    main()
