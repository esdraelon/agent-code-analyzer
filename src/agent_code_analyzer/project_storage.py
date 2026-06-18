from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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


def _now() -> str:
    from datetime import datetime, timezone

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


def _project_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            symbol_count INTEGER NOT NULL DEFAULT 0,
            languages TEXT NOT NULL DEFAULT '[]'
        );

        CREATE INDEX IF NOT EXISTS idx_projects_root_path ON projects(root_path);
        CREATE INDEX IF NOT EXISTS idx_projects_description ON projects(description);
        CREATE INDEX IF NOT EXISTS idx_projects_mode ON projects(mode);
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "languages" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")


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
            symbol_count INTEGER NOT NULL DEFAULT 0,
            languages TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL UNIQUE,
            abs_path TEXT NOT NULL,
            language TEXT NOT NULL,
            languages TEXT NOT NULL DEFAULT '[]',
            root_type TEXT NOT NULL,
            root_start_row INTEGER NOT NULL DEFAULT 0,
            root_start_column INTEGER NOT NULL DEFAULT 0,
            root_end_row INTEGER NOT NULL DEFAULT 0,
            root_end_column INTEGER NOT NULL DEFAULT 0,
            node_count INTEGER NOT NULL,
            has_error INTEGER NOT NULL,
            byte_length INTEGER NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            file_mtime_ns INTEGER NOT NULL DEFAULT 0,
            file_content_hash TEXT NOT NULL DEFAULT '',
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
            languages TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_files_rel_path ON files(rel_path);
        CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
        CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(project_state)").fetchall()}
    if "languages" not in columns:
        conn.execute("ALTER TABLE project_state ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")


def _ensure_project_schema(conn: sqlite3.Connection) -> None:
    _init_project_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    if "file_size" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
    if "file_mtime_ns" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN file_mtime_ns INTEGER NOT NULL DEFAULT 0")
    if "file_content_hash" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN file_content_hash TEXT NOT NULL DEFAULT ''")
    if "languages" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")
    if "root_start_row" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN root_start_row INTEGER NOT NULL DEFAULT 0")
    if "root_start_column" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN root_start_column INTEGER NOT NULL DEFAULT 0")
    if "root_end_row" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN root_end_row INTEGER NOT NULL DEFAULT 0")
    if "root_end_column" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN root_end_column INTEGER NOT NULL DEFAULT 0")

    symbol_columns = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    if "languages" not in symbol_columns:
        conn.execute("ALTER TABLE symbols ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")


def _project_file_snapshot(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "file_size": int(stat.st_size),
        "file_mtime_ns": int(stat.st_mtime_ns),
        "file_content_hash": _project_file_hash(path),
    }


def _normalize_project(project: str) -> str:
    return project.strip()
