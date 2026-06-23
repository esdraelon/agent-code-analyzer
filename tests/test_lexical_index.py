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
        assert helper_result["results"][0]["start_row"] == 0
        assert helper_result["results"][0]["end_row"] >= helper_result["results"][0]["start_row"]
        assert "camelCaseHelper" in helper_result["results"][0]["content_text"]
        assert broad_result["results"][0]["symbol_name"] in {"camelCaseHelper", "Worker"}
        assert any(item["symbol_name"] == "camelCaseHelper" for item in broad_result["results"])
        assert path_result["results"][0]["scope_type"] == "file"
        assert path_result["results"][0]["file_path"].endswith("src/app.py")
        assert path_result["results"][0]["root_type"]
        assert path_result["results"][0]["start_row"] == 0
        assert path_result["results"][0]["end_row"] >= path_result["results"][0]["start_row"]


def test_search_code_merges_lexical_and_semantic_results(monkeypatch) -> None:
    lexical_calls: list[dict[str, Any]] = []
    semantic_calls: list[dict[str, Any]] = []

    def fake_lexical_search(
        query: str,
        *,
        project=None,
        scope_type=None,
        directory=None,
        limit: int = 10,
        offset: int = 0,
        exclude_files=None,
        exclude_symbols=None,
    ) -> dict[str, object]:
        lexical_calls.append(
            {
                "query": query,
                "project": project,
                "scope_type": scope_type,
                "directory": directory,
                "limit": limit,
                "offset": offset,
                "exclude_files": exclude_files,
                "exclude_symbols": exclude_symbols,
            }
        )
        return {
            "query": query,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "total_count": 1,
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
        def search(
            self,
            query: str,
            *,
            project=None,
            scope_type=None,
            directory=None,
            limit: int = 10,
            offset: int = 0,
            exclude_files=None,
            exclude_symbols=None,
        ) -> dict[str, object]:
            semantic_calls.append(
                {
                    "query": query,
                    "project": project,
                    "scope_type": scope_type,
                    "directory": directory,
                    "limit": limit,
                    "offset": offset,
                    "exclude_files": exclude_files,
                    "exclude_symbols": exclude_symbols,
                }
            )
            return {
                "query": query,
                "project": project,
                "scope_type": scope_type,
                "limit": limit,
                "total_count": 1,
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

    result = projects.search_code(
        "hello world",
        project="demo",
        scope_type="symbol",
        limit=3,
        exclude_files=["src/old.py"],
        exclude_symbols=["world"],
    )

    assert lexical_calls == [{"query": "hello world", "project": "demo", "scope_type": "symbol", "directory": None, "limit": 3, "offset": 0, "exclude_files": ["src/old.py"], "exclude_symbols": ["world"]}]
    assert semantic_calls == [{"query": "hello world", "project": "demo", "scope_type": "symbol", "directory": None, "limit": 3, "offset": 0, "exclude_files": ["src/old.py"], "exclude_symbols": ["world"]}]
    assert result["lexical"]["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/1"
    assert result["semantic"]["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/2"
    assert result["total_count"] == 1
    assert [item["sqlite_uri"] for item in result["results"]] == ["sqlite://projects/demo/files/1"]


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
        assert result["results"][0]["start_row"] == 0
        assert result["results"][0]["end_row"] >= result["results"][0]["start_row"]


def test_lexical_search_respects_file_and_symbol_exclusions(tmp_path: Path, monkeypatch) -> None:
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

        file_result = search(conn, "camel helper", project="demo", scope_type="symbol", limit=5, exclude_files=["src/app.py"])
        symbol_result = search(conn, "camel helper", project="demo", scope_type="symbol", limit=5, exclude_symbols=["Worker", "camelCaseHelper"])

    assert file_result["results"] == []
    assert symbol_result["results"] == []


def test_lexical_search_filters_by_directory_prefix(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "demo"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    src_file = root / "src" / "worker.py"
    docs_file = root / "docs" / "worker_notes.py"
    src_file.write_text("class Worker:\n    pass\n", encoding="utf-8")
    docs_file.write_text("class WorkerNotes:\n    pass\n", encoding="utf-8")

    db_path = storage._project_db_path("demo")
    with storage._connect(db_path) as conn:
        storage._ensure_project_schema(conn)
        from agent_code_analyzer.lexical_index import sync_analysis, search

        for file_id, file_path in enumerate([src_file, docs_file], start=1):
            analysis = analyze_file(str(file_path))
            sync_analysis(
                conn,
                project="demo",
                root_path=root,
                file_id=file_id,
                file_path=str(file_path),
                analysis=analysis,
                indexed_at="2026-06-15T12:00:00Z",
                file_size=file_path.stat().st_size,
                file_mtime_ns=file_path.stat().st_mtime_ns,
            )

        result = search(conn, "worker", project="demo", directory="src", limit=10)

    assert result["directory"] == "src"
    assert result["results"]
    assert all(item["file_path"].startswith("src/") for item in result["results"])
    assert all(item["file_path"] != "docs/worker_notes.py" for item in result["results"])


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


def test_lexical_search_does_not_fall_back_to_full_scan(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    from agent_code_analyzer import lexical_repository
    from agent_code_analyzer.lexical_index import search

    def fail_fetch_documents(*args, **kwargs):
        raise AssertionError("full lexical scan fallback must not be used")

    monkeypatch.setattr(
        lexical_repository.LexicalRepository,
        "fetch_candidate_documents",
        staticmethod(lambda *args, **kwargs: []),
    )
    monkeypatch.setattr(
        lexical_repository.LexicalRepository,
        "fetch_documents",
        staticmethod(fail_fetch_documents),
    )

    db_path = storage._project_db_path("demo")
    with storage._connect(db_path) as conn:
        storage._ensure_project_schema(conn)
        result = search(conn, "noisy rare query", project="demo", scope_type="symbol", limit=5)

    assert result["results"] == []
