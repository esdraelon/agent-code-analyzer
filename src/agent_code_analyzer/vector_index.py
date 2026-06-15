from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from qdrant_client import QdrantClient, models as qmodels

from . import project_storage as storage
from .project_repository import ProjectRepository
from .project_row_mapper import ProjectRowMapper

QDRANT_DEFAULT_URL = os.environ.get("AGENT_CODE_ANALYZER_QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_DEFAULT_COLLECTION = os.environ.get("AGENT_CODE_ANALYZER_QDRANT_COLLECTION", "agent_code_analyzer_chunks")
QDRANT_VECTOR_SIZE = int(os.environ.get("AGENT_CODE_ANALYZER_QDRANT_VECTOR_SIZE", "16"))
QDRANT_NAMESPACE = uuid.UUID("8d02b10d-0d18-4b93-b3d9-4ff9c1c44c7d")


def _slug_component(value: str) -> str:
    return quote(storage._normalize_project(value), safe="")


def _sqlite_file_uri(project: str, file_id: int) -> str:
    return f"sqlite://projects/{_slug_component(project)}/files/{file_id}"


def _sqlite_symbol_uri(project: str, file_id: int, symbol_order: int) -> str:
    return f"{_sqlite_file_uri(project, file_id)}/symbols/{symbol_order}"


def _stable_point_id(sqlite_uri: str) -> str:
    return str(uuid.uuid5(QDRANT_NAMESPACE, sqlite_uri))


def _text_vector(text: str, size: int = QDRANT_VECTOR_SIZE) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(size)]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _symbol_range_text(source_text: str, symbol: dict[str, Any]) -> str:
    start_point = symbol.get("start_point") or {"row": 0, "column": 0}
    end_point = symbol.get("end_point") or start_point
    try:
        start_row = int(start_point.get("row", 0))
        start_column = int(start_point.get("column", 0))
        end_row = int(end_point.get("row", start_row))
        end_column = int(end_point.get("column", start_column))
    except Exception:
        return str(symbol.get("signature", "")).strip()

    lines = source_text.splitlines(keepends=True)
    if not lines:
        return str(symbol.get("signature", "")).strip()

    def offset_for(row: int, column: int) -> int:
        if row <= 0:
            return min(max(column, 0), len(source_text))
        if row >= len(lines):
            return len(source_text)
        offset = sum(len(lines[index]) for index in range(row))
        line = lines[row]
        return min(offset + max(column, 0), offset + len(line))

    start_offset = offset_for(start_row, start_column)
    end_offset = offset_for(end_row, end_column)
    if end_offset < start_offset:
        end_offset = start_offset
    snippet = source_text[start_offset:end_offset].strip()
    return snippet or str(symbol.get("signature", "")).strip()


@dataclass
class QdrantVectorIndex:
    """Best-effort Qdrant projection of the sqlite project index."""

    url: str = QDRANT_DEFAULT_URL
    collection_name: str = QDRANT_DEFAULT_COLLECTION
    vector_size: int = QDRANT_VECTOR_SIZE
    _client: QdrantClient | None = field(default=None, init=False, repr=False)

    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url)
        return self._client

    def ensure_collection(self) -> None:
        client = self.client()
        if client.collection_exists(self.collection_name):
            return
        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def delete_file(self, sqlite_file_uri: str) -> None:
        self.ensure_collection()
        self.client().delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="sqlite_file_uri",
                            match=qmodels.MatchValue(value=sqlite_file_uri),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def delete_project(self, project: str) -> None:
        self.ensure_collection()
        self.client().delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="project_name",
                            match=qmodels.MatchValue(value=project),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def _upsert_points(self, points: list[qmodels.PointStruct]) -> int:
        if not points:
            return 0
        self.ensure_collection()
        self.client().upsert(collection_name=self.collection_name, points=points, wait=True)
        return len(points)

    def _file_payload(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        language: str,
        languages: list[str],
        indexed_at: str,
        file_size: int | None,
        file_mtime_ns: int | None,
        chunk_text: str,
        source_kind: str,
    ) -> dict[str, Any]:
        sqlite_file_uri = _sqlite_file_uri(project, file_id)
        return {
            "project_name": project,
            "project_root": project_root,
            "file_id": file_id,
            "sqlite_file_id": file_id,
            "file_path": file_path,
            "language": language,
            "languages": languages,
            "scope_type": source_kind,
            "source_kind": source_kind,
            "sqlite_uri": sqlite_file_uri,
            "sqlite_file_uri": sqlite_file_uri,
            "sqlite_project_uri": f"sqlite://projects/{_slug_component(project)}",
            "indexed_at": indexed_at,
            "file_size": file_size,
            "file_mtime_ns": file_mtime_ns,
            "content_hash": _content_hash(chunk_text),
            "chunk_text": chunk_text,
            "content_text": chunk_text,
        }

    def _symbol_payload(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        file_language: str,
        file_languages: list[str],
        symbol: dict[str, Any],
        indexed_at: str,
        chunk_text: str,
    ) -> dict[str, Any]:
        symbol_order = int(symbol.get("symbol_order", symbol.get("order", 0)))
        sqlite_file_uri = _sqlite_file_uri(project, file_id)
        sqlite_uri = _sqlite_symbol_uri(project, file_id, symbol_order)
        return {
            "project_name": project,
            "project_root": project_root,
            "file_id": file_id,
            "sqlite_file_id": file_id,
            "file_path": file_path,
            "language": str(file_language),
            "languages": file_languages,
            "scope_type": "symbol",
            "source_kind": "symbol",
            "symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
            "sqlite_symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
            "symbol_order": symbol_order,
            "symbol_name": symbol.get("name", ""),
            "symbol_type": symbol.get("type", ""),
            "signature": symbol.get("signature", ""),
            "start_row": symbol.get("start_point", {}).get("row"),
            "start_column": symbol.get("start_point", {}).get("column"),
            "end_row": symbol.get("end_point", {}).get("row"),
            "end_column": symbol.get("end_point", {}).get("column"),
            "sqlite_uri": sqlite_uri,
            "sqlite_file_uri": sqlite_file_uri,
            "sqlite_project_uri": f"sqlite://projects/{_slug_component(project)}",
            "indexed_at": indexed_at,
            "content_hash": _content_hash(chunk_text),
            "chunk_text": chunk_text,
            "content_text": chunk_text,
        }

    def _build_points_from_analysis(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        analysis: dict[str, Any],
        indexed_at: str,
        file_size: int | None,
        file_mtime_ns: int | None,
    ) -> list[qmodels.PointStruct]:
        parsed = analysis["parsed"]
        file_languages = list(analysis.get("languages", [parsed.language]))
        source_text = parsed.source_code
        file_payload = self._file_payload(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            language=parsed.language,
            languages=file_languages,
            indexed_at=indexed_at,
            file_size=file_size,
            file_mtime_ns=file_mtime_ns,
            chunk_text=source_text,
            source_kind="file",
        )
        points = [
            qmodels.PointStruct(
                id=_stable_point_id(file_payload["sqlite_uri"]),
                vector=_text_vector(source_text, self.vector_size),
                payload=file_payload,
            )
        ]

        for order, symbol in enumerate(analysis.get("symbols", [])):
            symbol_ordered = dict(symbol)
            symbol_ordered.setdefault("symbol_order", order)
            chunk_text = _symbol_range_text(source_text, symbol_ordered)
            payload = self._symbol_payload(
                project=project,
                project_root=project_root,
                file_id=file_id,
                file_path=file_path,
                file_language=parsed.language,
                file_languages=file_languages,
                symbol=symbol_ordered,
                indexed_at=indexed_at,
                chunk_text=chunk_text,
            )
            points.append(
                qmodels.PointStruct(
                    id=_stable_point_id(payload["sqlite_uri"]),
                    vector=_text_vector(chunk_text, self.vector_size),
                    payload=payload,
                )
            )
        return points

    def _build_points_from_records(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_record: dict[str, Any],
        symbol_rows: list[dict[str, Any]],
    ) -> list[qmodels.PointStruct]:
        indexed_at = str(file_record.get("indexed_at") or storage._now())
        file_path = str(file_record["path"])
        file_languages = list(file_record.get("languages", [file_record["language"]]))
        file_payload = self._file_payload(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            language=str(file_record["language"]),
            languages=file_languages,
            indexed_at=indexed_at,
            file_size=file_record.get("file_size"),
            file_mtime_ns=file_record.get("file_mtime_ns"),
            chunk_text=str(file_record.get("skeleton", "")),
            source_kind="file",
        )
        points = [
            qmodels.PointStruct(
                id=_stable_point_id(file_payload["sqlite_uri"]),
                vector=_text_vector(str(file_record.get("skeleton", "")), self.vector_size),
                payload=file_payload,
            )
        ]
        for symbol in symbol_rows:
            symbol_ordered = dict(symbol)
            symbol_ordered.setdefault("symbol_order", symbol_ordered.get("order", 0))
            chunk_text = str(symbol_ordered.get("signature", ""))
            payload = self._symbol_payload(
                project=project,
                project_root=project_root,
                file_id=file_id,
                file_path=file_path,
                file_language=str(file_record["language"]),
                file_languages=file_languages,
                symbol=symbol_ordered,
                indexed_at=indexed_at,
                chunk_text=chunk_text,
            )
            points.append(
                qmodels.PointStruct(
                    id=_stable_point_id(payload["sqlite_uri"]),
                    vector=_text_vector(chunk_text, self.vector_size),
                    payload=payload,
                )
            )
        return points

    def sync_analysis(
        self,
        *,
        project: str,
        project_root: str | Path,
        file_id: int,
        file_path: str,
        analysis: dict[str, Any],
        indexed_at: str,
        file_size: int,
        file_mtime_ns: int,
    ) -> dict[str, Any]:
        project_root_text = str(Path(project_root).resolve())
        sqlite_file_uri = _sqlite_file_uri(project, file_id)
        self.delete_file(sqlite_file_uri)
        points = self._build_points_from_analysis(
            project=project,
            project_root=project_root_text,
            file_id=file_id,
            file_path=file_path,
            analysis=analysis,
            indexed_at=indexed_at,
            file_size=file_size,
            file_mtime_ns=file_mtime_ns,
        )
        upserted = self._upsert_points(points)
        return {
            "synced": True,
            "project": project,
            "file_id": file_id,
            "sqlite_uri": sqlite_file_uri,
            "points": upserted,
        }

    def sync_records(
        self,
        *,
        project: str,
        project_root: str | Path,
        file_id: int,
        file_record: dict[str, Any],
        symbol_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        project_root_text = str(Path(project_root).resolve())
        sqlite_file_uri = _sqlite_file_uri(project, file_id)
        self.delete_file(sqlite_file_uri)
        points = self._build_points_from_records(
            project=project,
            project_root=project_root_text,
            file_id=file_id,
            file_record=file_record,
            symbol_rows=symbol_rows,
        )
        upserted = self._upsert_points(points)
        return {
            "synced": True,
            "project": project,
            "file_id": file_id,
            "sqlite_uri": sqlite_file_uri,
            "points": upserted,
        }

    def bootstrap_project(self, project: str) -> dict[str, Any]:
        project_record = ProjectRepository.load_project_metadata(project)
        if project_record is None:
            return {"project": project, "synced": 0, "files": 0, "points": 0}

        db_path = Path(str(project_record["db_path"]))
        root_path = str(project_record["root_path"])
        if not db_path.exists():
            return {"project": project, "synced": 0, "files": 0, "points": 0, "missing_db": True}

        files_synced = 0
        points = 0
        with storage._connect(db_path) as conn:
            storage._ensure_project_schema(conn)
            rows = conn.execute("SELECT id FROM files ORDER BY rel_path ASC").fetchall()
            for row in rows:
                file_id = int(row["id"])
                file_record = ProjectRepository.read_file_record(conn, file_id)
                symbol_rows = ProjectRepository.symbol_rows(conn, file_id)
                result = self.sync_records(
                    project=project,
                    project_root=root_path,
                    file_id=file_id,
                    file_record=file_record,
                    symbol_rows=symbol_rows,
                )
                files_synced += 1
                points += int(result["points"])
        return {"project": project, "synced": files_synced, "files": files_synced, "points": points}

    def bootstrap_all_projects(self) -> dict[str, Any]:
        if not storage.METADATA_DB.exists():
            return {"projects": 0, "files": 0, "points": 0}

        projects = ProjectRepository.list_projects()
        totals = {"projects": len(projects), "files": 0, "points": 0, "errors": []}
        for project in projects:
            try:
                summary = self.bootstrap_project(str(project["name"]))
            except Exception as exc:  # pragma: no cover - defensive bootstrap guard
                totals["errors"].append({"project": project.get("name"), "error": str(exc)})
                continue
            totals["files"] += int(summary.get("files", 0))
            totals["points"] += int(summary.get("points", 0))
        return totals


_VECTOR_INDEX: QdrantVectorIndex | None = None


def get_vector_index() -> QdrantVectorIndex:
    global _VECTOR_INDEX
    if _VECTOR_INDEX is None:
        _VECTOR_INDEX = QdrantVectorIndex()
    return _VECTOR_INDEX


def bootstrap_existing_projects() -> dict[str, Any]:
    return get_vector_index().bootstrap_all_projects()
