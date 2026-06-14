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


def test_project_watcher_service_builds_fswatch_command_for_recursive_roots(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root_a = tmp_path / "alpha"
    root_b = tmp_path / "beta"
    root_a.mkdir()
    root_b.mkdir()
    add_project("alpha", str(root_a), mode="directory")
    add_project("beta", str(root_b), mode="directory")

    service = ProjectWatcherService()
    projects_list = [{"name": "alpha", "root_path": str(root_a)}, {"name": "beta", "root_path": str(root_b)}]

    command = service._build_fswatch_command(projects_list)

    assert command[0] == "fswatch"
    assert command[1:3] == ["-r", "--format=%p"]
    assert command[3:] == [str(root_a.resolve()), str(root_b.resolve())]


def test_project_watcher_service_reindexes_projects_for_matching_fswatch_events(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root_a = tmp_path / "alpha"
    root_b = tmp_path / "beta"
    root_a.mkdir()
    root_b.mkdir()

    events_a = root_a / "changed.py"
    events_b = root_b / "changed.py"
    events_a.write_text("print('alpha')\n", encoding="utf-8")
    events_b.write_text("print('beta')\n", encoding="utf-8")

    synced: list[str] = []
    monkeypatch.setattr(
        watcher_module,
        "sync_project_tree",
        lambda name: synced.append(name) or {"project": name, "changed_file_count": 1, "deleted_file_count": 0},
    )

    class FakeStdout:
        def __init__(self, lines: list[str]) -> None:
            self._lines = list(lines)

        def readline(self) -> str:
            return self._lines.pop(0) if self._lines else ""

    class FakeProcess:
        def __init__(self, lines: list[str]) -> None:
            self.stdout = FakeStdout(lines)
            self.stderr = FakeStdout([])
            self.terminated = False
            self.killed = False

        def poll(self):
            return 0 if not self.stdout._lines else None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout: float | None = None):
            return 0

    fake_process = FakeProcess([f"{events_a.resolve()}\n", f"{events_b.resolve()}\n", f"{tmp_path / 'outside.py'}\n", "\n"])
    monkeypatch.setattr(watcher_module.shutil, "which", lambda name: "/usr/bin/fswatch")
    monkeypatch.setattr(watcher_module.subprocess, "Popen", lambda *args, **kwargs: fake_process)

    service = ProjectWatcherService(poll_interval=0.01)
    service._stop_event.set()
    service._stop_event.clear()

    service._run_once(
        [
            {"name": "alpha", "root_path": str(root_a)},
            {"name": "beta", "root_path": str(root_b)},
        ]
    )

    assert synced == ["alpha", "beta", "alpha", "beta"]


def test_project_watcher_service_start_and_stop_manage_watcher_thread(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "alpha"
    root.mkdir()
    add_project("alpha", str(root), mode="directory")

    class FakeThread:
        def __init__(self, target, name, daemon) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            self.joined = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started and not self.joined

        def join(self, timeout: float | None = None) -> None:
            self.joined = True

    class FakeStdout:
        def readline(self) -> str:
            return ""

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout()
            self.stderr = FakeStdout()
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout: float | None = None):
            return 0

    fake_process = FakeProcess()
    monkeypatch.setattr(watcher_module.shutil, "which", lambda name: "/usr/bin/fswatch")
    monkeypatch.setattr(watcher_module.subprocess, "Popen", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr(watcher_module.threading, "Thread", FakeThread)

    service = ProjectWatcherService(poll_interval=0.01)
    scan_calls: list[str] = []
    monkeypatch.setattr(service, "scan_once", lambda: scan_calls.append("scan") or [])

    started = service.start()
    assert started is service
    assert scan_calls == ["scan"]
    assert service._thread is not None and service._thread.started is True
    assert service.start() is service
    assert scan_calls == ["scan"]
    service._process = fake_process  # type: ignore[assignment]
    service.stop()
    assert fake_process.terminated is True
    assert service._thread is None


def test_project_watcher_service_requires_fswatch_binary(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    service = ProjectWatcherService()
    monkeypatch.setattr(watcher_module.shutil, "which", lambda name: None)

    try:
        service._ensure_fswatch_available()
    except RuntimeError as exc:
        assert "fswatch" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_project_watcher_service_noops_for_empty_project_list(monkeypatch) -> None:
    service = ProjectWatcherService()
    monkeypatch.setattr(watcher_module, "subprocess", watcher_module.subprocess)

    service._run_once([])


