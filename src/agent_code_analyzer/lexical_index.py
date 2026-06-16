from __future__ import annotations

from typing import Any

from .lexical_repository import LexicalDocument, LexicalRepository
from .search_rank import query_terms, tokenize_text
from .search_scoring import DEFAULT_SEARCH_SCORER


def _normalize_query(query: str) -> tuple[list[str], str]:
    return query_terms(query)


def _score_document(document: dict[str, Any], query_terms_list: list[str], query_text: str) -> float:
    return DEFAULT_SEARCH_SCORER.score(
        query_text or " ".join(query_terms_list),
        searchable_text=str(document.get("searchable_text", "")),
        file_path=str(document.get("file_path", "")),
        symbol_name=str(document.get("symbol_name", "")),
        unit_type=str(document.get("unit_type", "")),
        content_text=str(document.get("content_text", "")),
    )


def ensure_schema(conn) -> None:
    LexicalRepository.ensure_schema(conn)


def delete_project(conn, project: str) -> None:
    LexicalRepository.delete_project(conn, project)


def delete_file(conn, project: str, file_id: int) -> None:
    LexicalRepository.delete_file(conn, project, file_id)


def sync_analysis(
    conn,
    *,
    project: str,
    root_path,
    file_id: int,
    file_path: str,
    analysis: dict[str, Any],
    indexed_at: str,
    file_size: int,
    file_mtime_ns: int,
) -> dict[str, Any]:
    return LexicalRepository.sync_analysis(
        conn,
        project=project,
        root_path=root_path,
        file_id=file_id,
        file_path=file_path,
        analysis=analysis,
        indexed_at=indexed_at,
        file_size=file_size,
        file_mtime_ns=file_mtime_ns,
    )


def search(
    conn,
    query: str,
    *,
    project: str | None = None,
    scope_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    LexicalRepository.ensure_schema(conn)
    query_terms_list, query_text = _normalize_query(query)
    if not query_terms_list and not query_text:
        return {
            "query": query,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for document in LexicalRepository.fetch_documents(conn, project=project, scope_type=scope_type):
        score = _score_document(document, query_terms_list, query_text)
        if score <= 0:
            continue
        document["score"] = score
        results.append(document)

    results.sort(
        key=lambda item: (
            -float(item["score"]),
            item.get("scope_type") != "symbol",
            item.get("symbol_name", ""),
            item.get("file_path", ""),
        )
    )
    return {
        "query": query,
        "project": project,
        "scope_type": scope_type,
        "limit": limit,
        "results": results[:limit],
    }
