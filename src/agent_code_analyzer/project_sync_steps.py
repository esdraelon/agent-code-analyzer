from __future__ import annotations

from pathlib import Path
from typing import Any

from . import project_storage as storage
from .parsing import detect_language
from .project_repository import ProjectRepository
from .project_row_mapper import ProjectRowMapper


def scan_source_files(root: Path) -> tuple[dict[str, Path], dict[str, dict[str, int | str]]]:
    current_files: dict[str, Path] = {}
    current_stats: dict[str, dict[str, int | str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in storage.IGNORED_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") and path.suffix == "":
            continue
        if not detect_language(str(path)):
            continue
        rel_path = str(path.relative_to(root))
        current_files[rel_path] = path
        current_stats[rel_path] = storage._project_file_snapshot(path)
    return current_files, current_stats


def project_sync_diff(
    existing_files: dict[str, Any],
    current_files: dict[str, Path],
    current_stats: dict[str, dict[str, int | str]],
) -> tuple[list[str], list[str], list[str]]:
    current_paths = set(current_files)
    existing_paths = set(existing_files)
    deleted_paths = sorted(existing_paths - current_paths)
    unchanged_paths: list[str] = []
    changed_paths: list[str] = []

    for rel_path in sorted(current_paths):
        snapshot = current_stats[rel_path]
        existing_row = existing_files.get(rel_path)
        if (
            existing_row is not None
            and int(existing_row["file_size"]) == snapshot["file_size"]
            and int(existing_row["file_mtime_ns"]) == snapshot["file_mtime_ns"]
            and str(existing_row["file_content_hash"] if "file_content_hash" in existing_row.keys() else "") == snapshot["file_content_hash"]
        ):
            unchanged_paths.append(rel_path)
            continue
        changed_paths.append(rel_path)

    return deleted_paths, unchanged_paths, changed_paths


def clear_project_indexes(conn, project: str) -> None:
    from .lexical_index import delete_project as delete_lexical_project

    delete_lexical_project(conn, project)
    try:
        from .vector_index import get_vector_index

        get_vector_index().delete_project(project)
    except Exception:
        pass


def delete_file_indexes(conn, project: str, file_id: int) -> None:
    from .lexical_index import delete_file as delete_lexical_file

    delete_lexical_file(conn, project, file_id)
    try:
        from .vector_index import get_vector_index, _sqlite_file_uri

        get_vector_index().delete_file(_sqlite_file_uri(project, file_id))
    except Exception:
        pass


def write_project_state(
    conn,
    *,
    project: str,
    root: Path,
    created_at: str,
    indexed_at: str,
    file_count: int,
    supported_file_count: int,
    symbol_count: int,
    languages: list[str],
) -> None:
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
            supported_file_count,
            symbol_count,
            ProjectRowMapper.encode_languages(languages),
        ),
    )


def update_metadata_projection(
    *,
    project: str,
    indexed_at: str,
    file_count: int,
    supported_file_count: int,
    symbol_count: int,
    languages: list[str],
) -> None:
    with storage._acquire_locks(storage.METADATA_DB):
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (
                    indexed_at,
                    indexed_at,
                    file_count,
                    supported_file_count,
                    symbol_count,
                    ProjectRowMapper.encode_languages(languages),
                    project,
                ),
            )
