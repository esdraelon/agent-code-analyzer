from __future__ import annotations

import sqlite3
from pathlib import Path

import agent_code_analyzer.projects as projects
import agent_code_analyzer.watcher as watcher_module
from agent_code_analyzer.projects import add_project, sync_project_tree
from agent_code_analyzer.watcher import ProjectWatcherService


def _isolate_project_state(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_sync_project_tree_reindexes_only_changed_files_and_removes_deleted_ones(tmp_path: Path, monkeypatch) -> None:
    projects_module = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "watch"
    root.mkdir()
    keep = root / "keep.py"
    change = root / "change.py"
    delete_me = root / "delete_me.py"
    keep.write_text("def keep():\n    return 1\n", encoding="utf-8")
    change.write_text("def change():\n    return 2\n", encoding="utf-8")
    delete_me.write_text("def gone():\n    return 3\n", encoding="utf-8")

    added = add_project("watch", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 3

    original_analyze_file = projects_module.analyze_file
    analyzed_paths: list[str] = []

    def analyze_spy(path: str):
        analyzed_paths.append(Path(path).name)
        return original_analyze_file(path)

    monkeypatch.setattr(projects_module, "analyze_file", analyze_spy)

    change.write_text("def change():\n    return 200\n", encoding="utf-8")
    new_file = root / "new_file.py"
    new_file.write_text("def added():\n    return 4\n", encoding="utf-8")
    delete_me.unlink()

    result = sync_project_tree("watch")
    assert result["changed_file_count"] == 2
    assert result["deleted_file_count"] == 1
    assert result["unchanged_file_count"] == 1
    assert sorted(analyzed_paths) == ["change.py", "new_file.py"]

    db_path = Path(added["db_path"])
    with sqlite3.connect(db_path) as conn:
        rel_paths = [row[0] for row in conn.execute("SELECT rel_path FROM files ORDER BY rel_path ASC").fetchall()]
        assert rel_paths == ["change.py", "keep.py", "new_file.py"]
        symbol_names = [row[0] for row in conn.execute("SELECT name FROM symbols ORDER BY id ASC").fetchall()]
        assert "gone" not in symbol_names
        assert "added" in symbol_names

    analyzed_paths.clear()
    monkeypatch.setattr(projects_module, "analyze_file", lambda path: (_ for _ in ()).throw(AssertionError("no-op sync should not reparse")))
    no_op = sync_project_tree("watch")
    assert no_op["changed_file_count"] == 0
    assert no_op["deleted_file_count"] == 0
    assert no_op["unchanged_file_count"] == 3


def test_ensure_project_schema_adds_missing_file_columns(tmp_path: Path, monkeypatch) -> None:
    projects_module = _isolate_project_state(tmp_path, monkeypatch)

    with sqlite3.connect(tmp_path / "legacy.sqlite3") as conn:
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
        projects_module._ensure_project_schema(conn)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()]

    assert "file_size" in columns
    assert "file_mtime_ns" in columns


def test_project_watcher_service_scans_registered_projects(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    seen: list[str] = []
    monkeypatch.setattr(watcher_module, "list_projects", lambda: [{"name": "one"}, {"name": "two"}])
    monkeypatch.setattr(
        watcher_module,
        "sync_project_tree",
        lambda name: seen.append(name) or {"project": name, "changed_file_count": 1, "deleted_file_count": 0},
    )

    service = ProjectWatcherService(poll_interval=0.01)
    results = service.scan_once()

    assert seen == ["one", "two"]
    assert results == [
        {"project": "one", "changed_file_count": 1, "deleted_file_count": 0},
        {"project": "two", "changed_file_count": 1, "deleted_file_count": 0},
    ]
    assert service.last_results == results


def test_project_watcher_service_lifecycle_and_run_loop(monkeypatch) -> None:
    start_calls: list[str] = []
    join_calls: list[float] = []
    scan_calls: list[str] = []

    class FakeThread:
        def __init__(self, target, name, daemon) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            self.alive = False

        def start(self) -> None:
            start_calls.append(self.name)
            self.started = True
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout: float | None = None) -> None:
            join_calls.append(float(timeout or 0.0))
            self.alive = False

    class FakeEvent:
        def __init__(self, waits: list[bool]) -> None:
            self._waits = list(waits)
            self.set_called = False
            self.clear_called = False

        def clear(self) -> None:
            self.clear_called = True

        def set(self) -> None:
            self.set_called = True

        def wait(self, interval: float) -> bool:
            return self._waits.pop(0)

    monkeypatch.setattr(watcher_module.threading, "Thread", FakeThread)

    service = ProjectWatcherService(poll_interval=0.01)
    service._stop_event = FakeEvent([False, True])
    monkeypatch.setattr(service, "scan_once", lambda: scan_calls.append("scan") or [])

    started = service.start()
    assert started is service
    assert start_calls == ["agent-code-analyzer-watcher"]
    assert service._thread is not None and service._thread.started is True

    service.start()
    assert start_calls == ["agent-code-analyzer-watcher"]

    service.stop()
    assert join_calls == [5.0]
    assert service._thread is None
    assert service._stop_event.set_called is True

    service.close()

    with service as entered:
        assert entered is service
        assert service._thread is not None

    assert service._thread is None
    assert service._stop_event.clear_called is True

    service._run()
    assert scan_calls == ["scan", "scan"]
