from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agent_code_analyzer.projects import add_project, ingest_project_tree
from agent_code_analyzer.project_sync_steps import project_sync_diff
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


def test_ingest_project_tree_refresh_rebuilds_every_supported_file(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    class FakeVectorIndex:
        def __init__(self) -> None:
            self.sync_calls: list[dict[str, Any]] = []

        def sync_records(self, **kwargs) -> dict[str, Any]:
            self.sync_calls.append(kwargs)
            return {"points": len(kwargs.get("symbol_rows", [])) + 1}

        def delete_file(self, sqlite_uri: str) -> None:
            return None

        def delete_project(self, project: str) -> None:
            return None

    fake_index = FakeVectorIndex()
    monkeypatch.setattr("agent_code_analyzer.vector_index.get_vector_index", lambda: fake_index)

    root = tmp_path / "refresh"
    root.mkdir()
    (root / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (root / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")

    added = add_project("refresh", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 2

    fake_index.sync_calls.clear()

    import agent_code_analyzer.project_service as project_service

    original_analyze_file = project_service.analyze_file
    analyzed_paths: list[str] = []

    def counting_analyze_file(path: str, *args, **kwargs):
        analyzed_paths.append(Path(path).name)
        return original_analyze_file(path, *args, **kwargs)

    monkeypatch.setattr(project_service, "analyze_file", counting_analyze_file)

    summary = ingest_project_tree("refresh", refresh=True)

    assert summary["project"] == "refresh"
    assert summary["file_count"] == 2
    assert summary["supported_file_count"] == 2
    assert summary["symbol_count"] == 2
    assert analyzed_paths == ["alpha.py", "beta.py"]
    assert len(fake_index.sync_calls) == 2


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


def test_sync_project_tree_tracks_changed_and_deleted_files(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    class FakeVectorIndex:
        def __init__(self) -> None:
            self.sync_calls: list[dict[str, Any]] = []
            self.deleted_files: list[str] = []
            self.deleted_projects: list[str] = []

        def sync_records(self, **kwargs) -> dict[str, Any]:
            self.sync_calls.append(kwargs)
            return {"points": len(kwargs.get("symbol_rows", [])) + 1}

        def delete_file(self, sqlite_uri: str) -> None:
            self.deleted_files.append(sqlite_uri)

        def delete_project(self, project: str) -> None:
            self.deleted_projects.append(project)

    fake_index = FakeVectorIndex()
    monkeypatch.setattr("agent_code_analyzer.vector_index.get_vector_index", lambda: fake_index)

    root = tmp_path / "sync"
    root.mkdir()
    alpha = root / "alpha.py"
    beta = root / "beta.py"
    alpha.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    beta.write_text("def beta():\n    return 2\n", encoding="utf-8")

    added = add_project("sync", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 2

    beta.unlink()
    alpha.write_text("def alpha():\n    return 10\n", encoding="utf-8")

    summary = projects.sync_project_tree("sync")

    assert summary["changed_file_count"] == 1
    assert summary["deleted_file_count"] == 1
    assert summary["unchanged_file_count"] == 0
    assert fake_index.deleted_files == ["sqlite://projects/sync/files/2"]

    db_path = Path(added["db_path"])
    with sqlite3.connect(db_path) as conn:
        file_rows = conn.execute("SELECT rel_path FROM files ORDER BY rel_path ASC").fetchall()
        assert [row[0] for row in file_rows] == ["alpha.py"]
        symbol_rows = conn.execute("SELECT name FROM symbols ORDER BY id ASC").fetchall()
        assert [row[0] for row in symbol_rows] == ["alpha"]
        project_state = conn.execute(
            "SELECT file_count, supported_file_count, symbol_count FROM project_state WHERE project_name = ?",
            ("sync",),
        ).fetchone()
        assert project_state == (1, 1, 1)


def test_project_sync_diff_uses_content_hash_to_detect_drift(tmp_path: Path) -> None:
    file_path = tmp_path / "alpha.py"
    file_path.write_text("def alpha():\n    return 1\n", encoding="utf-8")

    current_files = {"alpha.py": file_path}
    current_stats = {"alpha.py": {"file_size": 26, "file_mtime_ns": 123, "file_content_hash": "new-hash"}}
    existing_files = {
        "alpha.py": {
            "file_size": 26,
            "file_mtime_ns": 123,
            "file_content_hash": "old-hash",
        }
    }

    deleted_paths, unchanged_paths, changed_paths = project_sync_diff(existing_files, current_files, current_stats)

    assert deleted_paths == []
    assert unchanged_paths == []
    assert changed_paths == ["alpha.py"]
