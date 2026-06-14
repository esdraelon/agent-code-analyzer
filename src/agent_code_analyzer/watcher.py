from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .projects import list_projects, sync_project_tree


@dataclass
class ProjectWatcherService:
    """Background polling watcher that keeps configured projects in sync."""

    poll_interval: float = 2.0
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _last_results: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def start(self) -> "ProjectWatcherService":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="agent-code-analyzer-watcher", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._thread = None

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

    def _run(self) -> None:
        self.scan_once()
        while not self._stop_event.wait(self.poll_interval):
            self.scan_once()
