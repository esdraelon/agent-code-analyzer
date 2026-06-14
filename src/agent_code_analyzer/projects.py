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


class ProjectRowMapper:
    """Map sqlite rows and language metadata into plain project dictionaries."""

    @staticmethod
    def decode_languages(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, str):
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                return [value] if value else []
            if isinstance(raw, list):
                return [str(item) for item in raw if str(item)]
        return []

    @staticmethod
    def encode_languages(languages: list[str]) -> str:
        return json.dumps(ProjectRowMapper.merge_languages([str(language) for language in languages if str(language)]))

    @staticmethod
    def row_languages(row: sqlite3.Row) -> list[str]:
        return ProjectRowMapper.decode_languages(row["languages"])

    @staticmethod
    def merge_languages(*groups: list[str]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for language in group:
                if language and language not in merged:
                    merged.append(language)
        return merged

    @staticmethod
    def row_to_project_dict(row: sqlite3.Row) -> dict[str, Any]:
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
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
        }

    @staticmethod
    def row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "project": row["project_name"],
            "root_path": row["root_path"],
            "file_count": row["file_count"],
            "supported_file_count": row["supported_file_count"],
            "symbol_count": row["symbol_count"],
            "indexed_at": row["indexed_at"],
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
        }

    @staticmethod
    def project_languages_from_conn(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute("SELECT languages FROM files ORDER BY id ASC").fetchall()
        return ProjectRowMapper.merge_languages(*[ProjectRowMapper.decode_languages(row["languages"]) for row in rows])

    @staticmethod
    def symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature, languages
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
                "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
            }
            for row in rows
        ]

    @staticmethod
    def file_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "path": row["rel_path"],
            "abs_path": row["abs_path"],
            "language": row["language"],
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
            "root_type": row["root_type"],
            "node_count": row["node_count"],
            "has_error": bool(row["has_error"]),
            "byte_length": row["byte_length"],
            "file_size": row["file_size"],
            "file_mtime_ns": row["file_mtime_ns"],
            "skeleton": row["skeleton"],
            "indexed_at": row["indexed_at"],
        }


class ProjectRepository:
    """Repository-style helpers for sqlite-backed project persistence."""

    @staticmethod
    def connect(db_path: Path) -> sqlite3.Connection:
        _ensure_storage()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def init_metadata_schema(conn: sqlite3.Connection) -> None:
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

    @staticmethod
    def init_project_schema(conn: sqlite3.Connection) -> None:
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
                node_count INTEGER NOT NULL,
                has_error INTEGER NOT NULL,
                byte_length INTEGER NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                file_mtime_ns INTEGER NOT NULL DEFAULT 0,
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

    @staticmethod
    def ensure_project_schema(conn: sqlite3.Connection) -> None:
        ProjectRepository.init_project_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        if "file_size" not in columns:
            conn.execute("ALTER TABLE files ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
        if "file_mtime_ns" not in columns:
            conn.execute("ALTER TABLE files ADD COLUMN file_mtime_ns INTEGER NOT NULL DEFAULT 0")
        if "languages" not in columns:
            conn.execute("ALTER TABLE files ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")

        symbol_columns = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
        if "languages" not in symbol_columns:
            conn.execute("ALTER TABLE symbols ADD COLUMN languages TEXT NOT NULL DEFAULT '[]'")

    @staticmethod
    def load_project_metadata(project: str) -> dict[str, Any] | None:
        if not METADATA_DB.exists():
            return None
        with ProjectRepository.connect(METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            row = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
            if row is None:
                return None
            return ProjectRowMapper.row_to_project_dict(row)

    @staticmethod
    def list_projects() -> list[dict[str, Any]]:
        if not METADATA_DB.exists():
            return []
        with ProjectRepository.connect(METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
            return [ProjectRowMapper.row_to_project_dict(row) for row in rows]

    @staticmethod
    def search_projects(query: str) -> list[dict[str, Any]]:
        needle = query.strip()
        if not needle:
            return ProjectRepository.list_projects()

        pattern = f"%{needle.lower()}%"
        if not METADATA_DB.exists():
            return []

        with ProjectRepository.connect(METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
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
            return [ProjectRowMapper.row_to_project_dict(row) for row in rows]

    @staticmethod
    def write_project_summary(
        *,
        project: str,
        root: Path,
        mode: str,
        created_at: str,
        updated_at: str,
        indexed_at: str,
        file_count: int,
        supported_file_count: int,
        symbol_count: int,
        languages: list[str],
    ) -> None:
        encoded_languages = ProjectRowMapper.encode_languages(languages)
        with ProjectRepository.connect(METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                INSERT INTO projects (
                    name, root_path, db_path, mode, description, created_at, updated_at,
                    indexed_at, file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    root_path = excluded.root_path,
                    db_path = excluded.db_path,
                    mode = excluded.mode,
                    description = excluded.description,
                    updated_at = excluded.updated_at,
                    indexed_at = COALESCE(projects.indexed_at, excluded.indexed_at),
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
                """,
                (
                    project,
                    str(root),
                    str(_project_db_path(project)),
                    mode,
                    "",
                    created_at,
                    updated_at,
                    indexed_at,
                    file_count,
                    supported_file_count,
                    symbol_count,
                    encoded_languages,
                ),
            )

    @staticmethod
    def write_project_state(
        *,
        project: str,
        root: Path,
        created_at: str,
        updated_at: str,
        indexed_at: str,
        file_count: int,
        supported_file_count: int,
        symbol_count: int,
        languages: list[str],
    ) -> None:
        encoded_languages = ProjectRowMapper.encode_languages(languages)
        db_path = _project_db_path(project)
        with ProjectRepository.connect(db_path) as conn:
            ProjectRepository.ensure_project_schema(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
                """,
                (project, str(root), created_at, updated_at, indexed_at, file_count, supported_file_count, symbol_count, encoded_languages),
            )

    @staticmethod
    def update_project_metadata(
        *,
        project: str,
        indexed_at: str,
        file_count: int,
        supported_file_count: int,
        symbol_count: int,
        languages: list[str],
        updated_at: str | None = None,
    ) -> None:
        encoded_languages = ProjectRowMapper.encode_languages(languages)
        with ProjectRepository.connect(METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, updated_at or indexed_at, file_count, supported_file_count, symbol_count, encoded_languages, project),
            )

    @staticmethod
    def update_project_state(
        *,
        project: str,
        root: Path,
        created_at: str,
        updated_at: str,
        indexed_at: str,
        file_count: int,
        supported_file_count: int,
        symbol_count: int,
        languages: list[str],
    ) -> None:
        ProjectRepository.write_project_state(
            project=project,
            root=root,
            created_at=created_at,
            updated_at=updated_at,
            indexed_at=indexed_at,
            file_count=file_count,
            supported_file_count=supported_file_count,
            symbol_count=symbol_count,
            languages=languages,
        )

    @staticmethod
    def project_languages_from_conn(conn: sqlite3.Connection) -> list[str]:
        return ProjectRowMapper.project_languages_from_conn(conn)

    @staticmethod
    def symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
        return ProjectRowMapper.symbol_rows(conn, file_id)

    @staticmethod
    def read_file_record(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT rel_path, abs_path, language, languages, root_type, node_count, has_error, byte_length, file_size, file_mtime_ns, skeleton, indexed_at
            FROM files
            WHERE id = ?
            """,
            (file_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Indexed file record disappeared")
        return ProjectRowMapper.file_record(row)



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
    return ProjectRepository.connect(db_path)


def _init_metadata_schema(conn: sqlite3.Connection) -> None:
    ProjectRepository.init_metadata_schema(conn)




def _init_project_schema(conn: sqlite3.Connection) -> None:
    ProjectRepository.init_project_schema(conn)


def _ensure_project_schema(conn: sqlite3.Connection) -> None:
    ProjectRepository.ensure_project_schema(conn)


def _project_file_snapshot(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"file_size": int(stat.st_size), "file_mtime_ns": int(stat.st_mtime_ns)}


def _normalize_project(project: str) -> str:
    return project.strip()


def _row_to_project_dict(row: sqlite3.Row) -> dict[str, Any]:
    return ProjectRowMapper.row_to_project_dict(row)


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    return ProjectRowMapper.row_to_summary(row)


def _decode_languages(value: Any) -> list[str]:
    return ProjectRowMapper.decode_languages(value)


def _encode_languages(languages: list[str]) -> str:
    return ProjectRowMapper.encode_languages(languages)


def _row_languages(row: sqlite3.Row) -> list[str]:
    return ProjectRowMapper.row_languages(row)


def _merge_languages(*groups: list[str]) -> list[str]:
    return ProjectRowMapper.merge_languages(*groups)


def _project_languages_from_conn(conn: sqlite3.Connection) -> list[str]:
    return ProjectRowMapper.project_languages_from_conn(conn)


def _symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    return ProjectRowMapper.symbol_rows(conn, file_id)


def _upsert_file_analysis(
    conn: sqlite3.Connection,
    *,
    project: str,
    root_path: Path,
    resolved_path: Path,
    analysis: dict[str, Any],
    indexed_at: str,
    file_size: int,
    file_mtime_ns: int,
) -> None:
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    rel_path = str(resolved_path.relative_to(root_path))
    skeleton = analysis["skeleton"]
    byte_length = len(parsed.source_code.encode("utf-8"))
    languages = _encode_languages(analysis.get("languages", [parsed.language]))

    conn.execute(
        """
        INSERT INTO files (
            rel_path, abs_path, language, languages, root_type, node_count, has_error, byte_length, file_size, file_mtime_ns, skeleton, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rel_path) DO UPDATE SET
            abs_path = excluded.abs_path,
            language = excluded.language,
            languages = excluded.languages,
            root_type = excluded.root_type,
            node_count = excluded.node_count,
            has_error = excluded.has_error,
            byte_length = excluded.byte_length,
            file_size = excluded.file_size,
            file_mtime_ns = excluded.file_mtime_ns,
            skeleton = excluded.skeleton,
            indexed_at = excluded.indexed_at
        """,
        (
            rel_path,
            str(resolved_path),
            parsed.language,
            languages,
            root_node.type,
            root_node.descendant_count,
            int(root_node.has_error),
            byte_length,
            file_size,
            file_mtime_ns,
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
                file_id, symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature, languages
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                _encode_languages(symbol.get("languages", [parsed.language])),
            ),
        )


def _load_project_metadata(project: str) -> dict[str, Any] | None:
    return ProjectRepository.load_project_metadata(project)


def list_projects() -> list[dict[str, Any]]:
    return ProjectRepository.list_projects()


def search_projects(query: str) -> list[dict[str, Any]]:
    return ProjectRepository.search_projects(query)


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
    project_languages: list[str] = []

    with _acquire_locks(METADATA_DB, db_path):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            existing = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
            created_at = existing["created_at"] if existing else now
            indexed_at = existing["indexed_at"] if existing else None
            file_count = int(existing["file_count"] if existing else 0)
            supported_file_count = int(existing["supported_file_count"] if existing else 0)
            symbol_count = int(existing["symbol_count"] if existing else 0)
            languages = _encode_languages(_decode_languages(existing["languages"]) if existing and "languages" in existing.keys() else [])
            conn.execute(
                """
                INSERT INTO projects (
                    name, root_path, db_path, mode, description, created_at, updated_at,
                    indexed_at, file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    root_path = excluded.root_path,
                    db_path = excluded.db_path,
                    mode = excluded.mode,
                    description = excluded.description,
                    updated_at = excluded.updated_at,
                    indexed_at = COALESCE(projects.indexed_at, excluded.indexed_at),
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
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
                    languages,
                ),
            )

        with _connect(db_path) as conn:
            _ensure_project_schema(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    languages = excluded.languages
                """,
                (project, str(root), created_at, now, indexed_at, file_count, supported_file_count, symbol_count, languages),
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
            _ensure_project_schema(conn)
            row = conn.execute(
                """
                SELECT project_name, root_path, file_count, supported_file_count, symbol_count, indexed_at, languages
                FROM project_state
                WHERE project_name = ?
                """,
                (project,),
            ).fetchone()
            if row is not None:
                return _row_to_summary(row)

    with _db_lock(db_path):
        with _connect(db_path) as conn:
            _ensure_project_schema(conn)
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
                    **_project_file_snapshot(path),
                )
                total_symbols += len(analysis["symbols"])

            existing_state = conn.execute(
                "SELECT created_at FROM project_state WHERE project_name = ?",
                (project,),
            ).fetchone()
            created_at = existing_state["created_at"] if existing_state else indexed_at
            project_languages = _project_languages_from_conn(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
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
                    _encode_languages(project_languages),
                ),
            )

    with _acquire_locks(METADATA_DB):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, len(files), len(files), total_symbols, _encode_languages(project_languages), project),
            )

    return {
        "project": project,
        "root_path": str(root),
        "mode": project_data["mode"],
        "file_count": len(files),
        "supported_file_count": len(files),
        "symbol_count": total_symbols,
        "indexed_at": indexed_at,
        "languages": project_languages,
    }


def sync_project_tree(project: str) -> dict[str, Any]:
    project_data = get_project(project)
    root = Path(project_data["root_path"]).resolve()
    db_path = Path(project_data["db_path"])
    now = _now()

    with _db_lock(db_path):
        with _connect(db_path) as conn:
            _ensure_project_schema(conn)
            existing_state = conn.execute(
                """
                SELECT project_name, root_path, created_at, updated_at, indexed_at, file_count, supported_file_count, symbol_count, languages
                FROM project_state
                WHERE project_name = ?
                """,
                (project,),
            ).fetchone()
            existing_files = {
                row["rel_path"]: row
                for row in conn.execute(
                    """
                    SELECT id, rel_path, abs_path, file_size, file_mtime_ns
                    FROM files
                    """
                ).fetchall()
            }

            current_files: dict[str, Path] = {}
            current_stats: dict[str, dict[str, int]] = {}
            for path in _iter_source_files(root):
                rel_path = str(path.relative_to(root))
                current_files[rel_path] = path
                current_stats[rel_path] = _project_file_snapshot(path)

            current_paths = set(current_files)
            existing_paths = set(existing_files)
            deleted_paths = sorted(existing_paths - current_paths)
            upserted_paths: list[str] = []
            unchanged_paths: list[str] = []

            for rel_path in sorted(current_paths):
                path = current_files[rel_path]
                snapshot = current_stats[rel_path]
                existing_row = existing_files.get(rel_path)
                if (
                    existing_row is not None
                    and int(existing_row["file_size"]) == snapshot["file_size"]
                    and int(existing_row["file_mtime_ns"]) == snapshot["file_mtime_ns"]
                ):
                    unchanged_paths.append(rel_path)
                    continue

                analysis = analyze_file(str(path))
                _upsert_file_analysis(
                    conn,
                    project=project,
                    root_path=root,
                    resolved_path=path,
                    analysis=analysis,
                    indexed_at=now,
                    **snapshot,
                )
                upserted_paths.append(rel_path)

            deleted_file_count = 0
            for rel_path in deleted_paths:
                row = existing_files[rel_path]
                conn.execute("DELETE FROM files WHERE id = ?", (int(row["id"]),))
                deleted_file_count += 1

            if not upserted_paths and deleted_file_count == 0 and existing_state is not None:
                return {
                    "project": project,
                    "root_path": str(root),
                    "mode": project_data["mode"],
                    "file_count": int(existing_state["file_count"]),
                    "supported_file_count": int(existing_state["supported_file_count"]),
                    "symbol_count": int(existing_state["symbol_count"]),
                    "indexed_at": existing_state["indexed_at"],
                    "changed_file_count": 0,
                    "deleted_file_count": 0,
                    "unchanged_file_count": len(unchanged_paths),
                }

            file_count = int(conn.execute("SELECT COUNT(*) AS count FROM files").fetchone()["count"])
            symbol_count = int(conn.execute("SELECT COUNT(*) AS count FROM symbols").fetchone()["count"])
            indexed_at = now
            created_at = existing_state["created_at"] if existing_state else now
            project_languages = _project_languages_from_conn(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
                """,
                (
                    project,
                    str(root),
                    created_at,
                    indexed_at,
                    indexed_at,
                    file_count,
                    file_count,
                    symbol_count,
                    _encode_languages(project_languages),
                ),
            )

    with _acquire_locks(METADATA_DB):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, file_count, file_count, symbol_count, _encode_languages(project_languages), project),
            )

    return {
        "project": project,
        "root_path": str(root),
        "mode": project_data["mode"],
        "file_count": file_count,
        "supported_file_count": file_count,
        "symbol_count": symbol_count,
        "indexed_at": indexed_at,
        "languages": project_languages,
        "changed_file_count": len(upserted_paths),
        "deleted_file_count": deleted_file_count,
        "unchanged_file_count": len(unchanged_paths),
    }


def _read_file_record(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
    return ProjectRepository.read_file_record(conn, file_id)


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
            _ensure_project_schema(conn)
            _upsert_file_analysis(
                conn,
                project=project,
                root_path=root,
                resolved_path=resolved,
                analysis=analysis,
                indexed_at=indexed_at,
                **_project_file_snapshot(resolved),
            )
            file_row = conn.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,)).fetchone()
            if file_row is None:
                raise ValueError("Failed to persist file analysis")
            file_id = int(file_row[0])
            file_data = _read_file_record(conn, file_id)
            symbols = _symbol_rows(conn, file_id)
            file_count = conn.execute("SELECT COUNT(*) AS count FROM files").fetchone()["count"]
            symbol_count = conn.execute("SELECT COUNT(*) AS count FROM symbols").fetchone()["count"]
            project_languages = _project_languages_from_conn(conn)
            conn.execute(
                """
                INSERT INTO project_state (
                    project_name, root_path, created_at, updated_at, indexed_at,
                    file_count, supported_file_count, symbol_count, languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at,
                    file_count = excluded.file_count,
                    supported_file_count = excluded.supported_file_count,
                    symbol_count = excluded.symbol_count,
                    languages = excluded.languages
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
                    _encode_languages(project_languages),
                ),
            )

    with _acquire_locks(METADATA_DB):
        with _connect(METADATA_DB) as conn:
            _init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, int(file_count), int(file_count), int(symbol_count), _encode_languages(project_languages), project),
            )

    return {
        "project": project,
        "file_path": file_data["path"],
        "supported": True,
        "language": file_data["language"],
        "languages": file_data["languages"],
        "root_type": file_data["root_type"],
        "node_count": file_data["node_count"],
        "has_error": file_data["has_error"],
        "byte_length": file_data["byte_length"],
        "skeleton": file_data["skeleton"],
        "symbols": symbols,
        "symbol_health": analysis["symbol_health"],
        "indexed_at": file_data["indexed_at"],
    }
