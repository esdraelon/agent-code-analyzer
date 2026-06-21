from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from . import project_storage as storage
from .project_row_mapper import ProjectRowMapper

LOGGER = logging.getLogger(__name__)

INGESTION_STATUSES = ("queued", "running", "recovering", "completed", "failed")


@dataclass(frozen=True)
class IngestionCheckpoint:
    project_name: str
    root_path: str
    mode: str
    phase: str
    status: str
    queued_at: str
    started_at: str | None
    updated_at: str
    completed_at: str | None
    last_file_path: str | None
    last_file_mtime_ns: int | None
    last_file_content_hash: str
    total_file_count: int
    processed_file_count: int
    error_state: str

    @property
    def is_active(self) -> bool:
        return self.completed_at is None and self.status in {"queued", "running", "recovering"}

    def with_updates(self, **changes: Any) -> "IngestionCheckpoint":
        return replace(self, **changes)


def ensure_ingestion_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
            project_name TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            mode TEXT NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            last_file_path TEXT,
            last_file_mtime_ns INTEGER,
            last_file_content_hash TEXT NOT NULL DEFAULT '',
            total_file_count INTEGER NOT NULL DEFAULT 0,
            processed_file_count INTEGER NOT NULL DEFAULT 0,
            error_state TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_status ON ingestion_checkpoints(status);
        CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_updated_at ON ingestion_checkpoints(updated_at);
        """
    )


def _row_to_checkpoint(row: sqlite3.Row) -> IngestionCheckpoint:
    return IngestionCheckpoint(
        project_name=row["project_name"],
        root_path=row["root_path"],
        mode=row["mode"],
        phase=row["phase"],
        status=row["status"],
        queued_at=row["queued_at"],
        started_at=row["started_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        last_file_path=row["last_file_path"],
        last_file_mtime_ns=row["last_file_mtime_ns"],
        last_file_content_hash=row["last_file_content_hash"] or "",
        total_file_count=int(row["total_file_count"]),
        processed_file_count=int(row["processed_file_count"]),
        error_state=row["error_state"] or "",
    )


def _checkpoint_from_db(conn: sqlite3.Connection, project_name: str) -> IngestionCheckpoint | None:
    row = conn.execute(
        "SELECT * FROM ingestion_checkpoints WHERE project_name = ?",
        (project_name,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_checkpoint(row)


def load_ingestion_checkpoint(db_path: Path, project_name: str) -> IngestionCheckpoint | None:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            ensure_ingestion_schema(conn)
            return _checkpoint_from_db(conn, project_name)


def load_active_ingestion_checkpoints(db_path: Path) -> list[IngestionCheckpoint]:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            ensure_ingestion_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM ingestion_checkpoints
                WHERE completed_at IS NULL
                ORDER BY updated_at ASC, project_name ASC
                """
            ).fetchall()
            return [_row_to_checkpoint(row) for row in rows]


def _store_checkpoint(db_path: Path, checkpoint: IngestionCheckpoint) -> IngestionCheckpoint:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            return write_ingestion_checkpoint(conn, checkpoint)


def write_ingestion_checkpoint(conn: sqlite3.Connection, checkpoint: IngestionCheckpoint) -> IngestionCheckpoint:
    ensure_ingestion_schema(conn)
    conn.execute(
        """
        INSERT INTO ingestion_checkpoints (
            project_name, root_path, mode, phase, status, queued_at, started_at, updated_at,
            completed_at, last_file_path, last_file_mtime_ns, last_file_content_hash,
            total_file_count, processed_file_count, error_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_name) DO UPDATE SET
            root_path = excluded.root_path,
            mode = excluded.mode,
            phase = excluded.phase,
            status = excluded.status,
            queued_at = excluded.queued_at,
            started_at = excluded.started_at,
            updated_at = excluded.updated_at,
            completed_at = excluded.completed_at,
            last_file_path = excluded.last_file_path,
            last_file_mtime_ns = excluded.last_file_mtime_ns,
            last_file_content_hash = excluded.last_file_content_hash,
            total_file_count = excluded.total_file_count,
            processed_file_count = excluded.processed_file_count,
            error_state = excluded.error_state
        """,
        (
            checkpoint.project_name,
            checkpoint.root_path,
            checkpoint.mode,
            checkpoint.phase,
            checkpoint.status,
            checkpoint.queued_at,
            checkpoint.started_at,
            checkpoint.updated_at,
            checkpoint.completed_at,
            checkpoint.last_file_path,
            checkpoint.last_file_mtime_ns,
            checkpoint.last_file_content_hash,
            checkpoint.total_file_count,
            checkpoint.processed_file_count,
            checkpoint.error_state,
        ),
    )
    return checkpoint


def begin_ingestion_checkpoint(
    db_path: Path,
    *,
    project: str,
    root_path: Path | str,
    mode: str,
    phase: str,
    total_file_count: int,
) -> IngestionCheckpoint:
    now = storage._now()
    checkpoint = IngestionCheckpoint(
        project_name=project,
        root_path=str(root_path),
        mode=mode,
        phase=phase,
        status="running",
        queued_at=now,
        started_at=now,
        updated_at=now,
        completed_at=None,
        last_file_path=None,
        last_file_mtime_ns=None,
        last_file_content_hash="",
        total_file_count=total_file_count,
        processed_file_count=0,
        error_state="",
    )
    return _store_checkpoint(db_path, checkpoint)


def update_ingestion_checkpoint(
    db_path: Path,
    *,
    project: str,
    phase: str | None = None,
    status: str | None = None,
    total_file_count: int | None = None,
    processed_file_count: int | None = None,
    last_file_path: str | None = None,
    last_file_mtime_ns: int | None = None,
    last_file_content_hash: str | None = None,
    error_state: str | None = None,
) -> IngestionCheckpoint:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            ensure_ingestion_schema(conn)
            current = _checkpoint_from_db(conn, project)
            if current is None:
                raise ValueError(f"No ingestion checkpoint exists for project: {project}")
    checkpoint = current.with_updates(
        phase=phase if phase is not None else current.phase,
        status=status if status is not None else current.status,
        total_file_count=total_file_count if total_file_count is not None else current.total_file_count,
        processed_file_count=processed_file_count if processed_file_count is not None else current.processed_file_count,
        last_file_path=last_file_path if last_file_path is not None else current.last_file_path,
        last_file_mtime_ns=last_file_mtime_ns if last_file_mtime_ns is not None else current.last_file_mtime_ns,
        last_file_content_hash=last_file_content_hash if last_file_content_hash is not None else current.last_file_content_hash,
        error_state=error_state if error_state is not None else current.error_state,
        updated_at=storage._now(),
    )
    if checkpoint.status == "completed" and checkpoint.completed_at is None:
        checkpoint = checkpoint.with_updates(completed_at=checkpoint.updated_at)
    return _store_checkpoint(db_path, checkpoint)


def complete_ingestion_checkpoint(
    db_path: Path,
    *,
    project: str,
    phase: str = "completed",
) -> IngestionCheckpoint:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            ensure_ingestion_schema(conn)
            current = _checkpoint_from_db(conn, project)
            if current is None:
                raise ValueError(f"No ingestion checkpoint exists for project: {project}")
    now = storage._now()
    checkpoint = current.with_updates(
        phase=phase,
        status="completed",
        completed_at=now,
        updated_at=now,
    )
    return _store_checkpoint(db_path, checkpoint)


def fail_ingestion_checkpoint(
    db_path: Path,
    *,
    project: str,
    error_state: str,
    phase: str = "failed",
) -> IngestionCheckpoint:
    with storage._acquire_locks(db_path):
        with storage._connect(db_path) as conn:
            ensure_ingestion_schema(conn)
            current = _checkpoint_from_db(conn, project)
            if current is None:
                raise ValueError(f"No ingestion checkpoint exists for project: {project}")
    now = storage._now()
    checkpoint = current.with_updates(
        phase=phase,
        status="failed",
        updated_at=now,
        completed_at=current.completed_at,
        error_state=error_state,
    )
    return _store_checkpoint(db_path, checkpoint)


def recover_incomplete_ingestion(
    project_records: list[dict[str, Any]] | None = None,
    sync_callback: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if project_records is None:
        from .projects import list_projects

        project_records = list_projects()
    if sync_callback is None:
        from .projects import sync_project_tree

        sync_callback = sync_project_tree

    recovered: list[dict[str, Any]] = []
    for project in project_records:
        project_name = str(project["name"])
        db_path = Path(project["db_path"])
        checkpoint = load_ingestion_checkpoint(db_path, project_name)
        if checkpoint is None or not checkpoint.is_active:
            continue

        LOGGER.info(
            "recovering_ingestion project=%s mode=%s phase=%s processed=%s/%s",
            project_name,
            checkpoint.mode,
            checkpoint.phase,
            checkpoint.processed_file_count,
            checkpoint.total_file_count,
        )
        update_ingestion_checkpoint(
            db_path,
            project=project_name,
            phase="recovering",
            status="recovering",
        )
        try:
            result = sync_callback(project_name)
        except Exception as exc:
            fail_ingestion_checkpoint(db_path, project=project_name, error_state=str(exc))
            recovered.append({"project": project_name, "error": str(exc)})
            continue

        complete_ingestion_checkpoint(db_path, project=project_name)
        recovered.append(result)

    return recovered


def checkpoint_summary(checkpoint: IngestionCheckpoint) -> dict[str, Any]:
    return {
        "project": checkpoint.project_name,
        "root_path": checkpoint.root_path,
        "mode": checkpoint.mode,
        "phase": checkpoint.phase,
        "status": checkpoint.status,
        "queued_at": checkpoint.queued_at,
        "started_at": checkpoint.started_at,
        "updated_at": checkpoint.updated_at,
        "completed_at": checkpoint.completed_at,
        "last_file_path": checkpoint.last_file_path,
        "last_file_mtime_ns": checkpoint.last_file_mtime_ns,
        "last_file_content_hash": checkpoint.last_file_content_hash,
        "total_file_count": checkpoint.total_file_count,
        "processed_file_count": checkpoint.processed_file_count,
        "error_state": checkpoint.error_state,
        "is_active": checkpoint.is_active,
    }


def encode_project_languages(languages: list[str]) -> str:
    return ProjectRowMapper.encode_languages(languages)
