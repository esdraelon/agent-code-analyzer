from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .projects import list_projects, sync_project_tree


@dataclass
class ProjectWatcherService:
    """Background fswatch-driven watcher that keeps configured projects in sync."""

    poll_interval: float = 2.0
    fswatch_command: str = "fswatch"
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _last_results: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def start(self) -> "ProjectWatcherService":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._ensure_fswatch_available()
        self._stop_event.clear()
        self.scan_once()
        self._thread = threading.Thread(target=self._run, name="agent-code-analyzer-fswatch", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is not None:
            self._terminate_process(process)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._thread = None
        self._process = None

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> "ProjectWatcherService":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def scan_once(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for project in list_projects():
            name = project["name"]
            try:
                result = sync_project_tree(name)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                results.append({"project": name, "error": str(exc)})
                continue

            if result.get("changed_file_count") or result.get("deleted_file_count"):
                results.append(result)
        self._last_results = results
        return results

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

    def _sync_project(self, project_name: str) -> None:
        result = sync_project_tree(project_name)
        self._record_result(result)

    def _run_once(self, projects: list[dict[str, Any]]) -> None:
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
                    matched = self._project_for_path(projects, event_path)
                    if matched is None:
                        for project in projects:
                            self._sync_project(project["name"])
                    else:
                        self._sync_project(matched["name"])
                    continue

                if process.poll() is not None:
                    break

                time.sleep(0.05)
        finally:
            self._terminate_process(process)
            self._process = None

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

    def _run(self) -> None:
        while not self._stop_event.is_set():
            projects = list_projects()
            if not projects:
                self._stop_event.wait(self.poll_interval)
                continue
            self._run_once(projects)
            if not self._stop_event.is_set():
                self._stop_event.wait(self.poll_interval)
