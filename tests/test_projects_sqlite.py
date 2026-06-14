from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agent_code_analyzer.projects import add_project, ingest_project_tree
from agent_code_analyzer.server import (
    detect_source_language,
    generate_ast_skeleton,
    list_code_symbols,
    parse_source,
)


def _isolate_project_state(tmp_path: Path, monkeypatch) -> Any:
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_ingest_project_tree_reuses_cached_project_state_without_reparsing(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "cached"
    root.mkdir()
    (root / "app.py").write_text("def hello():\n    return 'ok'\n", encoding="utf-8")

    added = add_project("cached", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 1

    def fail_if_reparsed(*args, **kwargs):  # pragma: no cover - defensive guard
        raise AssertionError("cached ingest should not reparse unchanged project state")

    monkeypatch.setattr(projects, "analyze_file", fail_if_reparsed)

    summary = ingest_project_tree("cached", refresh=False)
    assert summary["project"] == "cached"
    assert summary["file_count"] == 1
    assert summary["supported_file_count"] == 1
    assert summary["symbol_count"] == 1


def test_project_tools_reject_paths_outside_project_root(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "scope"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("def outside():\n    return 1\n", encoding="utf-8")

    add_project("scope", str(root), mode="file")

    parsed = parse_source("scope", str(outside))
    assert parsed["supported"] is False
    assert "outside project root" in parsed["error"]
    assert detect_source_language("scope", str(outside)) == ""
    assert generate_ast_skeleton("scope", str(outside)) == ""
    assert list_code_symbols("scope", str(outside)) == "[]"


def test_directory_ingest_skips_unsupported_files(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "mixed"
    root.mkdir()
    (root / "service.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (root / "README.txt").write_text("not source code", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")

    added = add_project("mixed", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 1
    assert added["ingest"]["supported_file_count"] == 1
    assert added["ingest"]["symbol_count"] == 1

    db_path = Path(added["db_path"])
    with sqlite3.connect(db_path) as conn:
        file_rows = conn.execute("SELECT rel_path FROM files ORDER BY rel_path ASC").fetchall()
        assert [row[0] for row in file_rows] == ["service.py"]

        symbol_rows = conn.execute("SELECT name FROM symbols ORDER BY id ASC").fetchall()
        assert [row[0] for row in symbol_rows] == ["ok"]

        project_state = conn.execute(
            "SELECT file_count, supported_file_count, symbol_count FROM project_state WHERE project_name = ?",
            ("mixed",),
        ).fetchone()
        assert project_state == (1, 1, 1)

    with sqlite3.connect(projects.METADATA_DB) as conn:
        project_row = conn.execute(
            "SELECT file_count, supported_file_count, symbol_count FROM projects WHERE name = ?",
            ("mixed",),
        ).fetchone()
        assert project_row == (1, 1, 1)
