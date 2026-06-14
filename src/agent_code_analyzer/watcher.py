from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .projects import list_projects, sync_project_tree


@dataclass
class DirtyProjectQueue:
    """Deduplicated project-level dirty queue with debounce deadlines."""

    debounce_seconds: float = 1.0
    _dirty_until: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def mark_dirty(self, project: str, now: float | None = None) -> None:
        current = self._now(now)
        with self._lock:
            self._dirty_until[project] = current + self.debounce_seconds

    def mark_many_dirty(self, projects: Iterable[str], now: float | None = None) -> None:
        current = self._now(now)
        with self._lock:
            due_at = current + self.debounce_seconds
            for project in projects:
                self._dirty_until[project] = due_at

    def pending_projects(self) -> list[str]:
        with self._lock:
            return sorted(self._dirty_until)

    def pop_ready(self, now: float | None = None) -> list[str]:
        current = self._now(now)
        with self._lock:
            ready = sorted(project for project, due_at in self._dirty_until.items() if due_at <= current)
            for project in ready:
                self._dirty_until.pop(project, None)
            return ready

    def next_ready_at(self) -> float | None:
        with self._lock:
            if not self._dirty_until:
                return None
            return min(self._dirty_until.values())

    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._dirty_until)

    @staticmethod
    def _now(now: float | None) -> float:
        return time.monotonic() if now is None else now


@dataclass
class ProjectWatcherService:
    """Background fswatch-driven watcher that keeps configured projects in sync."""

    debounce_seconds: float = 1.0
    safety_sweep_interval: float = 10.0
    poll_interval: float = 0.05
    fswatch_command: str = "fswatch"
    project_provider: Callable[[], list[dict[str, Any]]] = list_projects
    sync_callback: Callable[[str], dict[str, Any]] = sync_project_tree
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _watch_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _sweep_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _last_results: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _last_sweep_at: float = field(default=0.0, init=False, repr=False)
    _dirty_queue: DirtyProjectQueue = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._dirty_queue = DirtyProjectQueue(debounce_seconds=self.debounce_seconds)

    def start(self) -> "ProjectWatcherService":
        if self._watch_thread is not None and self._watch_thread.is_alive():
            return self
        self._ensure_fswatch_available()
        self._stop_event.clear()
        self.scan_once()
        self._watch_thread = threading.Thread(target=self._watch_loop, name="agent-code-analyzer-fswatch", daemon=True)
        self._sweep_thread = threading.Thread(target=self._sweep_loop, name="agent-code-analyzer-sweep", daemon=True)
        self._watch_thread.start()
        self._sweep_thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is not None:
            self._terminate_process(process)
        for thread in (self._watch_thread, self._sweep_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=5.0)
        self._watch_thread = None
        self._sweep_thread = None
        self._process = None

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> "ProjectWatcherService":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def scan_once(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for project in self.project_provider():
            name = project["name"]
            try:
                result = self.sync_callback(name)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                results.append({"project": name, "error": str(exc)})
                continue

            if result.get("changed_file_count") or result.get("deleted_file_count"):
                results.append(result)
        self._last_results = results
        return results

    def enqueue_project(self, project_name: str, now: float | None = None) -> None:
        self._dirty_queue.mark_dirty(project_name, now=now)

    def enqueue_projects(self, project_names: Iterable[str], now: float | None = None) -> None:
        self._dirty_queue.mark_many_dirty(project_names, now=now)

    def observe_event(
        self,
        event_path: str,
        projects: list[dict[str, Any]] | None = None,
        now: float | None = None,
    ) -> list[str]:
        active_projects = projects if projects is not None else self.project_provider()
        matched = self._project_for_path(active_projects, event_path)
        if matched is None:
            project_names = [project["name"] for project in active_projects]
        else:
            project_names = [matched["name"]]
        self.enqueue_projects(project_names, now=now)
        return project_names

    def flush_ready_projects(self, now: float | None = None) -> list[dict[str, Any]]:
        ready_projects = self._dirty_queue.pop_ready(now=now)
        results: list[dict[str, Any]] = []
        for project_name in ready_projects:
            try:
                result = self.sync_callback(project_name)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                result = {"project": project_name, "error": str(exc)}
            else:
                self._record_result(result)
            results.append(result)
        return results

    def run_safety_sweep(self, now: float | None = None) -> list[dict[str, Any]]:
        current = self.clock() if now is None else now
        if current - self._last_sweep_at < self.safety_sweep_interval:
            return []

        if not self._dirty_queue.has_pending():
            return []

        ready = self.flush_ready_projects(now=current)
        if ready:
            self._last_sweep_at = current
        return ready

    @property
    def last_results(self) -> list[dict[str, Any]]:
        return list(self._last_results)

    def _ensure_fswatch_available(self) -> None:
        if shutil.which(self.fswatch_command) is None:
            raise RuntimeError(
                f"{self.fswatch_command!r} is required for filesystem watching but was not found on PATH"
            )

    def _project_roots(self, projects: list[dict[str, Any]]) -> list[tuple[str, str]]:
        roots: list[tuple[str, str]] = []
        for project in projects:
            root = str(Path(project["root_path"]).resolve())
            roots.append((project["name"], root))
        return roots

    def _build_fswatch_command(self, projects: list[dict[str, Any]]) -> list[str]:
        roots = self._project_roots(projects)
        return [self.fswatch_command, "-r", "--format=%p", *[root for _, root in roots]]

    def _project_for_path(
        self,
        projects: list[dict[str, Any]],
        event_path: str,
    ) -> dict[str, Any] | None:
        candidate = Path(event_path.strip()).resolve()
        candidate_text = str(candidate)
        best_project: dict[str, Any] | None = None
        best_root_length = -1
        for project in projects:
            root = str(Path(project["root_path"]).resolve())
            if candidate_text == root or candidate_text.startswith(root + os.sep):
                if len(root) > best_root_length:
                    best_project = project
                    best_root_length = len(root)
        return best_project

    def _record_result(self, result: dict[str, Any]) -> None:
        if result.get("changed_file_count") or result.get("deleted_file_count"):
            self._last_results.append(result)

    def _watch_loop(self) -> None:
        projects = self.project_provider()
        if not projects:
            return

        command = self._build_fswatch_command(projects)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._process = process
        try:
            stdout = process.stdout
            if stdout is None:
                return
            while not self._stop_event.is_set():
                line = stdout.readline()
                if line:
                    event_path = line.strip()
                    if not event_path:
                        continue
                    self.observe_event(event_path, projects=projects, now=self.clock())
                    continue

                if process.poll() is not None:
                    break

                self.sleeper(self.poll_interval)
        finally:
            self._terminate_process(process)
            self._process = None

    def _sweep_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self.safety_sweep_interval)
            if self._stop_event.is_set():
                break
            self.run_safety_sweep(now=self.clock())

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2.0)
            except Exception:
                pass
