from __future__ import annotations

import sqlite3
from pathlib import Path
import runpy
import warnings

import pytest

from agent_code_analyzer.parsing import analyze_file, ast_skeleton, list_symbols, parse_file, _node_name
from agent_code_analyzer.projects import (
    _iter_source_files,
    _load_project_metadata,
    _read_file_record,
    add_project,
    get_project,
    ingest_project_tree,
    list_projects,
    project_file_summary,
    resolve_project_path,
    search_projects,
)
from agent_code_analyzer.server import (
    add_project as add_project_tool,
    detect_source_language,
    generate_ast_skeleton,
    ingest_project_tree as ingest_project_tree_tool,
    list_code_symbols,
    list_projects as list_projects_tool,
    parse_source,
    read_file_excerpt,
    search_projects as search_projects_tool,
)


class _DummyNode:
    type = "dummy"
    start_byte = 0
    end_byte = 0

    def child_by_field_name(self, name: str):
        return None

    @property
    def named_children(self):
        return []


class _DummyNodeWithIdentifier:
    type = "dummy"
    start_byte = 0
    end_byte = 0

    def __init__(self, name: str) -> None:
        self._name = name

    def child_by_field_name(self, name: str):
        return None

    @property
    def named_children(self):
        return [type("Identifier", (), {"type": "identifier", "text": self._name.encode("utf-8")})()]


def _isolate_project_state(tmp_path: Path, monkeypatch):
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_parsing_error_paths_and_symbol_name_fallback(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("plain text", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file extension"):
        parse_file(str(source))

    with pytest.raises(ValueError, match="Unsupported file extension"):
        analyze_file(str(source))

    assert ast_skeleton(str(source)) == ""
    assert list_symbols(str(source)) == []
    assert _node_name(_DummyNode()) == ""
    assert _node_name(_DummyNodeWithIdentifier("hello")) == "hello"


def test_project_registry_error_paths_and_missing_file_resolution(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    assert list_projects() == []
    assert search_projects("anything") == []
    assert _load_project_metadata("missing") is None

    root = tmp_path / "alpha"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "ignored.py").write_text("def ignore():\n    return 0\n", encoding="utf-8")
    (root / "code.py").write_text("def hi():\n    return 1\n", encoding="utf-8")

    added = add_project("alpha", str(root), mode="file")
    assert added["name"] == "alpha"

    with pytest.raises(ValueError, match="Unknown project"):
        get_project("missing")

    alpha_metadata = _load_project_metadata("alpha")
    assert alpha_metadata is not None
    assert alpha_metadata["name"] == "alpha"

    with pytest.raises(ValueError, match="mode must be 'file' or 'directory'"):
        add_project("bad-mode", str(root), mode="invalid")

    with pytest.raises(ValueError, match="Project root does not exist"):
        add_project("bad-root", str(tmp_path / "does-not-exist"), mode="file")

    assert search_projects(" ")[0]["name"] == "alpha"

    with pytest.raises(ValueError, match="File does not exist"):
        resolve_project_path("alpha", "missing.py")

    with pytest.raises(ValueError, match="outside project root"):
        resolve_project_path("alpha", str(tmp_path / "outside.py"))

    assert _iter_source_files(root) == [root / "code.py"]

    missing_file = root / "missing.py"
    with pytest.raises(ValueError, match="File does not exist"):
        project_file_summary("alpha", str(missing_file))


def test_project_file_summary_and_registry_helpers_cover_missing_records(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "beta"
    root.mkdir()
    source = root / "main.py"
    source.write_text("def hi():\n    return 1\n", encoding="utf-8")

    added = add_project("beta", str(root), mode="directory")

    with sqlite3.connect(projects.METADATA_DB) as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1

    with sqlite3.connect(Path(added["db_path"])) as conn:
        row = conn.execute("SELECT id FROM files WHERE rel_path = ?", ("main.py",)).fetchone()
        assert row is not None
        conn.execute("DELETE FROM files WHERE id = ?", (row[0],))
        conn.execute("DELETE FROM symbols")
        conn.commit()
        with pytest.raises(ValueError, match="Indexed file record disappeared"):
            _read_file_record(conn, row[0])

    def noop_upsert(*args, **kwargs):
        return None

    monkeypatch.setattr(projects, "_upsert_file_analysis", noop_upsert)
    with pytest.raises(ValueError, match="Failed to persist file analysis"):
        project_file_summary("beta", "main.py")


def test_server_wrappers_and_file_excerpt_cover_tool_paths(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "gamma"
    root.mkdir()
    source = root / "tool.py"
    source.write_text("def tool():\n    return 3\n", encoding="utf-8")

    added = add_project_tool("gamma", str(root), mode="directory", description="tool wrapper")
    assert added["name"] == "gamma"

    assert [row["name"] for row in list_projects_tool()] == ["gamma"]
    assert [row["name"] for row in search_projects_tool("tool")][0] == "gamma"

    ingested = ingest_project_tree_tool("gamma", refresh=False)
    assert ingested["project"] == "gamma"

    assert parse_source("gamma", "tool.py")["supported"] is True
    assert detect_source_language("gamma", "tool.py") == "python"
    assert "tool" in generate_ast_skeleton("gamma", "tool.py")
    assert "tool" in list_code_symbols("gamma", "tool.py")

    assert read_file_excerpt("gamma", "tool.py", start_line=2, end_line=3) == "2:     return 3"
    assert read_file_excerpt("gamma", "tool.py", start_line=0, end_line=1) == "1: def tool():"
    assert read_file_excerpt("gamma", "tool.py", start_line=5, end_line=3) == ""

    # Exercise the direct project registry helpers too.
    assert list_projects()[0]["name"] == "gamma"
    assert search_projects("gamma")[0]["name"] == "gamma"
    assert get_project("gamma")["name"] == "gamma"

    import agent_code_analyzer.watcher as watcher
    import mcp.server.fastmcp as fastmcp

    monkeypatch.setattr(watcher.ProjectWatcherService, "start", lambda self: self)
    monkeypatch.setattr(watcher.ProjectWatcherService, "stop", lambda self: None)
    monkeypatch.setattr(fastmcp.FastMCP, "run", lambda self, transport="stdio": None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("agent_code_analyzer.server", run_name="__main__")
