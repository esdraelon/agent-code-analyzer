from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProjectRowMapper:
    """Map sqlite rows and language metadata into plain project dictionaries."""

    @staticmethod
    def decode_languages(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, str):
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                return [value] if value else []
            if isinstance(raw, list):
                return [str(item) for item in raw if str(item)]
        return []

    @staticmethod
    def encode_languages(languages: list[str]) -> str:
        return json.dumps(ProjectRowMapper.merge_languages([str(language) for language in languages if str(language)]))

    @staticmethod
    def row_languages(row: sqlite3.Row) -> list[str]:
        return ProjectRowMapper.decode_languages(row["languages"])

    @staticmethod
    def merge_languages(*groups: list[str]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for language in group:
                if language and language not in merged:
                    merged.append(language)
        return merged

    @staticmethod
    def row_to_project_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "root_path": row["root_path"],
            "db_path": row["db_path"],
            "mode": row["mode"],
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "indexed_at": row["indexed_at"],
            "file_count": row["file_count"],
            "supported_file_count": row["supported_file_count"],
            "symbol_count": row["symbol_count"],
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
        }

    @staticmethod
    def row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "project": row["project_name"],
            "root_path": row["root_path"],
            "file_count": row["file_count"],
            "supported_file_count": row["supported_file_count"],
            "symbol_count": row["symbol_count"],
            "indexed_at": row["indexed_at"],
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
        }

    @staticmethod
    def project_languages_from_conn(conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute("SELECT languages FROM files ORDER BY id ASC").fetchall()
        return ProjectRowMapper.merge_languages(*[ProjectRowMapper.decode_languages(row["languages"]) for row in rows])

    @staticmethod
    def symbol_rows(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, symbol_order, type, name, depth, start_row, start_column, end_row, end_column, signature, languages
            FROM symbols
            WHERE file_id = ?
            ORDER BY symbol_order ASC, id ASC
            """,
            (file_id,),
        ).fetchall()
        return [
            {
                "sqlite_symbol_id": row["id"],
                "symbol_order": row["symbol_order"],
                "type": row["type"],
                "name": row["name"],
                "depth": row["depth"],
                "start_point": {"row": row["start_row"], "column": row["start_column"]},
                "end_point": {"row": row["end_row"], "column": row["end_column"]},
                "signature": row["signature"],
                "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
            }
            for row in rows
        ]

    @staticmethod
    def file_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "path": row["rel_path"],
            "abs_path": row["abs_path"],
            "language": row["language"],
            "languages": ProjectRowMapper.decode_languages(row["languages"] if "languages" in row.keys() else "[]"),
            "root_type": row["root_type"],
            "node_count": row["node_count"],
            "has_error": bool(row["has_error"]),
            "byte_length": row["byte_length"],
            "file_size": row["file_size"],
            "file_mtime_ns": row["file_mtime_ns"],
            "skeleton": row["skeleton"],
            "indexed_at": row["indexed_at"],
        }
