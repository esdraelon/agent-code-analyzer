from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .projects import (
    add_project as add_project_record,
    get_project,
    ingest_project_tree as ingest_project_index,
    lexical_search as lexical_search_records,
    list_projects as list_project_records,
    project_file_summary,
    resolve_project_path,
    search_code as search_code_records,
    search_projects as search_project_records,
    sync_project_tree as sync_project_index,
)
from .ingestion_state import recover_incomplete_ingestion
from .watcher import ProjectWatcherService
from .vector_index import bootstrap_existing_projects, get_vector_index
from .logging_config import setup_logging

SERVER_INSTRUCTIONS = (
    "Tree-sitter-backed MCP for code-first analysis, symbol navigation, and line-accurate verification. "
    "Use this server whenever the user asks about source structure, definitions, references, ownership boundaries, or refactor impact. "
    "Any time the user asks you to consider the content of a code base, first check whether that code base is already ingested in agent-code-analyzer. "
    "If it is ingested, use this server's tools to investigate it. If it is not ingested, ask whether it should be onboarded to agent-code-analyzer before proceeding. "
    "Prefer project-scoped tools such as parse_source, generate_ast_skeleton, list_code_symbols, detect_source_language, read_file_excerpt, lexical_search, and search_code before guessing from raw text. "
    "Use semantic_rebuild for a full semantic-description rebuild and semantic_refresh for an incremental fswatch diff refresh. "
    "When the caller needs a semantic-description operation, make the mode explicit instead of relying on the generic ingest and sync tool names. "
    "When the user wants to ignore known-noisy code, use the exclusion filters on lexical_search, semantic_search, and search_code to omit file paths and symbol names rather than manually filtering results after the fact. "
    "When the question is about code, inspect the project first and answer with file paths, symbols, and line ranges when available. "
    "All analysis calls are project-scoped."
)

mcp = FastMCP(
    name="agent-code-analyzer",
    instructions=SERVER_INSTRUCTIONS,
)

LOGGER = logging.getLogger(__name__)


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


def _semantic_operation_response(operation: str, semantic_mode: str, summary: dict[str, object]) -> dict[str, object]:
    response = dict(summary)
    response.update(
        {
            "operation": operation,
            "semantic_mode": semantic_mode,
        }
    )
    return response


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
def semantic_search(
    query: str,
    project: str | None = None,
    scope_type: str | None = None,
    limit: int = 10,
    offset: int = 0,
    exclude_files: list[str] | None = None,
    exclude_symbols: list[str] | None = None,
) -> dict[str, object]:
    """Search the Qdrant-backed project index for semantically similar code chunks."""
    return get_vector_index().search(
        query,
        project=project,
        scope_type=scope_type,
        limit=limit,
        offset=offset,
        exclude_files=exclude_files,
        exclude_symbols=exclude_symbols,
    )


@mcp.tool()
def lexical_search(
    query: str,
    project: str | None = None,
    scope_type: str | None = None,
    limit: int = 10,
    offset: int = 0,
    directory: str | None = None,
    exclude_files: list[str] | None = None,
    exclude_symbols: list[str] | None = None,
) -> dict[str, object]:
    """Search the local lexical index for exact tokens, file paths, and identifiers."""
    return lexical_search_records(
        query,
        project=project,
        scope_type=scope_type,
        limit=limit,
        offset=offset,
        directory=directory,
        exclude_files=exclude_files,
        exclude_symbols=exclude_symbols,
    )


@mcp.tool()
def search_code(
    query: str,
    project: str | None = None,
    scope_type: str | None = None,
    limit: int = 10,
    offset: int = 0,
    directory: str | None = None,
    exclude_files: list[str] | None = None,
    exclude_symbols: list[str] | None = None,
) -> dict[str, object]:
    """Search code using both lexical and semantic retrieval, then merge the results."""
    return search_code_records(
        query,
        project=project,
        scope_type=scope_type,
        limit=limit,
        offset=offset,
        directory=directory,
        exclude_files=exclude_files,
        exclude_symbols=exclude_symbols,
    )


@mcp.tool()
def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, object]:
    """Recursively ingest a project's directory into a cached Tree-sitter index."""
    get_project(project)
    return ingest_project_index(project, refresh=refresh)


@mcp.tool()
def semantic_rebuild(project: str) -> dict[str, object]:
    """Trigger a full semantic-description rebuild using mass ingestion."""
    get_project(project)
    summary = ingest_project_index(project, refresh=True)
    return _semantic_operation_response("semantic_rebuild", "mass_ingestion", summary)


@mcp.tool()
def semantic_refresh(project: str) -> dict[str, object]:
    """Trigger an incremental semantic-description refresh using fswatch diffs."""
    get_project(project)
    summary = sync_project_index(project)
    return _semantic_operation_response("semantic_refresh", "fswatch_diff", summary)


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
    setup_logging()
    watcher = ProjectWatcherService().start()

    def _bootstrap_in_background() -> None:
        try:
            recovered = recover_incomplete_ingestion()
            if recovered:
                LOGGER.info("recovered_incomplete_ingestion projects=%s", [entry.get("project", entry.get("error")) for entry in recovered])
            bootstrap_existing_projects()
            LOGGER.info("bootstrap_existing_projects_complete")
        except Exception as exc:  # pragma: no cover - defensive startup guard
            LOGGER.warning("Background bootstrap failed: %s", exc)

    threading.Thread(target=_bootstrap_in_background, name="agent-code-analyzer-bootstrap", daemon=True).start()
    try:
        mcp.run(transport="stdio")
    finally:
        watcher.stop()


if __name__ == "__main__":
    main()
