from __future__ import annotations

import sqlite3
from pathlib import Path

from . import project_storage as storage
from .project_row_mapper import ProjectRowMapper


class ProjectRepository:
    """Repository-style helpers for sqlite-backed project persistence."""

    @staticmethod
    def connect(db_path: Path) -> sqlite3.Connection:
        return storage._connect(db_path)

    @staticmethod
    def init_metadata_schema(conn: sqlite3.Connection) -> None:
        storage._init_metadata_schema(conn)

    @staticmethod
    def init_project_schema(conn: sqlite3.Connection) -> None:
        storage._init_project_schema(conn)

    @staticmethod
    def ensure_project_schema(conn: sqlite3.Connection) -> None:
        storage._ensure_project_schema(conn)

    @staticmethod
    def load_project_metadata(project: str) -> dict[str, object] | None:
        if not storage.METADATA_DB.exists():
            return None
        with ProjectRepository.connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            row = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
            if row is None:
                return None
            return ProjectRowMapper.row_to_project_dict(row)

    @staticmethod
    def list_projects() -> list[dict[str, object]]:
        if not storage.METADATA_DB.exists():
            return []
        with ProjectRepository.connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            rows = conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
            return [ProjectRowMapper.row_to_project_dict(row) for row in rows]

    @staticmethod
    def search_projects(query: str) -> list[dict[str, object]]:
        needle = query.strip()
        if not needle:
            return ProjectRepository.list_projects()

        pattern = f"%{needle.lower()}%"
        if not storage.METADATA_DB.exists():
            return []

        with ProjectRepository.connect(storage.METADATA_DB) as conn:
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
        with ProjectRepository.connect(storage.METADATA_DB) as conn:
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
                    str(storage._project_db_path(project)),
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
        db_path = storage._project_db_path(project)
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
        with ProjectRepository.connect(storage.METADATA_DB) as conn:
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
    def symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, object]]:
        return ProjectRowMapper.symbol_rows(conn, file_id)

    @staticmethod
    def read_file_record(conn: sqlite3.Connection, file_id: int) -> dict[str, object]:
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
