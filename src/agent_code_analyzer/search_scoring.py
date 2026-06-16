from __future__ import annotations

import re
from dataclasses import dataclass

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")
_NON_WORD_RE = re.compile(r"[^A-Za-z0-9]+")
_GENERATED_PATH_RE = re.compile(
    r"(?:^|[\\/])(?:generated|gen|dist|build|vendor)(?:[\\/]|$)|(?:\.min\.)|(?:\.generated\.)",
    re.IGNORECASE,
)


def _normalize_identifier(identifier: str) -> list[str]:
    pieces: list[str] = []
    for chunk in _NON_WORD_RE.split(identifier):
        if not chunk:
            continue
        split_chunk = _DIGIT_BOUNDARY_RE.sub(" ", chunk)
        split_chunk = _ACRONYM_BOUNDARY_RE.sub(" ", split_chunk)
        split_chunk = _CAMEL_BOUNDARY_RE.sub(" ", split_chunk)
        pieces.extend(part.lower() for part in split_chunk.split() if part)
    return pieces


def _tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _NON_WORD_RE.split(text):
        if not raw:
            continue
        tokens.extend(_normalize_identifier(raw))
    return tokens


def _query_terms(query: str) -> tuple[list[str], str]:
    lowered = query.strip().lower()
    return sorted(set(_tokenize_text(query))), lowered


def _is_generated_or_minified(*values: str) -> bool:
    return any(_GENERATED_PATH_RE.search(value or "") for value in values)


@dataclass(frozen=True)
class ScoreBreakdown:
    base_score: float
    exact_term_bonus: float
    loose_term_bonus: float
    searchable_text_bonus: float
    symbol_text_bonus: float
    path_text_bonus: float
    path_terms_bonus: float
    symbol_terms_bonus: float
    file_path_bonus: float
    generated_multiplier: float
    total: float


class SearchScoringStrategy:
    def breakdown(
        self,
        query: str,
        *,
        base_score: float = 0.0,
        searchable_text: str,
        file_path: str = "",
        symbol_name: str = "",
        unit_type: str = "",
        content_text: str = "",
    ) -> ScoreBreakdown:
        query_terms, query_text = _query_terms(query)
        if not query_terms and not query_text:
            return ScoreBreakdown(
                base_score=float(base_score),
                exact_term_bonus=0.0,
                loose_term_bonus=0.0,
                searchable_text_bonus=0.0,
                symbol_text_bonus=0.0,
                path_text_bonus=0.0,
                path_terms_bonus=0.0,
                symbol_terms_bonus=0.0,
                file_path_bonus=0.0,
                generated_multiplier=1.0,
                total=float(base_score),
            )

        searchable = searchable_text.lower()
        symbol = symbol_name.lower()
        path = file_path.lower()
        tokens = set(_tokenize_text(searchable))

        exact_terms = [term for term in query_terms if term in tokens]
        loose_terms = [term for term in query_terms if term in searchable and term not in exact_terms]

        score = float(base_score)
        exact_term_bonus = 0.0
        loose_term_bonus = 0.0
        if query_terms:
            exact_term_bonus = 0.9 * (len(exact_terms) / len(query_terms))
            loose_term_bonus = 0.2 * (len(loose_terms) / len(query_terms))
            score += exact_term_bonus + loose_term_bonus

        searchable_text_bonus = 0.0
        symbol_text_bonus = 0.0
        path_text_bonus = 0.0
        path_terms_bonus = 0.0
        symbol_terms_bonus = 0.0
        file_path_bonus = 0.0

        if query_text and query_text in searchable:
            searchable_text_bonus = 0.6
            score += searchable_text_bonus
        if query_text and query_text in symbol:
            symbol_text_bonus = 0.4
            score += symbol_text_bonus
        if query_text and query_text in path:
            path_text_bonus = 0.35
            score += path_text_bonus
        if query_terms and all(term in path for term in query_terms):
            path_terms_bonus = 0.25
            score += path_terms_bonus
        if query_terms and all(term in symbol for term in query_terms):
            symbol_terms_bonus = 0.25
            score += symbol_terms_bonus
        if unit_type == "file" and query_terms and any(term in path for term in query_terms):
            file_path_bonus = 0.1
            score += file_path_bonus

        generated_multiplier = 1.0
        if _is_generated_or_minified(file_path, searchable_text, content_text):
            generated_multiplier = 0.75
            score *= generated_multiplier

        return ScoreBreakdown(
            base_score=float(base_score),
            exact_term_bonus=exact_term_bonus,
            loose_term_bonus=loose_term_bonus,
            searchable_text_bonus=searchable_text_bonus,
            symbol_text_bonus=symbol_text_bonus,
            path_text_bonus=path_text_bonus,
            path_terms_bonus=path_terms_bonus,
            symbol_terms_bonus=symbol_terms_bonus,
            file_path_bonus=file_path_bonus,
            generated_multiplier=generated_multiplier,
            total=score,
        )

    def score(
        self,
        query: str,
        *,
        base_score: float = 0.0,
        searchable_text: str,
        file_path: str = "",
        symbol_name: str = "",
        unit_type: str = "",
        content_text: str = "",
    ) -> float:
        return self.breakdown(
            query,
            base_score=base_score,
            searchable_text=searchable_text,
            file_path=file_path,
            symbol_name=symbol_name,
            unit_type=unit_type,
            content_text=content_text,
        ).total


DEFAULT_SEARCH_SCORER = SearchScoringStrategy()
