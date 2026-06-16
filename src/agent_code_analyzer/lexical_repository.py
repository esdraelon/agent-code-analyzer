from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import project_storage as storage


def _slug_component(value: str) -> str:
    return quote(storage._normalize_project(value), safe="")


def sqlite_file_uri(project: str, file_id: int) -> str:
    return f"sqlite://projects/{_slug_component(project)}/files/{file_id}"


def sqlite_symbol_uri(project: str, file_id: int, symbol_order: int) -> str:
    return f"{sqlite_file_uri(project, file_id)}/symbols/{symbol_order}"


def _symbol_unit_type(symbol_type: str) -> str:
    normalized = str(symbol_type).strip().lower()
    if not normalized:
        return "method"
    if "class" in normalized or "enum" in normalized or "struct" in normalized or "interface" in normalized:
        return "class"
    if "module" in normalized or "package" in normalized:
        return "module"
    if "file" in normalized:
        return "file"
    if "function" in normalized or "method" in normalized:
        return "method"
    return normalized


@dataclass(frozen=True)
class LexicalDocument:
    project_name: str
    file_id: int
    sqlite_uri: str
    sqlite_file_uri: str
    scope_type: str
    unit_type: str
    file_path: str
    symbol_name: str
    symbol_type: str
    content_text: str
    searchable_text: str
    indexed_at: str
    symbol_order: int | None = None

    @property
    def tokens(self) -> list[str]:
        from .search_rank import tokenize_text

        return sorted(set(tokenize_text(self.searchable_text)))


class LexicalRepository:
    """Repository-style helpers for sqlite-backed lexical persistence."""

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lexical_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                file_id INTEGER NOT NULL,
                sqlite_uri TEXT NOT NULL,
                sqlite_file_uri TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                unit_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                symbol_name TEXT NOT NULL DEFAULT '',
                symbol_type TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                searchable_text TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                symbol_order INTEGER,
                UNIQUE(project_name, sqlite_uri)
            );

            CREATE TABLE IF NOT EXISTS lexical_terms (
                project_name TEXT NOT NULL,
                term TEXT NOT NULL,
                doc_id INTEGER NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES lexical_documents(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_lexical_documents_project_scope
                ON lexical_documents(project_name, scope_type);
            CREATE INDEX IF NOT EXISTS idx_lexical_documents_file
                ON lexical_documents(project_name, file_id);
            CREATE INDEX IF NOT EXISTS idx_lexical_terms_project_term
                ON lexical_terms(project_name, term, doc_id);
            """
        )

    @staticmethod
    def delete_project(conn: sqlite3.Connection, project: str) -> None:
        LexicalRepository.ensure_schema(conn)
        conn.execute("DELETE FROM lexical_terms WHERE project_name = ?", (project,))
        conn.execute("DELETE FROM lexical_documents WHERE project_name = ?", (project,))

    @staticmethod
    def delete_file(conn: sqlite3.Connection, project: str, file_id: int) -> None:
        LexicalRepository.ensure_schema(conn)
        conn.execute(
            "DELETE FROM lexical_terms WHERE project_name = ? AND doc_id IN (SELECT id FROM lexical_documents WHERE project_name = ? AND file_id = ?)",
            (project, project, file_id),
        )
        conn.execute("DELETE FROM lexical_documents WHERE project_name = ? AND file_id = ?", (project, file_id))

    @staticmethod
    def upsert_document(conn: sqlite3.Connection, document: LexicalDocument) -> None:
        LexicalRepository.ensure_schema(conn)
        tokens = document.tokens
        cursor = conn.execute(
            """
            INSERT INTO lexical_documents (
                project_name, file_id, sqlite_uri, sqlite_file_uri, scope_type, unit_type,
                file_path, symbol_name, symbol_type, content_text, searchable_text, indexed_at, symbol_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_name, sqlite_uri) DO UPDATE SET
                file_id = excluded.file_id,
                sqlite_file_uri = excluded.sqlite_file_uri,
                scope_type = excluded.scope_type,
                unit_type = excluded.unit_type,
                file_path = excluded.file_path,
                symbol_name = excluded.symbol_name,
                symbol_type = excluded.symbol_type,
                content_text = excluded.content_text,
                searchable_text = excluded.searchable_text,
                indexed_at = excluded.indexed_at,
                symbol_order = excluded.symbol_order
            RETURNING id
            """,
            (
                document.project_name,
                document.file_id,
                document.sqlite_uri,
                document.sqlite_file_uri,
                document.scope_type,
                document.unit_type,
                document.file_path,
                document.symbol_name,
                document.symbol_type,
                document.content_text,
                document.searchable_text,
                document.indexed_at,
                document.symbol_order,
            ),
        )
        doc_id = int(cursor.fetchone()[0])
        conn.execute("DELETE FROM lexical_terms WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            "INSERT INTO lexical_terms(project_name, term, doc_id) VALUES (?, ?, ?)",
            [(document.project_name, term, doc_id) for term in tokens],
        )

    @staticmethod
    def fetch_documents(
        conn: sqlite3.Connection,
        *,
        project: str | None = None,
        scope_type: str | None = None,
    ) -> list[dict[str, Any]]:
        LexicalRepository.ensure_schema(conn)
        conditions: list[str] = []
        params: list[Any] = []
        if project is not None:
            conditions.append("project_name = ?")
            params.append(project)
        if scope_type is not None:
            conditions.append("scope_type = ?")
            params.append(scope_type)
        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM lexical_documents {where_sql} ORDER BY project_name ASC, scope_type ASC, file_path ASC, sqlite_uri ASC",
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def sync_analysis(
        conn: sqlite3.Connection,
        *,
        project: str,
        root_path: Path,
        file_id: int,
        file_path: str,
        analysis: dict[str, Any],
        indexed_at: str,
        file_size: int,
        file_mtime_ns: int,
    ) -> dict[str, Any]:
        LexicalRepository.ensure_schema(conn)
        parsed = analysis["parsed"]
        file_uri = sqlite_file_uri(project, file_id)
        source_text = parsed.source_code
        file_rel_path = str(Path(file_path).resolve().relative_to(Path(root_path).resolve()))

        LexicalRepository.delete_file(conn, project, file_id)

        file_document = LexicalDocument(
            project_name=project,
            file_id=file_id,
            sqlite_uri=file_uri,
            sqlite_file_uri=file_uri,
            scope_type="file",
            unit_type="file",
            file_path=file_rel_path,
            symbol_name="",
            symbol_type="",
            content_text=source_text,
            searchable_text=" ".join(
                [
                    file_rel_path,
                    source_text,
                    analysis.get("skeleton", ""),
                    " ".join(symbol.get("name", "") for symbol in analysis.get("symbols", [])),
                    " ".join(symbol.get("signature", "") for symbol in analysis.get("symbols", [])),
                ]
            ),
            indexed_at=indexed_at,
        )
        LexicalRepository.upsert_document(conn, file_document)

        for order, symbol in enumerate(analysis.get("symbols", [])):
            sqlite_uri = sqlite_symbol_uri(project, file_id, order)
            symbol_name = str(symbol.get("name", ""))
            symbol_type = str(symbol.get("type", ""))
            signature = str(symbol.get("signature", ""))
            searchable_text = " ".join(
                [
                    file_rel_path,
                    symbol_name,
                    symbol_type,
                    signature,
                    signature,
                    source_text,
                ]
            )
            symbol_document = LexicalDocument(
                project_name=project,
                file_id=file_id,
                sqlite_uri=sqlite_uri,
                sqlite_file_uri=file_uri,
                scope_type="symbol",
                unit_type=_symbol_unit_type(symbol_type),
                file_path=file_rel_path,
                symbol_name=symbol_name,
                symbol_type=symbol_type,
                content_text=signature,
                searchable_text=searchable_text,
                indexed_at=indexed_at,
                symbol_order=order,
            )
            LexicalRepository.upsert_document(conn, symbol_document)

        return {
            "project": project,
            "file_id": file_id,
            "sqlite_uri": file_uri,
            "documents": 1 + len(analysis.get("symbols", [])),
            "file_size": file_size,
            "file_mtime_ns": file_mtime_ns,
        }
