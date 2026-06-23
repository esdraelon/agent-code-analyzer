from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import project_storage as storage
from .ingestion_state import (
    IngestionCheckpoint,
    begin_ingestion_checkpoint,
    complete_ingestion_checkpoint,
    fail_ingestion_checkpoint,
    load_ingestion_checkpoint,
    update_ingestion_checkpoint,
    write_ingestion_checkpoint,
)
from .parsing import analyze_file, detect_language, render_ast_svg
from .project_repository import ProjectRepository
from .project_row_mapper import ProjectRowMapper
from . import project_sync_steps as sync_steps


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


def _sync_project_file(
    conn,
    *,
    project: str,
    root_path: Path,
    resolved_path: Path,
    indexed_at: str,
) -> int:
    analysis = analyze_file(str(resolved_path))
    snapshot = storage._project_file_snapshot(resolved_path)
    _upsert_file_analysis(
        conn,
        project=project,
        root_path=root_path,
        resolved_path=resolved_path,
        analysis=analysis,
        indexed_at=indexed_at,
        file_size=int(snapshot["file_size"]),
        file_mtime_ns=int(snapshot["file_mtime_ns"]),
        file_content_hash=str(snapshot["file_content_hash"]),
    )
    return len(analysis["symbols"])


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


def add_project(
    project: str,
    root_path: str,
    mode: str = "file",
    description: str = "",
    ingest: bool = True,
) -> dict[str, Any]:
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
    if ingest and mode == "directory":
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
    file_content_hash: str,
) -> None:
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    rel_path = str(resolved_path.relative_to(root_path))
    skeleton = analysis["skeleton"]
    byte_length = len(parsed.source_code.encode("utf-8"))
    languages = ProjectRowMapper.encode_languages(analysis.get("languages", [parsed.language]))
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

    current_files: dict[str, Path] = {}
    total_symbols = 0
    file_count = 0
    project_languages: list[str] = []
    checkpoint_started = False
    try:
        with storage._db_lock(db_path):
            with storage._connect(db_path) as conn:
                storage._ensure_project_schema(conn)
                checkpoint_started = True
                checkpoint = IngestionCheckpoint(
                    project_name=project,
                    root_path=str(root),
                    mode="semantic_rebuild",
                    phase="full_rebuild",
                    status="running",
                    queued_at=indexed_at,
                    started_at=indexed_at,
                    updated_at=indexed_at,
                    completed_at=None,
                    last_file_path=None,
                    last_file_mtime_ns=None,
                    last_file_content_hash="",
                    total_file_count=0,
                    processed_file_count=0,
                    error_state="",
                )
                write_ingestion_checkpoint(conn, checkpoint)
                if refresh:
                    conn.execute("DELETE FROM symbols")
                    conn.execute("DELETE FROM files")
                    sync_steps.clear_project_indexes(conn, project)

                current_files, _current_stats = sync_steps.scan_source_files(root)
                file_count = len(current_files)
                checkpoint = checkpoint.with_updates(
                    total_file_count=file_count,
                    processed_file_count=0,
                    phase="full_rebuild",
                    updated_at=storage._now(),
                )
                write_ingestion_checkpoint(conn, checkpoint)
                for processed_count, rel_path in enumerate(sorted(current_files), start=1):
                    total_symbols += _sync_project_file(
                        conn,
                        project=project,
                        root_path=root,
                        resolved_path=current_files[rel_path],
                        indexed_at=indexed_at,
                    )
                    snapshot = storage._project_file_snapshot(current_files[rel_path])
                    checkpoint = checkpoint.with_updates(
                        total_file_count=file_count,
                        processed_file_count=processed_count,
                        last_file_path=rel_path,
                        last_file_mtime_ns=int(snapshot["file_mtime_ns"]),
                        last_file_content_hash=str(snapshot["file_content_hash"]),
                        updated_at=storage._now(),
                    )
                    write_ingestion_checkpoint(conn, checkpoint)

                existing_state = conn.execute(
                    "SELECT created_at FROM project_state WHERE project_name = ?",
                    (project,),
                ).fetchone()
                created_at = existing_state["created_at"] if existing_state else indexed_at
                project_languages = ProjectRowMapper.project_languages_from_conn(conn)
                sync_steps.write_project_state(
                    conn,
                    project=project,
                    root=root,
                    created_at=created_at,
                    indexed_at=indexed_at,
                    file_count=file_count,
                    supported_file_count=file_count,
                    symbol_count=total_symbols,
                    languages=project_languages,
                )

                checkpoint = checkpoint.with_updates(
                    status="completed",
                    phase="completed",
                    completed_at=storage._now(),
                    updated_at=storage._now(),
                    error_state="",
                )
                write_ingestion_checkpoint(conn, checkpoint)

        sync_steps.update_metadata_projection(
            project=project,
            indexed_at=indexed_at,
            file_count=file_count,
            supported_file_count=file_count,
            symbol_count=total_symbols,
            languages=project_languages,
        )
    except Exception as exc:
        if checkpoint_started:
            try:
                fail_ingestion_checkpoint(db_path, project=project, error_state=str(exc))
            except Exception:
                pass
        raise

    return {
        "project": project,
        "root_path": str(root),
        "mode": project_data["mode"],
        "file_count": file_count,
        "supported_file_count": file_count,
        "symbol_count": total_symbols,
        "indexed_at": indexed_at,
        "languages": project_languages,
    }


def sync_project_tree(project: str) -> dict[str, Any]:
    project_data = get_project(project)
    root = Path(project_data["root_path"]).resolve()
    db_path = Path(project_data["db_path"])
    now = storage._now()

    checkpoint_started = False
    try:
        with storage._db_lock(db_path):
            with storage._connect(db_path) as conn:
                storage._ensure_project_schema(conn)
                checkpoint_started = True
                checkpoint = IngestionCheckpoint(
                    project_name=project,
                    root_path=str(root),
                    mode="semantic_refresh",
                    phase="gap_sweep",
                    status="running",
                    queued_at=now,
                    started_at=now,
                    updated_at=now,
                    completed_at=None,
                    last_file_path=None,
                    last_file_mtime_ns=None,
                    last_file_content_hash="",
                    total_file_count=0,
                    processed_file_count=0,
                    error_state="",
                )
                write_ingestion_checkpoint(conn, checkpoint)
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
                        SELECT id, rel_path, abs_path, file_size, file_mtime_ns, file_content_hash
                        FROM files
                        """
                    ).fetchall()
                }

                current_files, current_stats = sync_steps.scan_source_files(root)
                checkpoint = checkpoint.with_updates(
                    total_file_count=len(current_files),
                    processed_file_count=0,
                    updated_at=storage._now(),
                )
                write_ingestion_checkpoint(conn, checkpoint)

                deleted_paths, unchanged_paths, changed_paths = sync_steps.project_sync_diff(
                    existing_files,
                    current_files,
                    current_stats,
                )
                upserted_paths: list[str] = []

                for processed_count, rel_path in enumerate(changed_paths, start=1):
                    _sync_project_file(
                        conn,
                        project=project,
                        root_path=root,
                        resolved_path=current_files[rel_path],
                        indexed_at=now,
                    )
                    upserted_paths.append(rel_path)
                    snapshot = current_stats[rel_path]
                    checkpoint = checkpoint.with_updates(
                        total_file_count=len(current_files),
                        processed_file_count=processed_count,
                        last_file_path=rel_path,
                        last_file_mtime_ns=int(snapshot["file_mtime_ns"]),
                        last_file_content_hash=str(snapshot["file_content_hash"]),
                        updated_at=storage._now(),
                    )
                    write_ingestion_checkpoint(conn, checkpoint)

                deleted_file_count = 0
                for rel_path in deleted_paths:
                    row = existing_files[rel_path]
                    file_id = int(row["id"])
                    sync_steps.delete_file_indexes(conn, project, file_id)
                    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
                    deleted_file_count += 1

                if not upserted_paths and deleted_file_count == 0 and existing_state is not None:
                    checkpoint = checkpoint.with_updates(
                        status="completed",
                        phase="completed",
                        completed_at=storage._now(),
                        updated_at=storage._now(),
                        error_state="",
                    )
                    write_ingestion_checkpoint(conn, checkpoint)
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
                sync_steps.write_project_state(
                    conn,
                    project=project,
                    root=root,
                    created_at=created_at,
                    indexed_at=indexed_at,
                    file_count=file_count,
                    supported_file_count=file_count,
                    symbol_count=symbol_count,
                    languages=project_languages,
                )

                checkpoint = checkpoint.with_updates(
                    status="completed",
                    phase="completed",
                    completed_at=storage._now(),
                    updated_at=storage._now(),
                    error_state="",
                )
                write_ingestion_checkpoint(conn, checkpoint)

        sync_steps.update_metadata_projection(
            project=project,
            indexed_at=indexed_at,
            file_count=file_count,
            supported_file_count=file_count,
            symbol_count=symbol_count,
            languages=project_languages,
        )
    except Exception as exc:
        if checkpoint_started:
            try:
                fail_ingestion_checkpoint(db_path, project=project, error_state=str(exc))
            except Exception:
                pass
        raise

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
        "ast_svg": render_ast_svg(
            file_path=file_data["path"],
            language=file_data["language"],
            root_type=file_data["root_type"],
            skeleton=file_data["skeleton"],
            symbol_count=len(symbols),
            node_count=file_data["node_count"],
        ),
        "symbols": symbols,
        "symbol_health": analysis["symbol_health"],
        "indexed_at": file_data["indexed_at"],
    }


def project_ingestion_job(project: str) -> dict[str, Any] | None:
    project_data = get_project(project)
    checkpoint = load_ingestion_checkpoint(Path(project_data["db_path"]), project)
    if checkpoint is None:
        return None
    return {
        "project": checkpoint.project_name,
        "job_id": checkpoint.project_name,
        "action": checkpoint.mode,
        "phase": checkpoint.phase,
        "status": checkpoint.status,
        "queued_at": checkpoint.queued_at,
        "started_at": checkpoint.started_at,
        "updated_at": checkpoint.updated_at,
        "completed_at": checkpoint.completed_at,
        "total_count": checkpoint.total_file_count,
        "processed_count": checkpoint.processed_file_count,
        "last_file_path": checkpoint.last_file_path,
        "last_file_mtime_ns": checkpoint.last_file_mtime_ns,
        "last_file_content_hash": checkpoint.last_file_content_hash,
        "last_error": checkpoint.error_state,
    }


def _normalize_entry_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "other"
    if "class" in normalized or "enum" in normalized or "struct" in normalized or "interface" in normalized:
        return "class"
    if "function" in normalized or "method" in normalized:
        return "method"
    if "module" in normalized or "package" in normalized:
        return "module"
    if "file" in normalized:
        return "file"
    if "chunk" in normalized:
        return "chunk"
    if "symbol" in normalized:
        return "symbol"
    return "other"


def _label_for_entry_type(value: str) -> str:
    return {
        "class": "Classes",
        "method": "Methods",
        "module": "Modules",
        "file": "Files",
        "chunk": "Chunks",
        "symbol": "Symbols",
        "tree-sitter": "Tree-sitter",
        "lexical": "Lexical",
        "semantic": "Semantic",
        "other": "Other",
    }.get(value, value.replace("_", " ").title())


def _count_qdrant_points(project: str, filters: dict[str, str] | None = None) -> int:
    try:
        from qdrant_client import models as qmodels

        from .vector_index import get_vector_index

        vector_index = get_vector_index()
        client = vector_index.client()
        if not client.collection_exists(vector_index.collection_name):
            return 0
        must = [qmodels.FieldCondition(key="project_name", match=qmodels.MatchValue(value=project))]
        for key, value in (filters or {}).items():
            must.append(qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value)))
        result = client.count(
            collection_name=vector_index.collection_name,
            count_filter=qmodels.Filter(must=must),  # type: ignore[arg-type]
            exact=True,
        )
        return int(getattr(result, "count", 0) or 0)
    except Exception:
        return 0


def _counter_items(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"key": key, "label": _label_for_entry_type(key), "count": int(count)}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def project_index_summary(project: str) -> dict[str, Any]:
    project_data = get_project(project)
    db_path = Path(project_data["db_path"])

    file_count = int(project_data.get("file_count", 0))
    symbol_total = int(project_data.get("symbol_count", 0))
    hard_total = file_count + symbol_total

    with storage._db_lock(db_path):
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
            symbol_rows = conn.execute("SELECT type FROM symbols").fetchall()

    symbol_type_counts = Counter(_normalize_entry_type(row["type"]) for row in symbol_rows)
    lexical_scope_counts = Counter({"file": file_count, "symbol": symbol_total})
    lexical_unit_counts = Counter(symbol_type_counts)
    lexical_total = hard_total

    semantic_total = _count_qdrant_points(project)
    semantic_source_kinds = ["file", "tree-sitter", "chunk", "symbol"]
    semantic_unit_types = ["file", "class", "method", "module", "chunk"]
    semantic_source_counts = Counter({kind: _count_qdrant_points(project, {"source_kind": kind}) for kind in semantic_source_kinds})
    semantic_unit_counts = Counter({kind: _count_qdrant_points(project, {"unit_type": kind}) for kind in semantic_unit_types})
    semantic_known_total = sum(semantic_source_counts.values())
    semantic_other = max(0, semantic_total - semantic_known_total)
    if semantic_other:
        semantic_source_counts["other"] = semantic_other

    return {
        "project": project,
        "files": int(project_data.get("file_count", 0)),
        "symbols": int(project_data.get("symbol_count", 0)),
        "lexical_total": lexical_total,
        "semantic_total": semantic_total,
        "hard_total": lexical_total,
        "soft_total": semantic_total,
        "hard": {
            "lexical_total": lexical_total,
            "lexical_scope_counts": _counter_items(lexical_scope_counts),
            "lexical_symbol_unit_counts": _counter_items(lexical_unit_counts),
            "symbol_type_counts": _counter_items(symbol_type_counts),
        },
        "soft": {
            "semantic_total": semantic_total,
            "source_kind_counts": _counter_items(semantic_source_counts),
            "unit_type_counts": _counter_items(semantic_unit_counts),
        },
    }


def remove_project(project: str) -> dict[str, Any]:
    project = storage._normalize_project(project)
    metadata = _load_project_metadata(project)
    if metadata is None:
        return {"project": project, "removed": False, "reason": "not_found"}

    db_path = Path(metadata["db_path"])
    with storage._acquire_locks(storage.METADATA_DB, db_path):
        if db_path.exists():
            with storage._connect(db_path) as conn:
                storage._ensure_project_schema(conn)
                sync_steps.clear_project_indexes(conn, project)
                conn.execute("DELETE FROM ingestion_checkpoints WHERE project_name = ?", (project,))
                conn.execute("DELETE FROM project_state WHERE project_name = ?", (project,))
        with storage._connect(storage.METADATA_DB) as conn:
            ProjectRepository.init_metadata_schema(conn)
            conn.execute("DELETE FROM projects WHERE name = ?", (project,))
    try:
        db_path.unlink()
    except FileNotFoundError:
        pass
    return {"project": project, "removed": True, "db_path": str(db_path)}
