from __future__ import annotations

from pathlib import Path
from typing import Any

from . import project_storage as storage
from .parsing import analyze_file, detect_language
from .project_repository import ProjectRepository
from .project_row_mapper import ProjectRowMapper


def _sync_qdrant_records(
    *,
    project: str,
    root_path: Path,
    file_id: int,
    file_record: dict[str, Any],
    symbol_rows: list[dict[str, Any]],
) -> None:
    try:
        from .vector_index import get_vector_index

        get_vector_index().sync_records(
            project=project,
            project_root=root_path,
            file_id=file_id,
            file_record=file_record,
            symbol_rows=symbol_rows,
        )
    except Exception:
        # Best-effort secondary index; sqlite remains authoritative.
        pass


def _load_project_metadata(project: str) -> dict[str, Any] | None:
    return ProjectRepository.load_project_metadata(project)


def list_projects() -> list[dict[str, Any]]:
    return ProjectRepository.list_projects()


def search_projects(query: str) -> list[dict[str, Any]]:
    return ProjectRepository.search_projects(query)


def get_project(project: str) -> dict[str, Any]:
    project = storage._normalize_project(project)
    metadata = _load_project_metadata(project)
    if metadata is None:
        raise ValueError(f"Unknown project: {project}")
    return metadata


def add_project(project: str, root_path: str, mode: str = "file", description: str = "") -> dict[str, Any]:
    project = storage._normalize_project(project)
    mode = mode.strip().lower()
    if mode not in {"file", "directory"}:
        raise ValueError("mode must be 'file' or 'directory'")

    root = Path(root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")

    db_path = storage._project_db_path(project)
    now = storage._now()
    project_languages: list[str] = []

    with storage._acquire_locks(storage.METADATA_DB, db_path):
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            existing = conn.execute("SELECT * FROM projects WHERE name = ?", (project,)).fetchone()
            created_at = existing["created_at"] if existing else now
            indexed_at = existing["indexed_at"] if existing else None
            file_count = int(existing["file_count"] if existing else 0)
            supported_file_count = int(existing["supported_file_count"] if existing else 0)
            symbol_count = int(existing["symbol_count"] if existing else 0)
            languages = ProjectRowMapper.encode_languages(
                ProjectRowMapper.decode_languages(existing["languages"]) if existing and "languages" in existing.keys() else []
            )
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

        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
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
        if any(part in storage.IGNORED_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") and path.suffix == "":
            continue
        if detect_language(str(path)):
            files.append(path)
    return sorted(files)


def _upsert_file_analysis(
    conn,
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
    languages = ProjectRowMapper.encode_languages(analysis.get("languages", [parsed.language]))

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
                ProjectRowMapper.encode_languages(symbol.get("languages", [parsed.language])),
            ),
        )

    file_record = ProjectRepository.read_file_record(conn, file_id)
    symbol_rows = ProjectRepository.symbol_rows(conn, file_id)
    _sync_qdrant_records(
        project=project,
        root_path=root_path,
        file_id=file_id,
        file_record=file_record,
        symbol_rows=symbol_rows,
    )


def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, Any]:
    project_data = get_project(project)
    root = Path(project_data["root_path"])
    db_path = Path(project_data["db_path"])
    indexed_at = storage._now()

    if not refresh:
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
            row = conn.execute(
                """
                SELECT project_name, root_path, file_count, supported_file_count, symbol_count, indexed_at, languages
                FROM project_state
                WHERE project_name = ?
                """,
                (project,),
            ).fetchone()
            if row is not None:
                return ProjectRowMapper.row_to_summary(row)

    with storage._db_lock(db_path):
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
            if refresh:
                conn.execute("DELETE FROM symbols")
                conn.execute("DELETE FROM files")
                try:
                    from .vector_index import get_vector_index

                    get_vector_index().delete_project(project)
                except Exception:
                    pass

            files = _iter_source_files(root)
            total_symbols = 0
            for path in files:
                from . import projects as projects_api
                analysis = projects_api.analyze_file(str(path))
                from . import projects as projects_api
                projects_api._upsert_file_analysis(
                    conn,
                    project=project,
                    root_path=root,
                    resolved_path=path,
                    analysis=analysis,
                    indexed_at=indexed_at,
                    **storage._project_file_snapshot(path),
                )
                total_symbols += len(analysis["symbols"])

            existing_state = conn.execute(
                "SELECT created_at FROM project_state WHERE project_name = ?",
                (project,),
            ).fetchone()
            created_at = existing_state["created_at"] if existing_state else indexed_at
            project_languages = ProjectRowMapper.project_languages_from_conn(conn)
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
                    ProjectRowMapper.encode_languages(project_languages),
                ),
            )

    with storage._acquire_locks(storage.METADATA_DB):
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, len(files), len(files), total_symbols, ProjectRowMapper.encode_languages(project_languages), project),
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
    now = storage._now()

    with storage._db_lock(db_path):
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
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
                current_stats[rel_path] = storage._project_file_snapshot(path)

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

                from . import projects as projects_api
                analysis = projects_api.analyze_file(str(path))
                from . import projects as projects_api
                projects_api._upsert_file_analysis(
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
                file_id = int(row["id"])
                try:
                    from .vector_index import get_vector_index, _sqlite_file_uri

                    get_vector_index().delete_file(_sqlite_file_uri(project, file_id))
                except Exception:
                    pass
                conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
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
            project_languages = ProjectRowMapper.project_languages_from_conn(conn)
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
                    ProjectRowMapper.encode_languages(project_languages),
                ),
            )

    with storage._acquire_locks(storage.METADATA_DB):
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, file_count, file_count, symbol_count, ProjectRowMapper.encode_languages(project_languages), project),
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


def _read_file_record(conn, file_id: int) -> dict[str, Any]:
    return ProjectRepository.read_file_record(conn, file_id)


def project_file_summary(project: str, file_path: str) -> dict[str, Any]:
    project_data = get_project(project)
    resolved = resolve_project_path(project, file_path)
    root = Path(project_data["root_path"]).resolve()
    db_path = Path(project_data["db_path"])
    rel_path = str(resolved.relative_to(root))

    analysis = analyze_file(str(resolved))
    indexed_at = storage._now()

    with storage._db_lock(db_path):
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
            from . import projects as projects_api
            projects_api._upsert_file_analysis(
                conn,
                project=project,
                root_path=root,
                resolved_path=resolved,
                analysis=analysis,
                indexed_at=indexed_at,
                **storage._project_file_snapshot(resolved),
            )
            file_row = conn.execute("SELECT id FROM files WHERE rel_path = ?", (rel_path,)).fetchone()
            if file_row is None:
                raise ValueError("Failed to persist file analysis")
            file_id = int(file_row[0])
            file_data = _read_file_record(conn, file_id)
            symbols = ProjectRepository.symbol_rows(conn, file_id)
            file_count = conn.execute("SELECT COUNT(*) AS count FROM files").fetchone()["count"]
            symbol_count = conn.execute("SELECT COUNT(*) AS count FROM symbols").fetchone()["count"]
            project_languages = ProjectRowMapper.project_languages_from_conn(conn)
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
                    ProjectRowMapper.encode_languages(project_languages),
                ),
            )

    with storage._acquire_locks(storage.METADATA_DB):
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute(
                """
                UPDATE projects
                SET indexed_at = ?, updated_at = ?, file_count = ?, supported_file_count = ?, symbol_count = ?, languages = ?
                WHERE name = ?
                """,
                (indexed_at, indexed_at, int(file_count), int(file_count), int(symbol_count), ProjectRowMapper.encode_languages(project_languages), project),
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
