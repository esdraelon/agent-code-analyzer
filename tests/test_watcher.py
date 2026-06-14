from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def test_dirty_project_queue_dedupes_and_delays_flush() -> None:
    queue = DirtyProjectQueue(debounce_seconds=1.0)

    queue.mark_dirty("alpha", now=10.0)
    queue.mark_dirty("alpha", now=10.5)
    queue.mark_dirty("beta", now=10.6)

    assert queue.pending_projects() == ["alpha", "beta"]
    assert queue.pop_ready(now=11.2) == []
    assert queue.pop_ready(now=11.6) == ["alpha", "beta"]
    assert queue.pending_projects() == []


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
