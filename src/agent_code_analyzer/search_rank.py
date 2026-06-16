from __future__ import annotations

import re

from .search_scoring import DEFAULT_SEARCH_SCORER

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")
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
        split_chunk = _DIGIT_BOUNDARY_RE.sub(" ", chunk)
        split_chunk = _ACRONYM_BOUNDARY_RE.sub(" ", split_chunk)
        split_chunk = _CAMEL_BOUNDARY_RE.sub(" ", split_chunk)
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
    return DEFAULT_SEARCH_SCORER.score(
        query,
        base_score=base_score,
        searchable_text=searchable_text,
        file_path=file_path,
        symbol_name=symbol_name,
        unit_type=unit_type,
        content_text=content_text,
    )
