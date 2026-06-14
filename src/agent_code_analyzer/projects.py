from __future__ import annotations

import json
import os
import hashlib
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .parsing import analyze_file, detect_language

DATA_DIR = Path(os.environ.get("AGENT_CODE_ANALYZER_HOME", Path.home() / ".agent-code-analyzer"))
METADATA_DB = DATA_DIR / "metadata.sqlite3"
PROJECTS_DIR = DATA_DIR / "projects"
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "venv",
    "__pycache__",
}

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class ProjectRecord:
    name: str
    root_path: str
    db_path: str
    mode: str
    description: str
    created_at: str
    updated_at: str
    indexed_at: str | None = None
    file_count: int = 0
    supported_file_count: int = 0
    symbol_count: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    slug = slug.strip(".-_")
    return slug or "project"


def _project_db_path(name: str) -> Path:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return PROJECTS_DIR / f"{_slugify(name)}-{digest}" / "project.sqlite3"

def _db_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


@contextmanager
def _acquire_locks(*paths: Path) -> Iterator[None]:
    unique = sorted({str(path.resolve()): path.resolve() for path in paths}.values(), key=str)
    locks = [_db_lock(path) for path in unique]
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()


def _connect(db_path: Path) -> sqlite3.Connection:
    _ensure_storage()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _init_metadata_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            db_path TEXT NOT NULL,
            mode TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            indexed_at TEXT,
            file_count INTEGER NOT NULL DEFAULT 0,
            supported_file_count INTEGER NOT NULL DEFAULT 0,
            symbol_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path);
        CREATE INDEX IF NOT EXISTS idx_projects_description ON projects(description);
        CREATE INDEX IF NOT EXISTS idx_projects_mode ON projects(mode);
        """
    )


def _init_project_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_state (
            project_name TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            indexed_at TEXT,
            file_count INTEGER NOT NULL DEFAULT 0,
            supported_file_count INTEGER NOT NULL DEFAULT 0,
            symbol_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS files (
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
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            symbol_order INTEGER NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            depth INTEGER NOT NULL,
            start_row INTEGER NOT NULL,
            start_column INTEGER NOT NULL,
            end_row INTEGER NOT NULL,
            end_column INTEGER NOT NULL,
            signature TEXT NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_files_rel_path ON files(rel_path);
        CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
        CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        """
    )


def _normalize_project(project: str) -> str:
    return project.strip()


def _row_to_project_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "name": row["name"],
        "root_path": row["root_path"],
        "db_path": row["db_path"],
        "mode": row["mode"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "indexed_at": row["indexed_at"],
        "file_count": row["file_count"],
        "supported_file_count": row["supported_file_count"],
        "symbol_count": row["symbol_count"],
    }


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project": row["project_name"],
        "root_path": row["root_path"],
        "file_count": row["file_count"],
        "supported_file_count": row["supported_file_count"],
        "symbol_count": row["symbol_count"],
        "indexed_at": row["indexed_at"],
    }


def _symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature
        FROM symbols
        WHERE file_id = ?
        ORDER BY symbol_order ASC, id ASC
        """,
        (file_id,),
    ).fetchall()
    return [
        {
            "type": row["type"],
            "name": row["name"],
            "depth": row["depth"],
            "start_point": {"row": row["start_row"], "column": row["start_column"]},
            "end_point": {"row": row["end_row"], "column": row["end_column"]},
            "signature": row["signature"],
        }
        for row in rows
    ]


def _upsert_file_analysis(
    conn: sqlite3.Connection,
    *,
    project: str,
    root_path: Path,
    resolved_path: Path,
    analysis: dict[str, Any],
    indexed_at: str,
) -> None:
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    rel_path = str(resolved_path.relative_to(root_path))
    skeleton = analysis["skeleton"]
    byte_length = len(parsed.source_code.encode("utf-8"))

    conn.execute(
        """
        INSERT INTO files (
            rel_path, abs_path, language, root_type, node_count, has_error, byte_length, skeleton, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rel_path) DO UPDATE SET
            abs_path = excluded.abs_path,
            language = excluded.language,
            root_type = excluded.root_type,
            node_count = excluded.node_count,
            has_error = excluded.has_error,
            byte_length = excluded.byte_length,
            skeleton = excluded.skeleton,
            indexed_at = excluded.indexed_at
        """,
        (
            rel_path,
            str(resolved_path),
            parsed.language,
            root_node.type,
            root_node.descendant_count,
            int(root_node.has_error),
            byte_length,
            skeleton,
            indexed_at,
        ),
    )
    file_id = conn.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,)).fetchone()[0]
    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
    for order, symbol in enumerate(analysis["symbols"]):
        conn.execute(
            """
            INSERT INTO symbols (
                file_id, symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                order,
                symbol["type"],
                symbol["name"],
                symbol["depth"],
                symbol["start_point"]["row"],
                symbol["start_point"]["column"],
                symbol["end_point"]["row"],
                symbol["end_point"]["column"],
                symbol["signature"],
            ),
        )


def _load_project_metadata(project: str) -> dict[str, Any] | None:
    if not METADATA_DB.exists():
        return None
    with _connect(METADATA_DB) as conn:
        _init_metadata_schema(conn)
        row = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
        if row is None:
            return None
        return _row_to_project_dict(row)


def list_projects() -> list[dict[str, Any]]:
    if not METADATA_DB.exists():
        return []
    with _connect(METADATA_DB) as conn:
        _init_metadata_schema(conn)
        rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
        return [_row_to_project_dict(row) for row in rows]


def search_projects(query: str) -> list[dict[str, Any]]:
    needle = query.strip()
    if not needle:
        return list_projects()

    pattern = f"%{needle.lower()}%"
    if not METADATA_DB.exists():
        return []

    with _connect(METADATA_DB) as conn:
        _init_metadata_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE lower(name) LIKE ?
               OR lower(root_path) LIKE ?
               OR lower(mode) LIKE ?
               OR lower(description) LIKE ?
            ORDER BY name ASC
            """,
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [_row_to_project_dict(row) for row in rows]


def get_project(project: str) -> dict[str, Any]:
    project = _normalize_project(project)
    metadata = _load_project_metadata(project)
    if metadata is None:
        raise ValueError(f"Unknown project: {project}")
    return metadata


def add_project(project: str, root_path: str, mode: str = "file", description: str = "") -> dict[str, Any]:
    project = _normalize_project(project)
    mode = mode.strip().lower()
    if mode not in {"file", "directory"}:
        raise ValueError("mode must be 'file' or 'directory'")

    root = Path(root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")

    db_path = _project_db_path(project)
    now = _now()

    with _acquire_locks(METADATA_DB, db_path):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            existing = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
            created_at = existing["created_at"] if existing else now
            indexed_at = existing["indexed_at"] if existing else None
            file_count = int(existing["file_count"] if existing else 0)
            supported_file_count = int(existing["supported_file_count"] if existing else 0)
            symbol_count = int(existing["symbol_count"] if existing else 0)
            conn.execute(
                """
                INSERT INTO projects (
                    name, root_path, db_path, mode, description, created_at, updated_at,
                    indexed_at, file_count, supported_file_count, symbol_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    root_path = excluded.root_path,
                    db_path = excluded.db_path,
                    mode = excluded.mode,
                    description = excluded.description,
                    updated_at = excluded.updated_at,
                    indexed_at = COALESCE(projects.indexed_at, excluded.indexed_at),
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count
                """,
                (
                    project,
                    str(root),
                    str(db_path),
                    mode,
                    description.strip() or (existing["description"] if existing else ""),
                    created_at,
                    now,
                    indexed_at,
                    file_count,
                    supported_file_count,
                    symbol_count,
                ),
            )

        with _connect(db_path) as conn:
            _init_project_schema(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at
                """,
                (project, str(root), created_at, now, indexed_at, file_count, supported_file_count, symbol_count),
            )

    result = get_project(project)
    if mode == "directory":
        result["ingest"] = ingest_project_tree(project, refresh=True)
    return result


def resolve_project_path(project: str, file_path: str) -> Path:
    project_data = get_project(project)
    root = Path(project_data["root_path"]).resolve()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside project root: {file_path}") from exc

    if not candidate.exists():
        raise ValueError(f"File does not exist: {candidate}")
    return candidate


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") and path.suffix == "":
            continue
        if detect_language(str(path)):
            files.append(path)
    return sorted(files)


def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, Any]:
    project_data = get_project(project)
    root = Path(project_data["root_path"])
    db_path = Path(project_data["db_path"])
    indexed_at = _now()

    if not refresh:
        with _connect(db_path) as conn:
            _init_project_schema(conn)
            row = conn.execute(
                """
                SELECT project_name, root_path, file_count, supported_file_count, symbol_count, indexed_at
                FROM project_state
                WHERE project_name = ?
                """,
                (project,),
            ).fetchone()
            if row is not None:
                return _row_to_summary(row)

    with _db_lock(db_path):
        with _connect(db_path) as conn:
            _init_project_schema(conn)
            if refresh:
                conn.execute("DELETE FROM symbols")
                conn.execute("DELETE FROM files")

            files = _iter_source_files(root)
            total_symbols = 0
            for path in files:
                analysis = analyze_file(str(path))
                _upsert_file_analysis(
                    conn,
                    project=project,
                    root_path=root,
                    resolved_path=path,
                    analysis=analysis,
                    indexed_at=indexed_at,
                )
                total_symbols += len(analysis["symbols"])

            existing_state = conn.execute(
                "SELECT created_at FROM project_state WHERE project_name = ?",
                (project,),
            ).fetchone()
            created_at = existing_state["created_at"] if existing_state else indexed_at
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count
                """,
                (
                    project,
                    str(root),
                    created_at,
                    indexed_at,
                    indexed_at,
                    len(files),
                    len(files),
                    total_symbols,
                ),
            )

    with _acquire_locks(METADATA_DB):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, len(files), len(files), total_symbols, project),
            )

    return {
        "project": project,
        "root_path": str(root),
        "mode": project_data["mode"],
        "file_count": len(files),
        "supported_file_count": len(files),
        "symbol_count": total_symbols,
        "indexed_at": indexed_at,
    }


def _read_file_record(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT rel_path, abs_path, language, root_type, node_count, has_error, byte_length, skeleton, indexed_at
        FROM files
        WHERE id = ?
        """,
        (file_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Indexed file record disappeared")
    return {
        "path": row["rel_path"],
        "abs_path": row["abs_path"],
        "language": row["language"],
        "root_type": row["root_type"],
        "node_count": row["node_count"],
        "has_error": bool(row["has_error"]),
        "byte_length": row["byte_length"],
        "skeleton": row["skeleton"],
        "indexed_at": row["indexed_at"],
    }


def project_file_summary(project: str, file_path: str) -> dict[str, Any]:
    project_data = get_project(project)
    resolved = resolve_project_path(project, file_path)
    root = Path(project_data["root_path"]).resolve()
    db_path = Path(project_data["db_path"])
    rel_path = str(resolved.relative_to(root))

    analysis = analyze_file(str(resolved))
    indexed_at = _now()

    with _db_lock(db_path):
        with _connect(db_path) as conn:
            _init_project_schema(conn)
            _upsert_file_analysis(
                conn,
                project=project,
                root_path=root,
                resolved_path=resolved,
                analysis=analysis,
                indexed_at=indexed_at,
            )
            file_row = conn.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,)).fetchone()
            if file_row is None:
                raise ValueError("Failed to persist file analysis")
            file_id = int(file_row[0])
            file_data = _read_file_record(conn, file_id)
            symbols = _symbol_rows(conn, file_id)
            file_count = conn.execute("SELECT COUNT(*) AS count FROM files").fetchone()["count"]
            symbol_count = conn.execute("SELECT COUNT(*) AS count FROM symbols").fetchone()["count"]
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count
                """,
                (
                    project,
                    str(root),
                    indexed_at,
                    indexed_at,
                    indexed_at,
                    int(file_count),
                    int(file_count),
                    int(symbol_count),
                ),
            )

    with _acquire_locks(METADATA_DB):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, int(file_count), int(file_count), int(symbol_count), project),
            )

    return {
        "project": project,
        "file_path": file_data["path"],
        "supported": True,
        "language": file_data["language"],
        "root_type": file_data["root_type"],
        "node_count": file_data["node_count"],
        "has_error": file_data["has_error"],
        "byte_length": file_data["byte_length"],
        "skeleton": file_data["skeleton"],
        "symbols": symbols,
        "indexed_at": file_data["indexed_at"],
    }
