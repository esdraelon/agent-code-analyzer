from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import project_storage as _storage
from .project_models import ProjectRecord as _ProjectRecord
from .parsing import analyze_file, detect_language
from .project_repository import ProjectRepository as _ProjectRepository
from .project_row_mapper import ProjectRowMapper as _ProjectRowMapper
from .lexical_index import search as _lexical_search_impl
from .lexical_index import sync_analysis as _sync_lexical_analysis
from .search_filters import normalize_exclusions, should_exclude_result
from .vector_index import get_vector_index
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
    project_index_summary as _project_index_summary_impl,
    project_ingestion_job as _project_ingestion_job_impl,
    remove_project as _remove_project_impl,
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


def _project_file_snapshot(path: Path) -> dict[str, int | str]:
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
    file_content_hash: str,
) -> None:
    _sync_storage()
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    rel_path = str(resolved_path.relative_to(root_path))
    skeleton = analysis["skeleton"]
    byte_length = len(parsed.source_code.encode("utf-8"))
    languages = _ProjectRowMapper.encode_languages(analysis.get("languages", [parsed.language]))
    root_start_row = int(root_node.start_point[0])
    root_start_column = int(root_node.start_point[1])
    root_end_row = int(root_node.end_point[0])
    root_end_column = int(root_node.end_point[1])

    conn.execute(
        """
        INSERT INTO files (
            rel_path, abs_path, language, languages, root_type, root_start_row, root_start_column, root_end_row, root_end_column, node_count, has_error, byte_length, file_size, file_mtime_ns, file_content_hash, skeleton, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rel_path) DO UPDATE SET
            abs_path = excluded.abs_path,
            language = excluded.language,
            languages = excluded.languages,
            root_type = excluded.root_type,
            root_start_row = excluded.root_start_row,
            root_start_column = excluded.root_start_column,
            root_end_row = excluded.root_end_row,
            root_end_column = excluded.root_end_column,
            node_count = excluded.node_count,
            has_error = excluded.has_error,
            byte_length = excluded.byte_length,
            file_size = excluded.file_size,
            file_mtime_ns = excluded.file_mtime_ns,
            file_content_hash = excluded.file_content_hash,
            skeleton = excluded.skeleton,
            indexed_at = excluded.indexed_at
        """,
        (
            rel_path,
            str(resolved_path),
            parsed.language,
            languages,
            root_node.type,
            root_start_row,
            root_start_column,
            root_end_row,
            root_end_column,
            root_node.descendant_count,
            int(root_node.has_error),
            byte_length,
            file_size,
            file_mtime_ns,
            file_content_hash,
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

    _sync_lexical_analysis(
        conn,
        project=project,
        root_path=root_path,
        file_id=file_id,
        file_path=str(resolved_path),
        analysis=analysis,
        indexed_at=indexed_at,
        file_size=file_size,
        file_mtime_ns=file_mtime_ns,
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


def project_index_summary(project: str) -> dict[str, Any]:
    _sync_storage()
    return _project_index_summary_impl(project)


def project_ingestion_job(project: str) -> dict[str, Any] | None:
    _sync_storage()
    return _project_ingestion_job_impl(project)


def project_paths(project: str, *, kind: str = "all", prefix: str = "", limit: int = 50) -> dict[str, Any]:
    _sync_storage()
    project_data = get_project(project)
    normalized_kind = (kind or "all").strip().lower()
    normalized_prefix = (prefix or "").strip().replace("\\", "/").rstrip("/")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if normalized_kind not in {"all", "file", "directory"}:
        raise ValueError("kind must be one of: all, file, directory")

    with _storage._connect(Path(project_data["db_path"])) as conn:
        rows = conn.execute("SELECT rel_path FROM files ORDER BY rel_path ASC").fetchall()

    file_paths: list[str] = []
    directory_paths: list[str] = []
    directory_seen: set[str] = set()
    for row in rows:
        rel_path = str(row[0])
        if normalized_prefix and not rel_path.startswith(normalized_prefix):
            continue
        if normalized_kind in {"all", "file"} and rel_path not in file_paths:
            file_paths.append(rel_path)
        if normalized_kind in {"all", "directory"}:
            parts = Path(rel_path).parents
            for parent in parts:
                parent_text = str(parent).replace("\\", "/")
                if parent_text in {"", "."}:
                    continue
                if normalized_prefix and not (parent_text == normalized_prefix or parent_text.startswith(f"{normalized_prefix}/")):
                    continue
                if parent_text not in directory_seen:
                    directory_seen.add(parent_text)
                    directory_paths.append(parent_text)

    if normalized_kind == "file":
        return {"project": project, "kind": normalized_kind, "prefix": normalized_prefix, "paths": file_paths[:limit]}
    if normalized_kind == "directory":
        return {"project": project, "kind": normalized_kind, "prefix": normalized_prefix, "paths": directory_paths[:limit]}
    return {
        "project": project,
        "kind": normalized_kind,
        "prefix": normalized_prefix,
        "file_paths": file_paths[:limit],
        "directory_paths": directory_paths[:limit],
    }


def remove_project(project: str) -> dict[str, Any]:
    _sync_storage()
    return _remove_project_impl(project)


def lexical_search(
    query: str,
    *,
    project: str | None = None,
    scope_type: str | None = None,
    directory: str | None = None,
    limit: int = 10,
    exclude_files: list[str] | None = None,
    exclude_symbols: list[str] | None = None,
) -> dict[str, Any]:
    _sync_storage()
    excluded_files = normalize_exclusions(exclude_files)
    excluded_symbols = normalize_exclusions(exclude_symbols)
    if project is not None:
        project_data = get_project(project)
        with _storage._connect(Path(project_data["db_path"])) as conn:
            result = _lexical_search_impl(
                conn,
                query,
                project=project,
                scope_type=scope_type,
                directory=directory,
                limit=limit,
                exclude_files=exclude_files,
                exclude_symbols=exclude_symbols,
            )
            result["results"] = [
                item
                for item in result.get("results", [])
                if not should_exclude_result(item, exclude_files=excluded_files, exclude_symbols=excluded_symbols)
            ]
            return result

    results: list[dict[str, Any]] = []
    for project_record in list_projects():
        with _storage._connect(Path(project_record["db_path"])) as conn:
            search_result = _lexical_search_impl(
                conn,
                query,
                project=project_record["name"],
                scope_type=scope_type,
                directory=directory,
                limit=limit,
                exclude_files=exclude_files,
                exclude_symbols=exclude_symbols,
            )
        results.extend(
            item
            for item in search_result["results"]
            if not should_exclude_result(item, exclude_files=excluded_files, exclude_symbols=excluded_symbols)
        )

    results.sort(
        key=lambda item: (
            -float(item.get("score", 0.0)),
            item.get("scope_type") != "symbol",
            item.get("symbol_name", ""),
            item.get("file_path", ""),
        )
    )
    return {"query": query, "project": None, "scope_type": scope_type, "directory": directory, "limit": limit, "results": results[:limit]}


def _merge_search_results(
    *groups: dict[str, Any],
    limit: int,
    exclude_files: set[str] | None = None,
    exclude_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group_index, group in enumerate(groups):
        for result_index, result in enumerate(group.get("results", [])):
            if should_exclude_result(result, exclude_files=exclude_files, exclude_symbols=exclude_symbols):
                continue
            sqlite_uri = str(result.get("sqlite_uri", ""))
            if not sqlite_uri:
                continue
            combined_score = float(result.get("score", 0.0)) + (1.0 / (result_index + 1)) + (0.1 * (len(groups) - group_index))
            existing = merged.get(sqlite_uri)
            if existing is None or combined_score > float(existing.get("score", 0.0)):
                merged[sqlite_uri] = {**result, "score": combined_score}

    merged_results = list(merged.values())
    merged_results.sort(
        key=lambda item: (
            -float(item.get("score", 0.0)),
            item.get("scope_type") != "symbol",
            item.get("symbol_name", ""),
            item.get("file_path", ""),
        )
    )
    return merged_results[:limit]


def search_code(
    query: str,
    *,
    project: str | None = None,
    scope_type: str | None = None,
    directory: str | None = None,
    limit: int = 10,
    exclude_files: list[str] | None = None,
    exclude_symbols: list[str] | None = None,
) -> dict[str, Any]:
    _sync_storage()
    lexical = lexical_search(
        query,
        project=project,
        scope_type=scope_type,
        directory=directory,
        limit=limit,
        exclude_files=exclude_files,
        exclude_symbols=exclude_symbols,
    )
    semantic = get_vector_index().search(
        query,
        project=project,
        scope_type=scope_type,
        directory=directory,
        limit=limit,
        exclude_files=exclude_files,
        exclude_symbols=exclude_symbols,
    )
    excluded_files = normalize_exclusions(exclude_files)
    excluded_symbols = normalize_exclusions(exclude_symbols)
    results = _merge_search_results(
        lexical,
        semantic,
        limit=limit,
        exclude_files=excluded_files,
        exclude_symbols=excluded_symbols,
    )
    return {
        "query": query,
        "project": project,
        "scope_type": scope_type,
        "directory": directory,
        "limit": limit,
        "lexical": lexical,
        "semantic": semantic,
        "results": results,
    }
