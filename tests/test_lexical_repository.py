from __future__ import annotations

from pathlib import Path

from agent_code_analyzer import project_storage as storage
from agent_code_analyzer.lexical_repository import LexicalDocument, LexicalRepository


def test_lexical_repository_ensure_schema_migrates_legacy_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "lexical.sqlite3"

    with storage._connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE lexical_documents (
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
                UNIQUE(project_name, sqlite_uri)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE lexical_terms (
                project_name TEXT NOT NULL,
                term TEXT NOT NULL,
                doc_id INTEGER NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES lexical_documents(id) ON DELETE CASCADE
            )
            """
        )

        LexicalRepository.ensure_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(lexical_documents)").fetchall()}

    assert {"root_type", "start_row", "start_column", "end_row", "end_column", "content_text", "searchable_text", "indexed_at", "symbol_order"}.issubset(columns)


def test_lexical_repository_upsert_fetch_and_delete_file(tmp_path: Path) -> None:
    db_path = tmp_path / "lexical.sqlite3"

    with storage._connect(db_path) as conn:
        LexicalRepository.ensure_schema(conn)

        document = LexicalDocument(
            project_name="demo",
            file_id=7,
            sqlite_uri="sqlite://projects/demo/files/7/symbols/0",
            sqlite_file_uri="sqlite://projects/demo/files/7",
            scope_type="symbol",
            unit_type="method",
            file_path="src/app.py",
            symbol_name="hello",
            symbol_type="function_definition",
            root_type="function_definition",
            start_row=1,
            start_column=0,
            end_row=1,
            end_column=16,
            content_text="def hello(name):",
            searchable_text="src/app.py hello function_definition def hello(name):",
            indexed_at="2026-06-15T12:00:00Z",
            symbol_order=0,
        )

        LexicalRepository.upsert_document(conn, document)
        rows = LexicalRepository.fetch_documents(conn, project="demo", scope_type="symbol")

        assert len(rows) == 1
        assert rows[0]["sqlite_uri"] == "sqlite://projects/demo/files/7/symbols/0"
        assert rows[0]["sqlite_file_uri"] == "sqlite://projects/demo/files/7"
        assert rows[0]["symbol_name"] == "hello"
        assert rows[0]["unit_type"] == "method"
        assert rows[0]["root_type"] == "function_definition"
        assert rows[0]["start_row"] == 1
        assert rows[0]["searchable_text"]

        candidate_rows = LexicalRepository.fetch_candidate_documents(
            conn,
            query_terms=["hello"],
            project="demo",
            scope_type="symbol",
        )
        assert len(candidate_rows) == 1
        assert candidate_rows[0]["symbol_name"] == "hello"

        LexicalRepository.delete_file(conn, "demo", 7)
        assert LexicalRepository.fetch_documents(conn, project="demo") == []
