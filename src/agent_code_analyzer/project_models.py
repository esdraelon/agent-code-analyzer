from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRecord:
    name: str
    root_path: str
    db_path: str
    mode: str
    description: str
    created_at: str
    updated_at: str
    indexed_at: str | None = None
    file_count: int = 0
    supported_file_count: int = 0
    symbol_count: int = 0
