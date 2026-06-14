from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
import runpy
import warnings
from typing import Any, cast

import pytest

from agent_code_analyzer.parsing import analyze_file, ast_skeleton, list_symbols, parse_file, _node_name
import agent_code_analyzer.projects as projects
from agent_code_analyzer.projects import (
    _acquire_locks,
    _connect,
    _db_lock,
    _ensure_project_schema,
    _init_metadata_schema,
    _init_project_schema,
    _iter_source_files,
    _load_project_metadata,
    _project_db_path,
    _read_file_record,
    _row_to_project_dict,
    _row_to_summary,
    _slugify,
    _symbol_rows,
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


@dataclass
class _FakeRootNode:
    type: str = "module"
    descendant_count: int = 3
    has_error: bool = False


@dataclass
class _FakeTree:
    root_node: _FakeRootNode


@dataclass
class _FakeParsed:
    language: str
    source_code: str
    source_bytes: bytes
    tree: _FakeTree


@dataclass
class _FakeNode:
    type: str
    name: str
    signature: str
    row: int = 0
    column: int = 0
    end_row: int = 0
    end_column: int = 0
    depth: int = 0


def _fake_analysis(path: Path, symbol_name: str = "hi") -> dict[str, Any]:
    source_code = path.read_text(encoding="utf-8")
    parsed = _FakeParsed(
        language="python",
        source_code=source_code,
        source_bytes=source_code.encode("utf-8"),
        tree=_FakeTree(root_node=_FakeRootNode()),
    )
    return {
        "parsed": parsed,
        "skeleton": f"[function_definition] def {symbol_name}()",
        "symbols": [
            {
                "type": "function_definition",
                "name": symbol_name,
                "depth": 0,
                "start_point": {"row": 0, "column": 0},
                "end_point": {"row": 1, "column": 0},
                "signature": f"def {symbol_name}():",
            }
        ],
    }


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


def test_parse_file_handles_non_utf8_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "legacy.php"
    source.write_bytes(b"<?php\nfunction hi() { /* \xb0 */ return 1; }\n")

    parsed = parse_file(str(source))

    assert parsed.language == "php"
    assert "°" in parsed.source_code


def test_analyze_file_preserves_symbol_offsets_after_unicode_prefix(tmp_path: Path) -> None:
    source = tmp_path / "long_unicode.js"
    filler = ["// filler" for _ in range(1200)]
    body = [
        "// — unicode before the symbol",
        "if (true) {",
        "  function hi() {",
        "    return 1;",
        "  }",
        "}",
    ]
    source.write_text("\n".join(filler + body) + "\n", encoding="utf-8")

    symbols = list_symbols(str(source))
    symbol = cast(dict[str, Any], symbols[0])

    assert symbol["name"] == "hi"
    assert symbol["signature"] == "function hi()"
    assert symbol["start_point"]["row"] >= 1200


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


def test_project_private_helpers_and_schema_migration_cover_remaining_paths(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    assert _slugify("  Weird Project!!  ") == "weird-project"
    db_path = _project_db_path("Weird Project!!")
    assert db_path.name == "project.sqlite3"
    assert "weird-project" in str(db_path)
    assert _db_lock(db_path) is _db_lock(db_path)

    old_db = tmp_path / "state" / "legacy.sqlite3"
    with _connect(old_db) as conn:
        conn.execute(
            """
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_path TEXT NOT NULL UNIQUE,
                abs_path TEXT NOT NULL,
                language TEXT NOT NULL,
                root_type TEXT NOT NULL,
                node_count INTEGER NOT NULL,
                has_error INTEGER NOT NULL,
                byte_length INTEGER NOT NULL,
                skeleton TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO files (rel_path, abs_path, language, root_type, node_count, has_error, byte_length, skeleton, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("main.py", "/tmp/main.py", "python", "module", 1, 0, 20, "s", "now"))
        conn.commit()

    with _connect(old_db) as conn:
        _ensure_project_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        assert {"file_size", "file_mtime_ns"}.issubset(columns)

    with _connect(projects.METADATA_DB) as conn:
        _init_metadata_schema(conn)
        row = conn.execute(
            "SELECT 'gamma' AS name, '/root' AS root_path, '/db' AS db_path, 'directory' AS mode, 'desc' AS description, 'created' AS created_at, 'updated' AS updated_at, 'indexed' AS indexed_at, 3 AS file_count, 2 AS supported_file_count, 1 AS symbol_count"
        ).fetchone()
        assert _row_to_project_dict(row)["name"] == "gamma"

    with _connect(old_db) as conn:
        _init_project_schema(conn)
        conn.execute("DELETE FROM files")
        conn.execute(
            "INSERT INTO files (rel_path, abs_path, language, root_type, node_count, has_error, byte_length, file_size, file_mtime_ns, skeleton, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("main.py", "/tmp/main.py", "python", "module", 1, 0, 20, 20, 1, "s", "now"),
        )
        file_id = conn.execute("SELECT id FROM files WHERE rel_path = ?", ("main.py",)).fetchone()[0]
        conn.execute(
            "INSERT INTO symbols (file_id, symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, 0, "function_definition", "main", 0, 0, 0, 1, 0, "def main():"),
        )
        symbol_rows = _symbol_rows(conn, file_id)
        assert symbol_rows[0]["name"] == "main"
        summary_row = conn.execute("SELECT 'project' AS project_name, '/root' AS root_path, 1 AS file_count, 1 AS supported_file_count, 1 AS symbol_count, 'now' AS indexed_at").fetchone()
        assert _row_to_summary(summary_row)["project"] == "project"


def test_project_ingest_refresh_and_sync_branches_cover_remaining_paths(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "delta"
    root.mkdir()
    first = root / "first.py"
    second = root / "second.py"
    first.write_text("def first():\n    return 1\n", encoding="utf-8")
    second.write_text("def second():\n    return 2\n", encoding="utf-8")

    def fake_analyze(path: str):
        source = Path(path)
        return _fake_analysis(source, symbol_name=source.stem)

    monkeypatch.setattr(projects, "analyze_file", fake_analyze)

    added = add_project("delta", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 2
    assert added["ingest"]["symbol_count"] == 2

    assert ingest_project_tree("delta", refresh=False)["file_count"] == 2

    first.write_text("def first():\n    return 10\n", encoding="utf-8")
    second.unlink()
    third = root / "third.py"
    third.write_text("def third():\n    return 3\n", encoding="utf-8")

    sync = projects.sync_project_tree("delta")
    assert sync["changed_file_count"] == 2
    assert sync["deleted_file_count"] == 1
    assert sync["file_count"] == 2

    noop = projects.sync_project_tree("delta")
    assert noop["changed_file_count"] == 0
    assert noop["deleted_file_count"] == 0
    assert noop["unchanged_file_count"] == 2
