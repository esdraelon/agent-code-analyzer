from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

SCOPE_LEVELS: tuple[str, ...] = ("package", "module", "file", "class", "method", "chunk")
UPDATE_MODES: tuple[str, ...] = ("mass_ingestion", "fswatch_diff")


def normalize_scope_type(scope_type: str) -> str:
    normalized = str(scope_type).strip().lower()
    if normalized not in SCOPE_LEVELS:
        raise ValueError(f"unsupported scope_type: {scope_type!r}")
    return normalized


def _normalize_path_text(file_path: str) -> str:
    path_text = str(file_path).strip().replace("\\", "/")
    while "//" in path_text:
        path_text = path_text.replace("//", "/")
    return path_text.lstrip("./") or "."


def build_semantic_scope_id(
    *,
    project: str,
    scope_type: str,
    file_path: str,
    symbol_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    parent_scope_id: str | None = None,
) -> str:
    """Build a stable scope identity from structural facts only."""

    normalized_scope_type = normalize_scope_type(scope_type)
    components = [
        _normalize_path_text(project),
        normalized_scope_type,
        _normalize_path_text(file_path),
    ]
    if symbol_path:
        components.append(str(symbol_path).strip())
    if line_start is not None:
        components.append(f"start={int(line_start)}")
    if line_end is not None:
        components.append(f"end={int(line_end)}")
    if parent_scope_id:
        components.append(f"parent={parent_scope_id}")
    key = "|".join(components)
    return f"semantic://{_normalize_path_text(project)}/{normalized_scope_type}/{uuid5(NAMESPACE_URL, key)}"


@dataclass(frozen=True, slots=True)
class SemanticDescriptionRecord:
    """Immutable semantic record for a description-bearing code scope."""

    project: str
    scope_type: str
    file_path: str
    description_text: str
    source_fingerprint: str
    scope_id: str | None = None
    symbol_name: str | None = None
    symbol_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    parent_scope_id: str | None = None
    update_mode: str = "mass_ingestion"
    source_kind: str = "tree-sitter"
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        normalized_scope_type = normalize_scope_type(self.scope_type)
        normalized_update_mode = str(self.update_mode).strip().lower()
        if normalized_update_mode not in UPDATE_MODES:
            raise ValueError(f"unsupported update_mode: {self.update_mode!r}")
        object.__setattr__(self, "scope_type", normalized_scope_type)
        object.__setattr__(self, "update_mode", normalized_update_mode)
        if self.scope_id is None:
            object.__setattr__(
                self,
                "scope_id",
                build_semantic_scope_id(
                    project=self.project,
                    scope_type=normalized_scope_type,
                    file_path=self.file_path,
                    symbol_path=self.symbol_path,
                    line_start=self.line_start,
                    line_end=self.line_end,
                    parent_scope_id=self.parent_scope_id,
                ),
            )

    @property
    def has_line_anchors(self) -> bool:
        return self.line_start is not None or self.line_end is not None

    def with_description(self, description_text: str) -> "SemanticDescriptionRecord":
        return SemanticDescriptionRecord(
            project=self.project,
            scope_type=self.scope_type,
            file_path=self.file_path,
            description_text=description_text,
            source_fingerprint=self.source_fingerprint,
            scope_id=self.scope_id,
            symbol_name=self.symbol_name,
            symbol_path=self.symbol_path,
            line_start=self.line_start,
            line_end=self.line_end,
            parent_scope_id=self.parent_scope_id,
            update_mode=self.update_mode,
            source_kind=self.source_kind,
            metadata=dict(self.metadata),
        )


class SemanticDescriptionMapper:
    """Convert semantic records to and from storage payloads."""

    @staticmethod
    def to_payload(record: SemanticDescriptionRecord) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project": record.project,
            "scope_type": record.scope_type,
            "scope_id": record.scope_id,
            "file_path": record.file_path,
            "symbol_name": record.symbol_name,
            "symbol_path": record.symbol_path,
            "line_start": record.line_start,
            "line_end": record.line_end,
            "parent_scope_id": record.parent_scope_id,
            "source_fingerprint": record.source_fingerprint,
            "description_text": record.description_text,
            "update_mode": record.update_mode,
            "source_kind": record.source_kind,
        }
        if record.metadata:
            payload["metadata"] = dict(record.metadata)
        return payload

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> SemanticDescriptionRecord:
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            metadata = {"value": metadata}
        scope_id = payload.get("scope_id")
        if scope_id is not None:
            scope_id = str(scope_id)
        return SemanticDescriptionRecord(
            project=str(payload.get("project", "")),
            scope_type=str(payload.get("scope_type", "")),
            file_path=str(payload.get("file_path", "")),
            description_text=str(payload.get("description_text", "")),
            source_fingerprint=str(payload.get("source_fingerprint", "")),
            scope_id=scope_id,
            symbol_name=payload.get("symbol_name") or None,
            symbol_path=payload.get("symbol_path") or None,
            line_start=payload.get("line_start"),
            line_end=payload.get("line_end"),
            parent_scope_id=payload.get("parent_scope_id") or None,
            update_mode=str(payload.get("update_mode", "mass_ingestion")),
            source_kind=str(payload.get("source_kind", "tree-sitter")),
            metadata=dict(metadata),
        )


def build_semantic_description_record(
    *,
    project: str,
    scope_type: str,
    file_path: str,
    description_text: str,
    source_fingerprint: str,
    symbol_name: str | None = None,
    symbol_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    parent_scope_id: str | None = None,
    update_mode: str = "mass_ingestion",
    source_kind: str = "tree-sitter",
    metadata: Mapping[str, Any] | None = None,
) -> SemanticDescriptionRecord:
    return SemanticDescriptionRecord(
        project=project,
        scope_type=scope_type,
        file_path=file_path,
        description_text=description_text,
        source_fingerprint=source_fingerprint,
        symbol_name=symbol_name,
        symbol_path=symbol_path,
        line_start=line_start,
        line_end=line_end,
        parent_scope_id=parent_scope_id,
        update_mode=update_mode,
        source_kind=source_kind,
        metadata=dict(metadata or {}),
    )
