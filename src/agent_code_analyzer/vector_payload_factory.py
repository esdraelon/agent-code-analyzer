from __future__ import annotations

import hashlib
import uuid
from typing import Any
from urllib.parse import quote

from . import project_storage as storage

QDRANT_NAMESPACE = uuid.UUID("8d02b10d-0d18-4b93-b3d9-4ff9c1c44c7d")


def slug_component(value: str) -> str:
    return quote(storage._normalize_project(value), safe="")


def sqlite_file_uri(project: str, file_id: int) -> str:
    return f"sqlite://projects/{slug_component(project)}/files/{file_id}"


def sqlite_symbol_uri(project: str, file_id: int, symbol_order: int) -> str:
    return f"{sqlite_file_uri(project, file_id)}/symbols/{symbol_order}"


def stable_point_id(sqlite_uri: str) -> str:
    return str(uuid.uuid5(QDRANT_NAMESPACE, sqlite_uri))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_unit_type(symbol_type: str, *, fallback: str = "method") -> str:
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


def file_payload(
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
    sqlite_uri = sqlite_file_uri(project, file_id)
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
        "unit_type": source_kind,
        "sqlite_uri": sqlite_uri,
        "sqlite_file_uri": sqlite_uri,
        "sqlite_project_uri": f"sqlite://projects/{slug_component(project)}",
        "indexed_at": indexed_at,
        "file_size": file_size,
        "file_mtime_ns": file_mtime_ns,
        "content_hash": content_hash(chunk_text),
        "chunk_text": chunk_text,
        "content_text": chunk_text,
    }


def symbol_payload(
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
    sqlite_file_uri_value = sqlite_file_uri(project, file_id)
    sqlite_uri = sqlite_symbol_uri(project, file_id, symbol_order)
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
        "unit_type": normalize_unit_type(str(symbol.get("type", ""))),
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
        "sqlite_file_uri": sqlite_file_uri_value,
        "sqlite_project_uri": f"sqlite://projects/{slug_component(project)}",
        "indexed_at": indexed_at,
        "content_hash": content_hash(chunk_text),
        "chunk_text": chunk_text,
        "content_text": chunk_text,
    }
