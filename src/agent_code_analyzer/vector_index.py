from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from qdrant_client import QdrantClient, models as qmodels

from .config import get_config
from . import project_storage as storage
from .embedding_provider import EmbeddingProvider, get_embedding_provider
from .parsing import analyze_file
from .project_repository import ProjectRepository
from .project_row_mapper import ProjectRowMapper
from .search_filters import normalize_exclusions, should_exclude_result
from .search_rank import build_embedding_text, tokenize_text
from .search_scoring import DEFAULT_SEARCH_SCORER
from .freshness import get_freshness_registry
from .semantic_agent import SemanticWriteRequest, SemanticWriter, build_semantic_writer
from .semantic_chunking import build_method_chunk_spans
from .semantic_descriptions import build_semantic_description_record
from .vector_payload_factory import (
    file_payload,
    sqlite_file_uri as factory_sqlite_file_uri,
    sqlite_symbol_uri as factory_sqlite_symbol_uri,
    stable_point_id,
    symbol_payload,
)

_CONFIG = get_config()
QDRANT_DEFAULT_URL = _CONFIG.vector.qdrant_url
QDRANT_DEFAULT_COLLECTION = _CONFIG.vector.qdrant_collection
QDRANT_EMBEDDING_MODEL = _CONFIG.vector.embedding_model
QDRANT_NAMESPACE = uuid.UUID("8d02b10d-0d18-4b93-b3d9-4ff9c1c44c7d")

logger = logging.getLogger(__name__)


def _slug_component(value: str) -> str:
    return quote(storage._normalize_project(value), safe="")


def _sqlite_file_uri(project: str, file_id: int) -> str:
    return f"sqlite://projects/{_slug_component(project)}/files/{file_id}"


def _sqlite_symbol_uri(project: str, file_id: int, symbol_order: int) -> str:
    return f"{factory_sqlite_file_uri(project, file_id)}/symbols/{symbol_order}"


def _sqlite_chunk_uri(project: str, file_id: int, symbol_order: int, chunk_order: int) -> str:
    return f"{_sqlite_symbol_uri(project, file_id, symbol_order)}/chunks/{chunk_order}"


def _stable_point_id(sqlite_uri: str) -> str:
    return str(uuid.uuid5(QDRANT_NAMESPACE, sqlite_uri))


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_unit_type(symbol_type: str, *, fallback: str = "method") -> str:
    normalized = str(symbol_type).strip().lower()
    if not normalized:
        return fallback
    if "class" in normalized or "enum" in normalized or "struct" in normalized or "interface" in normalized:
        return "class"
    if "module" in normalized or "package" in normalized:
        return "module"
    if "file" in normalized:
        return "file"
    if "function" in normalized or "method" in normalized:
        return "method"
    return fallback


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
    embedding_model: str = QDRANT_EMBEDDING_MODEL
    embedding_provider: EmbeddingProvider | None = field(default=None, repr=False)
    semantic_writer: SemanticWriter | None = field(default=None, repr=False)
    _client: QdrantClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.embedding_provider is None:
            self.embedding_provider = get_embedding_provider()
        if self.semantic_writer is None:
            self.semantic_writer = build_semantic_writer()
        logger.info(
            "vector_index_initialized url=%s collection=%s embedding_model=%s embedding_provider=%s semantic_writer=%s",
            self.url,
            self.collection_name,
            self.embedding_model,
            type(self.embedding_provider).__name__ if self.embedding_provider is not None else None,
            type(self.semantic_writer).__name__ if self.semantic_writer is not None else None,
        )

    def _freshness_key(self, payload: dict[str, Any]) -> str:
        return str(payload.get("sqlite_uri") or payload.get("project_name") or payload.get("project") or "")

    def _freshness_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        registry = get_freshness_registry()
        snapshot = registry.snapshot(self._freshness_key(payload))
        return {
            "freshness_state": snapshot.freshness_state,
            "source_revision": snapshot.source_revision,
            "source_hash": snapshot.source_hash,
            "potentially_inaccurate": snapshot.potentially_inaccurate,
            "relevant": snapshot.relevant,
            "dirty_at": snapshot.dirty_at,
        }

    def _mark_payload_dirty(self, payload: dict[str, Any], *, obsolete: bool = False) -> int:
        registry = get_freshness_registry()
        key = self._freshness_key(payload)
        snapshot = registry.mark_obsolete(key) if obsolete else registry.mark_dirty(key)
        return snapshot.source_revision

    def _promote_payload_fresh(self, payload: dict[str, Any], *, observed_revision: int) -> None:
        registry = get_freshness_registry()
        registry.promote_if_current(self._freshness_key(payload), observed_revision=observed_revision)

    @property
    def vector_size(self) -> int:
        assert self.embedding_provider is not None
        return int(self.embedding_provider.vector_size)

    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url, check_compatibility=False)
        return self._client

    def ensure_collection(self) -> None:
        client = self.client()
        if client.collection_exists(self.collection_name):
            return
        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def _embed_document(self, text: str) -> list[float]:
        assert self.embedding_provider is not None
        return self.embedding_provider.embed_document(text)

    def _embed_query(self, text: str) -> list[float]:
        assert self.embedding_provider is not None
        return self.embedding_provider.embed_query(text)

    def _semantic_description_fields(self, result: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "semantic_description_state": "no_response" if getattr(result, "is_no_response", False) else "description",
            "semantic_description_backend": getattr(result, "backend", ""),
        }
        description_text = getattr(result, "description_text", None)
        if description_text:
            fields["description_text"] = description_text
        return fields

    def _semantic_payload_freshness(self, payload: dict[str, Any], *, obsolete: bool = False) -> dict[str, Any]:
        revision = self._mark_payload_dirty(payload, obsolete=obsolete)
        return {"freshness_revision": revision, **self._freshness_fields(payload)}

    def _chunk_payload(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        file_language: str,
        file_languages: list[str],
        indexed_at: str,
        chunk_text: str,
        parent_symbol: dict[str, Any],
        chunk_index: int,
        chunk_total: int,
        line_start: int,
        line_end: int,
        split_reason: str,
        parent_scope_id: str,
    ) -> dict[str, Any]:
        symbol_order = int(parent_symbol.get("symbol_order", parent_symbol.get("order", 0)))
        sqlite_file_uri_value = factory_sqlite_file_uri(project, file_id)
        sqlite_symbol_uri_value = _sqlite_symbol_uri(project, file_id, symbol_order)
        sqlite_uri = _sqlite_chunk_uri(project, file_id, symbol_order, chunk_index)
        parent_symbol_name = str(parent_symbol.get("name", ""))
        parent_symbol_type = str(parent_symbol.get("type", ""))
        return {
            "project_name": project,
            "project_root": project_root,
            "file_id": file_id,
            "sqlite_file_id": file_id,
            "file_path": file_path,
            "language": file_language,
            "languages": file_languages,
            "scope_type": "chunk",
            "source_kind": "chunk",
            "unit_type": "chunk",
            "symbol_id": parent_symbol.get("sqlite_symbol_id", parent_symbol.get("id")),
            "sqlite_symbol_id": parent_symbol.get("sqlite_symbol_id", parent_symbol.get("id")),
            "symbol_order": symbol_order,
            "symbol_name": parent_symbol_name,
            "symbol_type": parent_symbol_type,
            "parent_scope_id": parent_scope_id,
            "parent_symbol_name": parent_symbol_name,
            "parent_symbol_type": parent_symbol_type,
            "parent_symbol_order": symbol_order,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "chunk_strategy": split_reason,
            "start_row": line_start,
            "start_column": 0,
            "end_row": line_end,
            "end_column": 0,
            "sqlite_uri": sqlite_uri,
            "sqlite_file_uri": sqlite_file_uri_value,
            "sqlite_symbol_uri": sqlite_symbol_uri_value,
            "sqlite_project_uri": f"sqlite://projects/{_slug_component(project)}",
            "indexed_at": indexed_at,
            "content_hash": _content_hash(chunk_text),
            "chunk_text": chunk_text,
            "content_text": chunk_text,
            "signature": str(parent_symbol.get("signature", "")),
        }

    def _write_semantic_description(
        self,
        *,
        project: str,
        scope_type: str,
        file_path: str,
        source_text: str,
        outline_text: str,
        line_start: int | None,
        line_end: int | None,
        symbol_path: str | None = None,
        parent_scope_id: str | None = None,
        source_kind: str = "tree-sitter",
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        record = build_semantic_description_record(
            project=project,
            scope_type=scope_type,
            file_path=file_path,
            description_text="",
            source_fingerprint=_content_hash(source_text),
            symbol_path=symbol_path,
            line_start=line_start,
            line_end=line_end,
            parent_scope_id=parent_scope_id,
            source_kind=source_kind,
            metadata=metadata or {},
        )
        request = SemanticWriteRequest(
            record=record,
            source_text=source_text,
            outline_text=outline_text,
            metadata=metadata or {},
        )
        writer = self.semantic_writer
        assert writer is not None
        logger.debug(
            "vector_index_semantic_write project=%s scope_type=%s file_path=%s symbol_path=%s parent_scope_id=%s source_kind=%s",
            project,
            scope_type,
            file_path,
            symbol_path,
            parent_scope_id,
            source_kind,
        )
        return writer.write(request)

    def _module_name_from_path(self, project_root: str, file_path: str) -> str:
        project_root_path = Path(project_root).resolve()
        file_path_path = Path(file_path).resolve()
        try:
            relative = file_path_path.relative_to(project_root_path)
        except Exception:
            relative = file_path_path
        relative = relative.with_suffix("")
        parts = [part for part in relative.parts if part not in {".", ".."}]
        if not parts:
            return file_path_path.stem or "module"
        return ".".join(parts)

    def _build_package_module_points(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        file_language: str,
        file_languages: list[str],
        indexed_at: str,
        source_text: str,
        outline_text: str,
        root_type: str,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
    ) -> list[qmodels.PointStruct]:
        project_slug = _slug_component(project)
        package_sqlite_uri = f"sqlite://projects/{project_slug}/package"
        package_source = f"Project {project}\nRoot: {project_root}\nFile: {file_path}"
        package_outline = outline_text.strip() or root_type or project
        package_record = build_semantic_description_record(
            project=project,
            scope_type="package",
            file_path=project_root,
            description_text="",
            source_fingerprint=_content_hash(package_source),
            symbol_name=project,
            symbol_path=project,
            parent_scope_id=None,
            update_mode="mass_ingestion",
            source_kind="package",
            metadata={"project_root": project_root, "file_path": file_path, "language": file_language},
        )
        package_description = self._write_semantic_description(
            project=project,
            scope_type="package",
            file_path=project_root,
            source_text=package_source,
            outline_text=package_outline,
            line_start=None,
            line_end=None,
            symbol_path=project,
            parent_scope_id=None,
            source_kind="package",
            metadata={"project_root": project_root, "file_path": file_path, "language": file_language},
        )
        package_payload = {
            "project_name": project,
            "project_root": project_root,
            "file_id": file_id,
            "sqlite_file_id": file_id,
            "file_path": project_root,
            "language": file_language,
            "languages": file_languages,
            "scope_type": "package",
            "source_kind": "package",
            "unit_type": "package",
            "symbol_id": project,
            "sqlite_symbol_id": project,
            "symbol_order": 0,
            "symbol_name": project,
            "symbol_type": "package",
            "root_type": root_type,
            "start_row": None,
            "start_column": None,
            "end_row": None,
            "end_column": None,
            "sqlite_uri": package_sqlite_uri,
            "scope_id": package_record.scope_id,
            "sqlite_file_uri": f"sqlite://projects/{project_slug}",
            "indexed_at": indexed_at,
            "content_hash": _content_hash(package_source),
            "chunk_text": package_outline,
            "content_text": package_source,
            "symbol_path": project,
        }
        package_payload.update(self._semantic_description_fields(package_description))
        package_payload.update(self._freshness_fields(package_payload))

        module_name = self._module_name_from_path(project_root, file_path)
        module_sqlite_uri = f"{factory_sqlite_file_uri(project, file_id)}/module"
        module_source = source_text or outline_text or file_path
        module_outline = outline_text.strip() or module_name
        module_record = build_semantic_description_record(
            project=project,
            scope_type="module",
            file_path=file_path,
            description_text="",
            source_fingerprint=_content_hash(module_source),
            symbol_name=module_name,
            symbol_path=module_name,
            line_start=start_row,
            line_end=end_row,
            parent_scope_id=package_record.scope_id,
            update_mode="mass_ingestion",
            source_kind="module",
            metadata={"module_name": module_name, "file_path": file_path, "language": file_language},
        )
        module_description = self._write_semantic_description(
            project=project,
            scope_type="module",
            file_path=file_path,
            source_text=module_source,
            outline_text=module_outline,
            line_start=start_row,
            line_end=end_row,
            symbol_path=module_name,
            parent_scope_id=package_record.scope_id,
            source_kind="module",
            metadata={"module_name": module_name, "file_path": file_path, "language": file_language},
        )
        module_payload = file_payload(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            language=file_language,
            languages=file_languages,
            root_type=root_type,
            start_row=start_row,
            start_column=start_column,
            end_row=end_row,
            end_column=end_column,
            indexed_at=indexed_at,
            file_size=None,
            file_mtime_ns=None,
            chunk_text=module_outline,
            source_kind="module",
        )
        module_payload.update(
            {
                "scope_type": "module",
                "source_kind": "module",
                "unit_type": "module",
                "symbol_name": module_name,
                "symbol_type": "module",
                "symbol_path": module_name,
                "sqlite_uri": module_sqlite_uri,
                "scope_id": module_record.scope_id,
                "content_hash": _content_hash(module_source),
                "parent_scope_id": package_record.scope_id,
            }
        )
        module_payload.update(self._semantic_description_fields(module_description))
        module_payload.update(self._freshness_fields(module_payload))

        return [
            qmodels.PointStruct(
                id=_stable_point_id(package_payload["sqlite_uri"]),
                vector=self._embed_document(
                    build_embedding_text(file_path=project_root, skeleton=package_outline, source_text=package_source)
                ),
                payload=package_payload,
            ),
            qmodels.PointStruct(
                id=_stable_point_id(module_payload["sqlite_uri"]),
                vector=self._embed_document(
                    build_embedding_text(file_path=file_path, symbol_name=module_name, signature=module_outline, source_text=module_source)
                ),
                payload=module_payload,
            ),
        ]

    def _build_chunk_points(
        self,
        *,
        parsed: Any,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        file_language: str,
        file_languages: list[str],
        indexed_at: str,
        parent_symbol: dict[str, Any],
        parent_description: Any,
    ) -> list[qmodels.PointStruct]:
        parent_scope_id = getattr(getattr(parent_description, "request", None), "record", None)
        parent_scope_id_text = getattr(parent_scope_id, "scope_id", None)
        if not parent_scope_id_text:
            return []
        chunk_spans = build_method_chunk_spans(parsed, parent_symbol)
        if not chunk_spans:
            return []

        points: list[qmodels.PointStruct] = []
        parent_symbol_name = str(parent_symbol.get("name", "")) or None
        symbol_path_root = parent_symbol_name or str(parent_symbol.get("type", "method"))
        for chunk in chunk_spans:
            chunk_symbol_path = f"{symbol_path_root}::chunk-{chunk.chunk_index}"
            chunk_description = self._write_semantic_description(
                project=project,
                scope_type="chunk",
                file_path=file_path,
                source_text=chunk.chunk_text or file_path,
                outline_text=chunk.outline_text,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                symbol_path=chunk_symbol_path,
                parent_scope_id=parent_scope_id_text,
                source_kind="tree-sitter",
                metadata={
                    "chunk_index": chunk.chunk_index,
                    "chunk_total": chunk.chunk_total,
                    "split_reason": chunk.split_reason,
                    "is_split": chunk.is_split,
                    "statement_count": chunk.statement_count,
                    "parent_symbol_type": str(parent_symbol.get("type", "")),
                },
            )
            payload = self._chunk_payload(
                project=project,
                project_root=project_root,
                file_id=file_id,
                file_path=file_path,
                file_language=file_language,
                file_languages=file_languages,
                indexed_at=indexed_at,
                chunk_text=chunk.chunk_text or file_path,
                parent_symbol=parent_symbol,
                chunk_index=chunk.chunk_index,
                chunk_total=chunk.chunk_total,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                split_reason=chunk.split_reason,
                parent_scope_id=parent_scope_id_text,
            )
            payload.update(self._semantic_description_fields(chunk_description))
            payload.update(self._freshness_fields(payload))
            points.append(
                qmodels.PointStruct(
                    id=_stable_point_id(payload["sqlite_uri"]),
                    vector=self._embed_document(
                        build_embedding_text(
                            file_path=file_path,
                            symbol_name=parent_symbol_name or "",
                            signature=chunk.outline_text,
                            source_text=chunk.chunk_text,
                        )
                    ),
                    payload=payload,
                )
            )
        return points

    def _make_point(
        self,
        *,
        project: str,
        project_root: str,
        file_id: int,
        file_path: str,
        language: str,
        languages: list[str],
        root_type: str = "",
        start_row: int = 0,
        start_column: int = 0,
        end_row: int = 0,
        end_column: int = 0,
        indexed_at: str,
        file_size: int | None,
        file_mtime_ns: int | None,
        chunk_text: str,
        source_kind: str,
        sqlite_uri: str | None = None,
        symbol: dict[str, Any] | None = None,
        is_query: bool = False,
    ) -> qmodels.PointStruct:
        if source_kind == "file":
            payload = file_payload(
                project=project,
                project_root=project_root,
                file_id=file_id,
                file_path=file_path,
                language=language,
                languages=languages,
                root_type=root_type,
                start_row=start_row,
                start_column=start_column,
                end_row=end_row,
                end_column=end_column,
                indexed_at=indexed_at,
                file_size=file_size,
                file_mtime_ns=file_mtime_ns,
                chunk_text=chunk_text,
                source_kind=source_kind,
            )
        else:
            assert symbol is not None
            payload = symbol_payload(
                project=project,
                project_root=project_root,
                file_id=file_id,
                file_path=file_path,
                file_language=language,
                file_languages=languages,
                symbol=symbol,
                root_type=root_type,
                indexed_at=indexed_at,
                chunk_text=chunk_text,
            )
        point_uri = sqlite_uri or str(payload["sqlite_uri"])
        return qmodels.PointStruct(
            id=stable_point_id(point_uri),
            vector=self._embed_query(chunk_text) if is_query else self._embed_document(chunk_text),
            payload=payload,
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
        root_type: str,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
        indexed_at: str,
        file_size: int | None,
        file_mtime_ns: int | None,
        chunk_text: str,
        source_kind: str,
    ) -> dict[str, Any]:
        sqlite_file_uri = factory_sqlite_file_uri(project, file_id)
        return {
            "project_name": project,
            "project_root": project_root,
            "file_id": file_id,
            "sqlite_file_id": file_id,
            "file_path": file_path,
            "language": language,
            "languages": languages,
            "root_type": root_type,
            "start_row": start_row,
            "start_column": start_column,
            "end_row": end_row,
            "end_column": end_column,
            "scope_type": source_kind,
            "source_kind": source_kind,
            "unit_type": source_kind,
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
        root_type: str = "",
        indexed_at: str,
        chunk_text: str,
    ) -> dict[str, Any]:
        symbol_order = int(symbol.get("symbol_order", symbol.get("order", 0)))
        sqlite_file_uri = factory_sqlite_file_uri(project, file_id)
        sqlite_uri = factory_sqlite_symbol_uri(project, file_id, symbol_order)
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
            "unit_type": _normalize_unit_type(str(symbol.get("type", ""))),
            "symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
            "sqlite_symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
            "symbol_order": symbol_order,
            "symbol_name": symbol.get("name", ""),
            "symbol_type": symbol.get("type", ""),
            "root_type": root_type,
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
        root_node = parsed.tree.root_node
        file_languages = list(analysis.get("languages", [parsed.language]))
        source_text = parsed.source_code
        package_module_points = self._build_package_module_points(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            file_language=parsed.language,
            file_languages=file_languages,
            indexed_at=indexed_at,
            source_text=source_text,
            outline_text=str(analysis.get("skeleton", "")),
            root_type=root_node.type,
            start_row=int(root_node.start_point[0]),
            start_column=int(root_node.start_point[1]),
            end_row=int(root_node.end_point[0]),
            end_column=int(root_node.end_point[1]),
        )
        module_point_payload = package_module_points[1].payload or {}
        module_scope_id = str(module_point_payload.get("scope_id", ""))
        file_embedding_text = build_embedding_text(
            file_path=file_path,
            skeleton=f"{root_node.type}\n{analysis.get('skeleton', '')}",
            source_text=source_text,
        )
        file_payload = self._file_payload(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            language=parsed.language,
            languages=file_languages,
            root_type=root_node.type,
            start_row=int(root_node.start_point[0]),
            start_column=int(root_node.start_point[1]),
            end_row=int(root_node.end_point[0]),
            end_column=int(root_node.end_point[1]),
            indexed_at=indexed_at,
            file_size=file_size,
            file_mtime_ns=file_mtime_ns,
            chunk_text=source_text,
            source_kind="file",
        )
        file_description = self._write_semantic_description(
            project=project,
            scope_type="file",
            file_path=file_path,
            source_text=source_text,
            outline_text=str(analysis.get("skeleton", "")),
            line_start=int(root_node.start_point[0]),
            line_end=int(root_node.end_point[0]),
            parent_scope_id=module_scope_id or None,
            source_kind="tree-sitter",
            metadata={"root_type": root_node.type, "language": parsed.language},
        )
        file_payload.update(self._semantic_description_fields(file_description))
        file_payload.update(self._freshness_fields(file_payload))
        file_payload["parent_scope_id"] = module_scope_id or None
        points = [
            *package_module_points,
            qmodels.PointStruct(
                id=_stable_point_id(file_payload["sqlite_uri"]),
                vector=self._embed_document(file_embedding_text),
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
                root_type=root_node.type,
                indexed_at=indexed_at,
                chunk_text=chunk_text,
            )
            symbol_description = self._write_semantic_description(
                project=project,
                scope_type=_normalize_unit_type(str(symbol_ordered.get("type", ""))),
                file_path=file_path,
                source_text=chunk_text or source_text,
                outline_text=str(symbol_ordered.get("signature", "")),
                line_start=symbol_ordered.get("start_point", {}).get("row"),
                line_end=symbol_ordered.get("end_point", {}).get("row"),
                symbol_path=str(symbol_ordered.get("name", "")) or None,
                parent_scope_id=str(file_description.request.record.scope_id),
                source_kind="tree-sitter",
                metadata={"symbol_type": symbol_ordered.get("type", "")},
            )
            payload.update(self._semantic_description_fields(symbol_description))
            payload.update(self._freshness_fields(payload))
            payload["parent_scope_id"] = str(file_description.request.record.scope_id)
            symbol_embedding_text = build_embedding_text(
                file_path=file_path,
                symbol_name=str(symbol_ordered.get("name", "")),
                signature=str(symbol_ordered.get("signature", "")),
                source_text=chunk_text,
            )
            points.append(
                qmodels.PointStruct(
                    id=_stable_point_id(payload["sqlite_uri"]),
                    vector=self._embed_document(symbol_embedding_text),
                    payload=payload,
                )
            )

            if _normalize_unit_type(str(symbol_ordered.get("type", ""))) == "method":
                points.extend(
                    self._build_chunk_points(
                        parsed=parsed,
                        project=project,
                        project_root=project_root,
                        file_id=file_id,
                        file_path=file_path,
                        file_language=parsed.language,
                        file_languages=file_languages,
                        indexed_at=indexed_at,
                        parent_symbol=symbol_ordered,
                        parent_description=symbol_description,
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
        parsed = None
        abs_path = str(file_record.get("abs_path") or "")
        if abs_path and Path(abs_path).exists():
            try:
                parsed = analyze_file(abs_path)["parsed"]
            except Exception:
                parsed = None
        root_type = str(file_record.get("root_type", ""))
        start_row = int(file_record.get("start_point", {}).get("row", 0))
        start_column = int(file_record.get("start_point", {}).get("column", 0))
        end_row = int(file_record.get("end_point", {}).get("row", 0))
        end_column = int(file_record.get("end_point", {}).get("column", 0))
        package_module_points = self._build_package_module_points(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            file_language=str(file_record["language"]),
            file_languages=file_languages,
            indexed_at=indexed_at,
            source_text=str(file_record.get("skeleton", "")) or file_path,
            outline_text=f"{root_type}\n{str(file_record.get('skeleton', ''))}",
            root_type=root_type,
            start_row=start_row,
            start_column=start_column,
            end_row=end_row,
            end_column=end_column,
        )
        module_point_payload = package_module_points[1].payload or {}
        module_scope_id = str(module_point_payload.get("scope_id", ""))
        file_payload = self._file_payload(
            project=project,
            project_root=project_root,
            file_id=file_id,
            file_path=file_path,
            language=str(file_record["language"]),
            languages=file_languages,
            root_type=root_type,
            start_row=start_row,
            start_column=start_column,
            end_row=end_row,
            end_column=end_column,
            indexed_at=indexed_at,
            file_size=file_record.get("file_size"),
            file_mtime_ns=file_record.get("file_mtime_ns"),
            chunk_text=str(file_record.get("skeleton", "")),
            source_kind="file",
        )
        file_description = self._write_semantic_description(
            project=project,
            scope_type="file",
            file_path=file_path,
            source_text=str(file_record.get("skeleton", "")) or file_path,
            outline_text=f"{str(file_record.get('root_type', ''))}\n{str(file_record.get('skeleton', ''))}",
            line_start=start_row,
            line_end=end_row,
            parent_scope_id=module_scope_id or None,
            source_kind="tree-sitter",
            metadata={"root_type": file_record.get("root_type", ""), "language": file_record["language"]},
        )
        file_payload.update(self._semantic_description_fields(file_description))
        file_payload.update(self._freshness_fields(file_payload))
        file_payload["parent_scope_id"] = module_scope_id or None
        file_embedding_text = build_embedding_text(
            file_path=file_path,
            skeleton=f"{str(file_record.get('root_type', ''))}\n{str(file_record.get('skeleton', ''))}",
        )
        points = [
            *package_module_points,
            qmodels.PointStruct(
                id=_stable_point_id(file_payload["sqlite_uri"]),
                vector=self._embed_document(file_embedding_text),
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
                root_type=str(file_record.get("root_type", "")),
                indexed_at=indexed_at,
                chunk_text=chunk_text,
            )
            symbol_description = self._write_semantic_description(
                project=project,
                scope_type=_normalize_unit_type(str(symbol_ordered.get("type", ""))),
                file_path=file_path,
                source_text=chunk_text or file_path,
                outline_text=str(symbol_ordered.get("signature", "")),
                line_start=symbol_ordered.get("start_point", {}).get("row"),
                line_end=symbol_ordered.get("end_point", {}).get("row"),
                symbol_path=str(symbol_ordered.get("name", "")) or None,
                parent_scope_id=str(file_description.request.record.scope_id),
                source_kind="tree-sitter",
                metadata={"symbol_type": symbol_ordered.get("type", "")},
            )
            payload.update(self._semantic_description_fields(symbol_description))
            payload.update(self._freshness_fields(payload))
            payload["parent_scope_id"] = str(file_description.request.record.scope_id)
            symbol_embedding_text = build_embedding_text(
                file_path=file_path,
                symbol_name=str(symbol_ordered.get("name", "")),
                signature=chunk_text,
            )
            points.append(
                qmodels.PointStruct(
                    id=_stable_point_id(payload["sqlite_uri"]),
                    vector=self._embed_document(symbol_embedding_text),
                    payload=payload,
                )
            )

            if parsed is not None and _normalize_unit_type(str(symbol_ordered.get("type", ""))) == "method":
                points.extend(
                    self._build_chunk_points(
                        parsed=parsed,
                        project=project,
                        project_root=project_root,
                        file_id=file_id,
                        file_path=file_path,
                        file_language=str(file_record["language"]),
                        file_languages=file_languages,
                        indexed_at=indexed_at,
                        parent_symbol=symbol_ordered,
                        parent_description=symbol_description,
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
        sqlite_file_uri = factory_sqlite_file_uri(project, file_id)
        logger.info(
            "vector_index_sync_analysis project=%s file_id=%d file_path=%s file_size=%d file_mtime_ns=%d sqlite_uri=%s",
            project,
            file_id,
            file_path,
            file_size,
            file_mtime_ns,
            sqlite_file_uri,
        )
        observed_revision = self._mark_payload_dirty({"sqlite_uri": sqlite_file_uri})
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
        self._promote_payload_fresh({"sqlite_uri": sqlite_file_uri}, observed_revision=observed_revision)
        logger.info(
            "vector_index_sync_complete project=%s file_id=%d sqlite_uri=%s points=%d",
            project,
            file_id,
            sqlite_file_uri,
            upserted,
        )
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
        sqlite_file_uri = factory_sqlite_file_uri(project, file_id)
        observed_revision = self._mark_payload_dirty({"sqlite_uri": sqlite_file_uri})
        self.delete_file(sqlite_file_uri)
        points = self._build_points_from_records(
            project=project,
            project_root=project_root_text,
            file_id=file_id,
            file_record=file_record,
            symbol_rows=symbol_rows,
        )
        upserted = self._upsert_points(points)
        self._promote_payload_fresh({"sqlite_uri": sqlite_file_uri}, observed_revision=observed_revision)
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

    def search(
        self,
        query: str,
        *,
        project: str | None = None,
        scope_type: str | None = None,
        limit: int = 10,
        exclude_files: list[str] | None = None,
        exclude_symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        needle = query.strip()
        if not needle:
            raise ValueError("query must not be empty")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        logger.info(
            "vector_index_search query=%r project=%r scope_type=%r limit=%d",
            needle,
            project,
            scope_type,
            limit,
        )
        self.ensure_collection()
        conditions: list[qmodels.FieldCondition] = []
        if project:
            conditions.append(
                qmodels.FieldCondition(
                    key="project_name",
                    match=qmodels.MatchValue(value=project),
                )
            )
        if scope_type:
            conditions.append(
                qmodels.FieldCondition(
                    key="scope_type",
                    match=qmodels.MatchValue(value=scope_type),
                )
            )
        query_filter = qmodels.Filter(must=conditions) if conditions else None
        response = self.client().query_points(
            collection_name=self.collection_name,
            query=self._embed_query(needle),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        points = getattr(response, "points", response) or []
        excluded_files = normalize_exclusions(exclude_files)
        excluded_symbols = normalize_exclusions(exclude_symbols)
        results: list[dict[str, Any]] = []
        for point in points:
            payload = dict(getattr(point, "payload", {}) or {})
            result = {
                "score": float(getattr(point, "score", 0.0)),
                **payload,
            }
            result.update(self._freshness_fields(result))
            result["score"] = DEFAULT_SEARCH_SCORER.score(
                needle,
                base_score=float(result["score"]),
                searchable_text=str(result.get("content_text", ""))
                + " "
                + str(result.get("chunk_text", ""))
                + " "
                + str(result.get("signature", "")),
                file_path=str(result.get("file_path", "")),
                symbol_name=str(result.get("symbol_name", "")),
                unit_type=str(result.get("unit_type", "")),
                content_text=str(result.get("content_text", "")),
            )
            if should_exclude_result(result, exclude_files=excluded_files, exclude_symbols=excluded_symbols):
                continue
            results.append(result)
        results.sort(
            key=lambda item: (
                -float(item["score"]),
                item.get("scope_type") != "symbol",
                item.get("symbol_name", ""),
                item.get("file_path", ""),
            )
        )
        return {
            "query": needle,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "results": results,
        }

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
