from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_code_analyzer import project_storage as storage
from agent_code_analyzer import projects
from agent_code_analyzer.parsing import analyze_file


def _isolate_project_state(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    projects._sync_storage()


def test_lexical_search_finds_split_identifiers_and_file_paths(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "src" / "app.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "def camelCaseHelper(value):\n    return value\n\nclass Worker:\n    pass\n",
        encoding="utf-8",
    )

    db_path = storage._project_db_path("demo")
    with storage._connect(db_path) as conn:
        storage._ensure_project_schema(conn)
        analysis = analyze_file(str(file_path))

        from agent_code_analyzer.lexical_index import sync_analysis, search

        sync_analysis(
            conn,
            project="demo",
            root_path=root,
            file_id=7,
            file_path=str(file_path),
            analysis=analysis,
            indexed_at="2026-06-15T12:00:00Z",
            file_size=file_path.stat().st_size,
            file_mtime_ns=file_path.stat().st_mtime_ns,
        )

        helper_result = search(conn, "camel helper", project="demo", scope_type="symbol", limit=5)
        broad_result = search(conn, "camel helper worker", project="demo", scope_type="symbol", limit=5)
        path_result = search(conn, "src app py", project="demo", scope_type="file", limit=5)

        assert helper_result["results"][0]["symbol_name"] == "camelCaseHelper"
        assert helper_result["results"][0]["scope_type"] == "symbol"
        assert "camelCaseHelper" in helper_result["results"][0]["content_text"]
        assert broad_result["results"][0]["symbol_name"] in {"camelCaseHelper", "Worker"}
        assert any(item["symbol_name"] == "camelCaseHelper" for item in broad_result["results"])
        assert path_result["results"][0]["scope_type"] == "file"
        assert path_result["results"][0]["file_path"].endswith("src/app.py")


def test_search_code_merges_lexical_and_semantic_results(monkeypatch) -> None:
    lexical_calls: list[dict[str, Any]] = []
    semantic_calls: list[dict[str, Any]] = []

    def fake_lexical_search(query: str, *, project=None, scope_type=None, limit: int = 10) -> dict[str, object]:
        lexical_calls.append({"query": query, "project": project, "scope_type": scope_type, "limit": limit})
        return {
            "query": query,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "results": [
                {
                    "sqlite_uri": "sqlite://projects/demo/files/1",
                    "scope_type": "symbol",
                    "unit_type": "method",
                    "symbol_name": "hello",
                    "score": 0.95,
                }
            ],
        }

    class FakeSemanticIndex:
        def search(self, query: str, *, project=None, scope_type=None, limit: int = 10) -> dict[str, object]:
            semantic_calls.append({"query": query, "project": project, "scope_type": scope_type, "limit": limit})
            return {
                "query": query,
                "project": project,
                "scope_type": scope_type,
                "limit": limit,
                "results": [
                    {
                        "sqlite_uri": "sqlite://projects/demo/files/2",
                        "scope_type": "symbol",
                        "unit_type": "method",
                        "symbol_name": "world",
                        "score": 0.91,
                    }
                ],
            }

    monkeypatch.setattr(projects, "lexical_search", fake_lexical_search)
    monkeypatch.setattr(projects, "get_vector_index", lambda: FakeSemanticIndex())

    result = projects.search_code("hello world", project="demo", scope_type="symbol", limit=3)

    assert lexical_calls == [{"query": "hello world", "project": "demo", "scope_type": "symbol", "limit": 3}]
    assert semantic_calls == [{"query": "hello world", "project": "demo", "scope_type": "symbol", "limit": 3}]
    assert result["lexical"]["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/1"
    assert result["semantic"]["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/2"
    assert [item["sqlite_uri"] for item in result["results"]][:2] == [
        "sqlite://projects/demo/files/1",
        "sqlite://projects/demo/files/2",
    ]


def test_lexical_search_handles_acronym_identifiers(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "src" / "http_service.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "def XMLHttpRequest2(url):\n    return url\n",
        encoding="utf-8",
    )

    db_path = storage._project_db_path("demo")
    with storage._connect(db_path) as conn:
        storage._ensure_project_schema(conn)
        analysis = analyze_file(str(file_path))

        from agent_code_analyzer.lexical_index import sync_analysis, search

        sync_analysis(
            conn,
            project="demo",
            root_path=root,
            file_id=11,
            file_path=str(file_path),
            analysis=analysis,
            indexed_at="2026-06-15T12:00:00Z",
            file_size=file_path.stat().st_size,
            file_mtime_ns=file_path.stat().st_mtime_ns,
        )

        result = search(conn, "xml http request", project="demo", scope_type="symbol", limit=5)

        assert result["results"][0]["symbol_name"] == "XMLHttpRequest2"
        assert result["results"][0]["scope_type"] == "symbol"


def test_lexical_search_emits_timing_metrics(tmp_path: Path, monkeypatch, caplog) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "src" / "app.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "def camelCaseHelper(value):\n    return value\n\nclass Worker:\n    pass\n",
        encoding="utf-8",
    )

    db_path = storage._project_db_path("demo")
    with storage._connect(db_path) as conn:
        storage._ensure_project_schema(conn)
        analysis = analyze_file(str(file_path))

        from agent_code_analyzer.lexical_index import sync_analysis, search

        sync_analysis(
            conn,
            project="demo",
            root_path=root,
            file_id=7,
            file_path=str(file_path),
            analysis=analysis,
            indexed_at="2026-06-15T12:00:00Z",
            file_size=file_path.stat().st_size,
            file_mtime_ns=file_path.stat().st_mtime_ns,
        )

        caplog.set_level(logging.INFO)
        result = search(conn, "camel helper", project="demo", scope_type="symbol", limit=5)

        assert result["results"][0]["symbol_name"] == "camelCaseHelper"
        timing_messages = [record.message for record in caplog.records if "lexical_search_timing" in record.message]
        assert timing_messages
        assert "candidate_ms=" in timing_messages[0]
        assert "scoring_ms=" in timing_messages[0]
        assert "total_ms=" in timing_messages[0]
