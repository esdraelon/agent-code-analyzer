from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class SourceLink:
    project: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        params: list[str] = []
        if self.start_line is not None:
            params.append(f"start_line={self.start_line}")
        if self.end_line is not None:
            params.append(f"end_line={self.end_line}")
        if self.symbol_name:
            params.append(f"symbol_name={quote(self.symbol_name)}")
        query = f"?{'&'.join(params)}" if params else ""
        return {
            "project": self.project,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "href": f"/api/projects/{quote(self.project)}/files/{quote(self.file_path, safe='/')}" f"{query}",
        }


@dataclass(frozen=True, slots=True)
class ProjectListItem:
    name: str
    root_path: str
    mode: str
    description: str
    created_at: str
    updated_at: str
    indexed_at: str | None
    file_count: int
    supported_file_count: int
    symbol_count: int
    languages: list[str] = field(default_factory=list)
    status: str = "idle"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root_path": self.root_path,
            "mode": self.mode,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "indexed_at": self.indexed_at,
            "file_count": self.file_count,
            "supported_file_count": self.supported_file_count,
            "symbol_count": self.symbol_count,
            "languages": list(self.languages),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class IngestionJob:
    project: str
    job_id: str
    action: str
    phase: str
    status: str
    queued_at: str
    started_at: str | None
    updated_at: str
    completed_at: str | None
    total_count: int
    processed_count: int
    last_file_path: str | None
    last_file_mtime_ns: int | None
    last_file_content_hash: str
    last_error: str

    def percent_complete(self) -> float:
        if self.total_count <= 0:
            return 0.0
        return round(min(100.0, (self.processed_count / self.total_count) * 100.0), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "job_id": self.job_id,
            "action": self.action,
            "phase": self.phase,
            "status": self.status,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "total_count": self.total_count,
            "processed_count": self.processed_count,
            "percent_complete": self.percent_complete(),
            "last_file_path": self.last_file_path,
            "last_file_mtime_ns": self.last_file_mtime_ns,
            "last_file_content_hash": self.last_file_content_hash,
            "last_error": self.last_error,
        }


@dataclass(frozen=True, slots=True)
class SearchResultEnvelope:
    index_type: str
    scope_type: str | None
    project: str | None
    file_path: str | None
    symbol_name: str | None
    start_row: int | None
    start_column: int | None
    end_row: int | None
    end_column: int | None
    sqlite_uri: str | None
    score: float | None
    source_link: SourceLink | None = None
    related_index_links: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "index_type": self.index_type,
            "scope_type": self.scope_type,
            "project": self.project,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "start_row": self.start_row,
            "start_column": self.start_column,
            "end_row": self.end_row,
            "end_column": self.end_column,
            "sqlite_uri": self.sqlite_uri,
            "score": self.score,
            "source_link": self.source_link.to_dict() if self.source_link is not None else None,
            "related_index_links": list(self.related_index_links),
        }
        payload.update(self.extra)
        return payload
