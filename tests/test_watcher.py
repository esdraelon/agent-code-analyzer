from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import io

from agent_code_analyzer.watcher import DirtyProjectQueue, ProjectWatcherService


@dataclass
class SyncRecorder:
    calls: list[str]

    def __call__(self, project: str) -> dict[str, Any]:
        self.calls.append(project)
        return {
            "project": project,
            "changed_file_count": 1,
            "deleted_file_count": 0,
            "unchanged_file_count": 0,
        }


class _FakeProcess:
    def __init__(self, output: str) -> None:
        self.stdout = io.StringIO(output)
        self._polled = False
        self.terminated = False
        self.killed = False

    def poll(self):
        if self._polled:
            return 0
        if self.stdout.tell() >= len(self.stdout.getvalue()):
            self._polled = True
            return 0
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None):
        self._polled = True
        return 0


@dataclass
class _ErrorRecorder:
    calls: list[str]

    def __call__(self, project: str) -> dict[str, Any]:
        self.calls.append(project)
        if project == "beta":
            raise RuntimeError("boom")
        return {
            "project": project,
            "changed_file_count": 0,
            "deleted_file_count": 0,
            "unchanged_file_count": 1,
        }


class _OneShotEvent:
    def __init__(self) -> None:
        self.calls = 0

    def is_set(self) -> bool:
        return self.calls > 1

    def wait(self, timeout: float) -> bool:
        self.calls += 1
        return False

    def set(self) -> None:
        self.calls = 2


class _TerminateOnlyProcess:
    def __init__(self) -> None:
        self.poll_calls = 0
        self.terminated = False
        self.killed = False

    def poll(self):
        self.poll_calls += 1
        return None

    def terminate(self) -> None:
        self.terminated = True
        raise RuntimeError("terminate failed")

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None):
        return 0


def test_dirty_project_queue_dedupes_and_delays_flush() -> None:
    queue = DirtyProjectQueue(debounce_seconds=1.0)

    queue.mark_dirty("alpha", now=10.0)
    queue.mark_dirty("alpha", now=10.5)
    queue.mark_dirty("beta", now=10.6)

    assert queue.pending_projects() == ["alpha", "beta"]
    assert queue.pop_ready(now=11.2) == []
    assert queue.pop_ready(now=11.6) == ["alpha", "beta"]
    assert queue.pending_projects() == []


def test_dirty_project_queue_bulk_updates_and_status_queries() -> None:
    queue = DirtyProjectQueue(debounce_seconds=2.0)

    assert queue.next_ready_at() is None
    assert queue.has_pending() is False

    queue.mark_many_dirty(["gamma", "alpha", "gamma"], now=5.0)
    assert queue.pending_projects() == ["alpha", "gamma"]
    assert queue.has_pending() is True
    assert queue.next_ready_at() == 7.0
    assert queue.pop_ready(now=6.9) == []
    assert queue.pop_ready(now=7.0) == ["alpha", "gamma"]
    assert queue.has_pending() is False


def test_project_watcher_service_enqueues_each_project_once_per_burst() -> None:
    synced: list[str] = []
    projects = [
        {"name": "alpha", "root_path": "/repo/alpha"},
        {"name": "beta", "root_path": "/repo/beta"},
    ]
    service = ProjectWatcherService(
        debounce_seconds=1.0,
        safety_sweep_interval=10.0,
        project_provider=lambda: projects,
        sync_callback=SyncRecorder(synced),
    )

    service.observe_event("/repo/alpha/src/app.py", now=1.0)
    service.observe_event("/repo/alpha/src/app.py", now=1.3)
    service.observe_event("/repo/beta/src/main.py", now=1.4)

    assert service.flush_ready_projects(now=2.0) == []
    assert synced == []

    flushed = service.flush_ready_projects(now=2.6)
    assert [item["project"] for item in flushed] == ["alpha", "beta"]
    assert synced == ["alpha", "beta"]


def test_project_watcher_service_fallback_and_error_paths() -> None:
    calls: list[str] = []
    projects = [
        {"name": "alpha", "root_path": "/repo/alpha"},
        {"name": "beta", "root_path": "/repo/beta"},
    ]
    service = ProjectWatcherService(
        debounce_seconds=0.5,
        safety_sweep_interval=10.0,
        project_provider=lambda: projects,
        sync_callback=_ErrorRecorder(calls),
    )

    assert service.observe_event("/repo/alpha/sub/file.py", projects=projects, now=1.0) == ["alpha"]
    assert service.observe_event("/elsewhere/file.py", projects=projects, now=1.0) == ["alpha", "beta"]

    flushed = service.flush_ready_projects(now=2.0)
    assert [item["project"] for item in flushed] == ["alpha", "beta"]
    assert flushed[0]["changed_file_count"] == 0
    assert flushed[1]["error"] == "boom"
    assert calls == ["alpha", "beta"]


def test_project_watcher_service_start_and_stop_are_idempotent(monkeypatch) -> None:
    service = ProjectWatcherService(
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder([]),
    )
    monkeypatch.setattr(service, "_ensure_fswatch_available", lambda: None)
    monkeypatch.setattr(service, "scan_once", lambda: [])
    monkeypatch.setattr(service, "_watch_loop", lambda: service._stop_event.wait(0.2))
    monkeypatch.setattr(service, "_sweep_loop", lambda: service._stop_event.wait(0.2))

    started = service.start()
    assert started is service
    watch_thread = service._watch_thread
    assert watch_thread is not None and watch_thread.is_alive()
    assert service.start() is service

    service.stop()
    assert service._watch_thread is None
    assert service._sweep_thread is None


def test_project_watcher_service_watch_loop_processes_one_event_and_terminates(monkeypatch) -> None:
    synced: list[str] = []
    service = ProjectWatcherService(
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder(synced),
    )
    fake_process = _FakeProcess("/repo/alpha/src/app.py\n")
    monkeypatch.setattr("agent_code_analyzer.watcher.subprocess.Popen", lambda *args, **kwargs: fake_process)

    service._watch_loop()

    assert service.flush_ready_projects(now=999999999999.0)[0]["project"] == "alpha"
    assert fake_process.terminated is False
    assert service.last_results[0]["project"] == "alpha"


def test_safety_sweep_checks_queue_before_running() -> None:
    synced: list[str] = []
    service = ProjectWatcherService(
        debounce_seconds=1.0,
        safety_sweep_interval=10.0,
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder(synced),
    )

    service.enqueue_project("alpha", now=0.0)
    assert service.run_safety_sweep(now=5.0) == []
    assert synced == []

    flushed = service.run_safety_sweep(now=11.0)
    assert [item["project"] for item in flushed] == ["alpha"]
    assert synced == ["alpha"]


def test_safety_sweep_skips_when_empty_and_records_no_results() -> None:
    service = ProjectWatcherService(
        debounce_seconds=1.0,
        safety_sweep_interval=10.0,
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder([]),
    )

    assert service.run_safety_sweep(now=20.0) == []
    assert service.flush_ready_projects(now=20.0) == []
    assert service.last_results == []


def test_project_watcher_service_ensure_and_context_manager_paths(monkeypatch) -> None:
    service = ProjectWatcherService(
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder([]),
    )

    monkeypatch.setattr("agent_code_analyzer.watcher.shutil.which", lambda command: None)
    try:
        service._ensure_fswatch_available()
    except RuntimeError as exc:
        assert "fswatch" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected RuntimeError")

    monkeypatch.setattr(service, "_ensure_fswatch_available", lambda: None)
    monkeypatch.setattr(service, "scan_once", lambda: [])
    monkeypatch.setattr(service, "_watch_loop", lambda: service._stop_event.wait(0.1))
    monkeypatch.setattr(service, "_sweep_loop", lambda: service._stop_event.wait(0.1))

    with service as started:
        assert started is service
        assert service._watch_thread is not None and service._watch_thread.is_alive()

    assert service._watch_thread is None
    assert service._sweep_thread is None


def test_project_watcher_service_path_helpers_and_terminate_branch(monkeypatch) -> None:
    service = ProjectWatcherService(
        project_provider=lambda: [
            {"name": "alpha", "root_path": "/repo/alpha"},
            {"name": "alpha-nested", "root_path": "/repo/alpha/nested"},
        ],
        sync_callback=SyncRecorder([]),
    )

    roots = service._project_roots(service.project_provider())
    assert roots == [("alpha", "/repo/alpha"), ("alpha-nested", "/repo/alpha/nested")]
    assert service._build_fswatch_command(service.project_provider())[:3] == ["fswatch", "-r", "--format=%p"]
    nested = service._project_for_path(service.project_provider(), "/repo/alpha/nested/file.py")
    assert nested is not None
    assert nested["name"] == "alpha-nested"
    assert service._project_for_path(service.project_provider(), "/elsewhere/file.py") is None

    process = _TerminateOnlyProcess()
    service._terminate_process(process)
    assert process.terminated is True
    assert process.killed is True


def test_project_watcher_service_empty_watch_and_sweep_loop_paths(monkeypatch) -> None:
    service = ProjectWatcherService(
        project_provider=lambda: [],
        sync_callback=SyncRecorder([]),
    )

    service._watch_loop()
    assert service.last_results == []

    service = ProjectWatcherService(
        project_provider=lambda: [{"name": "alpha", "root_path": "/repo/alpha"}],
        sync_callback=SyncRecorder([]),
    )
    monkeypatch.setattr(service, "run_safety_sweep", lambda now=None: service._stop_event.set() or [])
    service._stop_event = _OneShotEvent()
    service._sweep_loop()
