from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def _normalize_term(value: str) -> str:
    return str(value).strip().replace("\\", "/")


def _path_variants(value: str) -> set[str]:
    raw = _normalize_term(value)
    if not raw:
        return set()
    variants = {raw}
    stripped = raw.lstrip("./")
    if stripped:
        variants.add(stripped)
    stripped_slashes = raw.lstrip("/")
    if stripped_slashes:
        variants.add(stripped_slashes)
    basename = Path(raw).name
    if basename:
        variants.add(basename)
    return {variant for variant in variants if variant}


def normalize_exclusions(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()
    normalized: set[str] = set()
    for value in values:
        for variant in _path_variants(str(value)):
            normalized.add(variant)
        trimmed = str(value).strip()
        if trimmed:
            normalized.add(trimmed)
    return normalized


def _result_file_candidates(result: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key in ("file_path", "sqlite_file_uri", "sqlite_uri", "project_root"):
        value = result.get(key)
        if value:
            candidates.update(_path_variants(str(value)))
            candidates.add(str(value).strip())
    return {candidate for candidate in candidates if candidate}


def _result_symbol_candidates(result: dict[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key in ("symbol_name", "sqlite_uri", "sqlite_file_uri"):
        value = result.get(key)
        if value:
            candidates.update(_path_variants(str(value)))
            candidates.add(str(value).strip())
    return {candidate for candidate in candidates if candidate}


def should_exclude_result(
    result: dict[str, Any],
    *,
    exclude_files: set[str] | None = None,
    exclude_symbols: set[str] | None = None,
) -> bool:
    exclude_files = exclude_files or set()
    exclude_symbols = exclude_symbols or set()
    if not exclude_files and not exclude_symbols:
        return False

    file_candidates = _result_file_candidates(result)
    symbol_candidates = _result_symbol_candidates(result)

    for excluded in exclude_files:
        if excluded in file_candidates:
            return True
        for candidate in file_candidates:
            if candidate.endswith(f"/{excluded}") or candidate.endswith(excluded):
                return True

    for excluded in exclude_symbols:
        if excluded in symbol_candidates:
            return True
        for candidate in symbol_candidates:
            if candidate.endswith(f"/{excluded}") or candidate.endswith(excluded):
                return True

    return False
