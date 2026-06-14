from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import project_storage as _storage
from .project_models import ProjectRecord as _ProjectRecord
from .parsing import analyze_file, detect_language
from .project_repository import ProjectRepository as _ProjectRepository
from .project_row_mapper import ProjectRowMapper as _ProjectRowMapper
from .project_service import (
    _iter_source_files as _iter_source_files_impl,
    _load_project_metadata as _load_project_metadata_impl,
    _read_file_record as _read_file_record_impl,
    _upsert_file_analysis as _upsert_file_analysis_impl,
    add_project as _add_project_impl,
    get_project as _get_project_impl,
    ingest_project_tree as _ingest_project_tree_impl,
    list_projects as _list_projects_impl,
    project_file_summary as _project_file_summary_impl,
    resolve_project_path as _resolve_project_path_impl,
    search_projects as _search_projects_impl,
    sync_project_tree as _sync_project_tree_impl,
)

DATA_DIR = _storage.DATA_DIR
METADATA_DB = _storage.METADATA_DB
PROJECTS_DIR = _storage.PROJECTS_DIR
IGNORED_DIRS = _storage.IGNORED_DIRS


def _sync_storage() -> None:
    _storage.DATA_DIR = DATA_DIR
    _storage.METADATA_DB = METADATA_DB
    _storage.PROJECTS_DIR = PROJECTS_DIR
    _storage.IGNORED_DIRS = IGNORED_DIRS


# Direct re-exports for class-specific modules.
ProjectRecord = _ProjectRecord
ProjectRowMapper = _ProjectRowMapper
ProjectRepository = _ProjectRepository


def _now() -> str:
    _sync_storage()
    return _storage._now()


def _ensure_storage() -> None:
    _sync_storage()
    _storage._ensure_storage()


def _slugify(value: str) -> str:
    _sync_storage()
    return _storage._slugify(value)


def _project_db_path(name: str) -> Path:
    _sync_storage()
    return _storage._project_db_path(name)


def _db_lock(path: Path):
    _sync_storage()
    return _storage._db_lock(path)


def _acquire_locks(*paths: Path) -> Any:
    _sync_storage()
    return _storage._acquire_locks(*paths)


def _connect(db_path: Path) -> sqlite3.Connection:
    _sync_storage()
    return _storage._connect(db_path)


def _init_metadata_schema(conn: sqlite3.Connection) -> None:
    _sync_storage()
    _storage._init_metadata_schema(conn)


def _init_project_schema(conn: sqlite3.Connection) -> None:
    _sync_storage()
    _storage._init_project_schema(conn)


def _ensure_project_schema(conn: sqlite3.Connection) -> None:
    _sync_storage()
    _storage._ensure_project_schema(conn)


def _project_file_snapshot(path: Path) -> dict[str, int]:
    _sync_storage()
    return _storage._project_file_snapshot(path)


def _normalize_project(project: str) -> str:
    _sync_storage()
    return _storage._normalize_project(project)


def _row_to_project_dict(row: sqlite3.Row) -> dict[str, Any]:
    return _ProjectRowMapper.row_to_project_dict(row)


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    return _ProjectRowMapper.row_to_summary(row)


def _decode_languages(value: Any) -> list[str]:
    return _ProjectRowMapper.decode_languages(value)


def _encode_languages(languages: list[str]) -> str:
    return _ProjectRowMapper.encode_languages(languages)


def _row_languages(row: sqlite3.Row) -> list[str]:
    return _ProjectRowMapper.row_languages(row)


def _merge_languages(*groups: list[str]) -> list[str]:
    return _ProjectRowMapper.merge_languages(*groups)


def _project_languages_from_conn(conn: sqlite3.Connection) -> list[str]:
    return _ProjectRowMapper.project_languages_from_conn(conn)


def _symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    return _ProjectRowMapper.symbol_rows(conn, file_id)


def _iter_source_files(root: Path) -> list[Path]:
    _sync_storage()
    return _iter_source_files_impl(root)


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
    _sync_storage()
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    rel_path = str(resolved_path.relative_to(root_path))
    skeleton = analysis["skeleton"]
    byte_length = len(parsed.source_code.encode("utf-8"))
    languages = _ProjectRowMapper.encode_languages(analysis.get("languages", [parsed.language]))

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
    file_row = conn.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,)).fetchone()
    if file_row is None:
        raise ValueError("Failed to persist file analysis")
    file_id = int(file_row[0])
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
                _ProjectRowMapper.encode_languages(symbol.get("languages", [parsed.language])),
            ),
        )


def _load_project_metadata(project: str) -> dict[str, Any] | None:
    _sync_storage()
    return _load_project_metadata_impl(project)


def list_projects() -> list[dict[str, Any]]:
    _sync_storage()
    return _list_projects_impl()


def search_projects(query: str) -> list[dict[str, Any]]:
    _sync_storage()
    return _search_projects_impl(query)


def get_project(project: str) -> dict[str, Any]:
    _sync_storage()
    return _get_project_impl(project)


def add_project(project: str, root_path: str, mode: str = "file", description: str = "") -> dict[str, Any]:
    _sync_storage()
    return _add_project_impl(project, root_path, mode=mode, description=description)


def resolve_project_path(project: str, file_path: str) -> Path:
    _sync_storage()
    return _resolve_project_path_impl(project, file_path)


def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, Any]:
    _sync_storage()
    return _ingest_project_tree_impl(project, refresh=refresh)


def sync_project_tree(project: str) -> dict[str, Any]:
    _sync_storage()
    return _sync_project_tree_impl(project)


def _read_file_record(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
    return _read_file_record_impl(conn, file_id)


def project_file_summary(project: str, file_path: str) -> dict[str, Any]:
    _sync_storage()
    return _project_file_summary_impl(project, file_path)
