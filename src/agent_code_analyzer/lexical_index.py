from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from .lexical_repository import LexicalDocument, LexicalRepository
from .search_rank import query_terms, tokenize_text
from .search_scoring import DEFAULT_SEARCH_SCORER


logger = logging.getLogger(__name__)


def _normalize_query(query: str) -> tuple[list[str], str]:
    return query_terms(query)


def _score_document(document: dict[str, Any], query_terms_list: list[str], query_text: str) -> float:
    if "matched_term_count" in document:
        matched_term_count = int(document.get("matched_term_count") or 0)
        searchable = str(document.get("searchable_text", "")).lower()
        symbol = str(document.get("symbol_name", "")).lower()
        path = str(document.get("file_path", "")).lower()
        score = 0.0
        if query_terms_list:
            score += 0.9 * (matched_term_count / len(query_terms_list))
            if matched_term_count < len(query_terms_list):
                score += 0.2 * (matched_term_count / len(query_terms_list))
        if query_text and query_text in searchable:
            score += 0.8
        if query_text and query_text in symbol:
            score += 0.4
        if query_text and query_text in path:
            score += 0.35
        if query_terms_list and all(term in path for term in query_terms_list):
            score += 0.25
        if query_terms_list and all(term in symbol for term in query_terms_list):
            score += 0.25
        if str(document.get("unit_type", "")) == "file" and query_terms_list and any(term in path for term in query_terms_list):
            score += 0.1
        if "generated" in path or ".min." in path or ".generated." in path:
            score *= 0.75
        return score

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
    started_at = perf_counter()
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
    candidate_started_at = perf_counter()
    candidate_documents = LexicalRepository.fetch_candidate_documents(
        conn,
        query_terms=query_terms_list,
        project=project,
        scope_type=scope_type,
    )
    candidate_elapsed_ms = (perf_counter() - candidate_started_at) * 1000.0
    scoring_started_at = perf_counter()
    for document in candidate_documents:
        score = _score_document(document, query_terms_list, query_text)
        if score <= 0:
            continue
        document["score"] = score
        results.append(document)
    scoring_elapsed_ms = (perf_counter() - scoring_started_at) * 1000.0

    fallback_elapsed_ms = 0.0
    fallback_used = False
    if not results:
        fallback_used = True
        fallback_started_at = perf_counter()
        for document in LexicalRepository.fetch_documents(conn, project=project, scope_type=scope_type):
            score = _score_document(document, query_terms_list, query_text)
            if score <= 0:
                continue
            document["score"] = score
            results.append(document)
        fallback_elapsed_ms = (perf_counter() - fallback_started_at) * 1000.0

    sort_started_at = perf_counter()
    results.sort(
        key=lambda item: (
            -float(item["score"]),
            item.get("scope_type") != "symbol",
            item.get("symbol_name", ""),
            item.get("file_path", ""),
        )
    )
    sort_elapsed_ms = (perf_counter() - sort_started_at) * 1000.0
    total_elapsed_ms = (perf_counter() - started_at) * 1000.0

    logger.info(
        "lexical_search_timing query=%r project=%r scope_type=%r candidates=%d matched=%d fallback=%s candidate_ms=%.3f scoring_ms=%.3f fallback_ms=%.3f sort_ms=%.3f total_ms=%.3f",
        query,
        project,
        scope_type,
        len(candidate_documents),
        len(results),
        fallback_used,
        candidate_elapsed_ms,
        scoring_elapsed_ms,
        fallback_elapsed_ms,
        sort_elapsed_ms,
        total_elapsed_ms,
    )
    return {
        "query": query,
        "project": project,
        "scope_type": scope_type,
        "limit": limit,
        "results": results[:limit],
    }
