from __future__ import annotations

import re
from typing import Iterable

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD_RE = re.compile(r"[^A-Za-z0-9]+")
_GENERATED_PATH_RE = re.compile(
    r"(?:^|[\\/])(?:generated|gen|dist|build|vendor)(?:[\\/]|$)|(?:\.min\.)|(?:\.generated\.)",
    re.IGNORECASE,
)


def normalize_identifier(identifier: str) -> list[str]:
    pieces: list[str] = []
    for chunk in _NON_WORD_RE.split(identifier):
        if not chunk:
            continue
        split_chunk = _CAMEL_BOUNDARY_RE.sub(" ", chunk)
        pieces.extend(part.lower() for part in split_chunk.split() if part)
    return pieces


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _NON_WORD_RE.split(text):
        if not raw:
            continue
        tokens.extend(normalize_identifier(raw))
    return tokens


def query_terms(query: str) -> tuple[list[str], str]:
    lowered = query.strip().lower()
    return sorted(set(tokenize_text(query))), lowered


def is_generated_or_minified(*values: str) -> bool:
    return any(_GENERATED_PATH_RE.search(value or "") for value in values)


def build_embedding_text(*, file_path: str, symbol_name: str = "", signature: str = "", skeleton: str = "", source_text: str = "") -> str:
    parts = [
        f"file path: {file_path}" if file_path else "",
        f"symbol: {symbol_name}" if symbol_name else "",
        f"signature: {signature}" if signature else "",
        f"skeleton: {skeleton}" if skeleton else "",
        source_text,
    ]
    return "\n".join(part for part in parts if part)


def score_search_candidate(
    query: str,
    *,
    base_score: float = 0.0,
    searchable_text: str,
    file_path: str = "",
    symbol_name: str = "",
    unit_type: str = "",
    content_text: str = "",
) -> float:
    query_terms_list, query_text = query_terms(query)
    if not query_terms_list and not query_text:
        return float(base_score)

    searchable = searchable_text.lower()
    symbol = symbol_name.lower()
    path = file_path.lower()
    content = content_text.lower()
    tokens = set(tokenize_text(searchable))

    exact_terms = [term for term in query_terms_list if term in tokens]
    loose_terms = [term for term in query_terms_list if term in searchable and term not in exact_terms]

    score = float(base_score)
    if query_terms_list:
        score += 0.9 * (len(exact_terms) / len(query_terms_list))
        score += 0.2 * (len(loose_terms) / len(query_terms_list))
    if query_text and query_text in searchable:
        score += 0.6
    if query_text and query_text in symbol:
        score += 0.4
    if query_text and query_text in path:
        score += 0.35
    if query_terms_list and all(term in path for term in query_terms_list):
        score += 0.25
    if query_terms_list and all(term in symbol for term in query_terms_list):
        score += 0.25
    if unit_type == "file" and query_terms_list and any(term in path for term in query_terms_list):
        score += 0.1
    if is_generated_or_minified(file_path, searchable_text, content_text):
        score *= 0.75
    return score
