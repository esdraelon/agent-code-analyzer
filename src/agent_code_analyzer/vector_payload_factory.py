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


def normalize_path_text(path_text: str) -> str:
    normalized = str(path_text).strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized.lstrip("./")


def path_prefixes(path_text: str, *, separator: str = "/") -> list[str]:
    normalized = normalize_path_text(path_text).strip(separator)
    if not normalized:
        return []
    prefixes: list[str] = []
    current: list[str] = []
    for part in normalized.split(separator):
        if not part:
            continue
        current.append(part)
        prefixes.append(separator.join(current))
    return prefixes


def directory_path(file_path: str) -> str:
    normalized = normalize_path_text(file_path)
    if "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def directory_ancestors(file_path: str) -> list[str]:
    directory = directory_path(file_path)
    return path_prefixes(directory) if directory else []


def scope_path(scope_type: str, *, file_path: str, symbol_name: str = "", chunk_index: int | None = None) -> str:
    normalized_scope_type = str(scope_type).strip().lower()
    if normalized_scope_type == "file":
        return normalize_path_text(file_path)
    if normalized_scope_type == "chunk":
        root = str(symbol_name).strip() or normalize_path_text(file_path)
        if chunk_index is None:
            return root
        return f"{root}::chunk-{int(chunk_index)}"
    symbol_name = str(symbol_name).strip()
    return symbol_name or normalize_path_text(file_path)


def scope_path_ancestors(scope_path_value: str) -> list[str]:
    normalized = normalize_path_text(scope_path_value).strip("/")
    if not normalized:
        return []
    prefixes: list[str] = []
    current: list[str] = []
    for part in normalized.split("::"):
        if not part:
            continue
        current.append(part)
        prefixes.append("::".join(current))
    return prefixes


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
    root_type: str = "",
    start_row: int,
    start_column: int,
    end_row: int,
    end_column: int,
    indexed_at: str,
    file_size: int | None,
    file_mtime_ns: int | None,
    chunk_text: str,
    source_kind: str,
    directory_path_value: str | None = None,
    directory_ancestors_value: list[str] | None = None,
    scope_path_value: str | None = None,
    scope_path_ancestors_value: list[str] | None = None,
) -> dict[str, Any]:
    sqlite_uri = sqlite_file_uri(project, file_id)
    normalized_file_path = normalize_path_text(file_path)
    directory_path_text = directory_path_value if directory_path_value is not None else directory_path(normalized_file_path)
    directory_ancestor_list = directory_ancestors_value if directory_ancestors_value is not None else directory_ancestors(normalized_file_path)
    scope_path_text = scope_path_value if scope_path_value is not None else scope_path(source_kind, file_path=normalized_file_path, symbol_name=root_type)
    scope_ancestor_list = scope_path_ancestors_value if scope_path_ancestors_value is not None else scope_path_ancestors(scope_path_text)
    return {
        "project_name": project,
        "project_root": project_root,
        "file_id": file_id,
        "sqlite_file_id": file_id,
        "file_path": normalized_file_path,
        "directory_path": directory_path_text,
        "directory_ancestors": directory_ancestor_list,
        "scope_path": scope_path_text,
        "scope_path_ancestors": scope_ancestor_list,
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
    root_type: str = "",
    indexed_at: str,
    chunk_text: str,
    scope_path_value: str | None = None,
    scope_path_ancestors_value: list[str] | None = None,
) -> dict[str, Any]:
    symbol_order = int(symbol.get("symbol_order", symbol.get("order", 0)))
    sqlite_file_uri_value = sqlite_file_uri(project, file_id)
    sqlite_uri = sqlite_symbol_uri(project, file_id, symbol_order)
    normalized_file_path = normalize_path_text(file_path)
    symbol_name = str(symbol.get("name", "")).strip()
    scope_path_text = scope_path_value if scope_path_value is not None else scope_path("symbol", file_path=normalized_file_path, symbol_name=symbol_name)
    scope_ancestor_list = scope_path_ancestors_value if scope_path_ancestors_value is not None else scope_path_ancestors(scope_path_text)
    directory_path_text = directory_path(normalized_file_path)
    directory_ancestor_list = directory_ancestors(normalized_file_path)
    return {
        "project_name": project,
        "project_root": project_root,
        "file_id": file_id,
        "sqlite_file_id": file_id,
        "file_path": normalized_file_path,
        "directory_path": directory_path_text,
        "directory_ancestors": directory_ancestor_list,
        "scope_path": scope_path_text,
        "scope_path_ancestors": scope_ancestor_list,
        "language": str(file_language),
        "languages": file_languages,
        "scope_type": "symbol",
        "source_kind": "symbol",
        "unit_type": normalize_unit_type(str(symbol.get("type", ""))),
        "symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
        "sqlite_symbol_id": symbol.get("sqlite_symbol_id", symbol.get("id")),
        "symbol_order": symbol_order,
        "symbol_name": symbol_name,
        "symbol_type": symbol.get("type", ""),
        "root_type": root_type,
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
