from __future__ import annotations

from pathlib import Path

from agent_code_analyzer import server


def test_server_instructions_promote_code_first_workflows() -> None:
    instructions = server.SERVER_INSTRUCTIONS
    assert "code-first analysis" in instructions
    assert "parse_source" in instructions
    assert "generate_ast_skeleton" in instructions
    assert "list_code_symbols" in instructions
    assert "read_file_excerpt" in instructions
    assert "semantic_rebuild" in instructions
    assert "semantic_refresh" in instructions
    assert "project-scoped" in instructions
    assert "onboarded to agent-code-analyzer" in instructions


def test_tool_response_factory_shapes_fallback_payloads() -> None:
    factory = server.ToolResponseFactory()

    payload = factory.parse_source_error("alpha", "src/one.py", ValueError("outside project root"))
    assert payload == {
        "project": "alpha",
        "file_path": "src/one.py",
        "supported": False,
        "language": "",
        "languages": [],
        "error": "outside project root",
    }
    assert factory.empty_symbol_list() == "[]"
    assert factory.empty_language() == ""


class FakeSemanticIndex:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, *, project=None, scope_type=None, limit: int = 10, exclude_files=None, exclude_symbols=None) -> dict[str, object]:
        self.calls.append(
            {
                "query": query,
                "project": project,
                "scope_type": scope_type,
                "limit": limit,
                "exclude_files": exclude_files,
                "exclude_symbols": exclude_symbols,
            }
        )
        return {
            "query": query,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "results": [{"sqlite_uri": "sqlite://projects/demo/files/1", "score": 0.9}],
        }


class FakeLexicalIndex:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, query: str, *, project=None, scope_type=None, limit: int = 10, exclude_files=None, exclude_symbols=None) -> dict[str, object]:
        self.calls.append(
            {
                "query": query,
                "project": project,
                "scope_type": scope_type,
                "limit": limit,
                "exclude_files": exclude_files,
                "exclude_symbols": exclude_symbols,
            }
        )
        return {
            "query": query,
            "project": project,
            "scope_type": scope_type,
            "limit": limit,
            "results": [{"sqlite_uri": "sqlite://projects/demo/files/2", "score": 0.95}],
        }


def test_semantic_search_tool_delegates_to_vector_index(monkeypatch) -> None:
    fake_index = FakeSemanticIndex()
    monkeypatch.setattr(server, "get_vector_index", lambda: fake_index)

    result = server.semantic_search("hello world", project="demo", scope_type="symbol", limit=4)

    assert fake_index.calls == [
        {"query": "hello world", "project": "demo", "scope_type": "symbol", "limit": 4, "exclude_files": None, "exclude_symbols": None}
    ]
    assert result["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/1"


def test_lexical_search_tool_delegates_to_project_search(monkeypatch) -> None:
    fake_lexical = FakeLexicalIndex()
    monkeypatch.setattr(server, "lexical_search_records", fake_lexical)

    result = server.lexical_search("hello world", project="demo", scope_type="symbol", limit=4)

    assert fake_lexical.calls == [
        {"query": "hello world", "project": "demo", "scope_type": "symbol", "limit": 4, "exclude_files": None, "exclude_symbols": None}
    ]
    assert result["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/2"


def test_search_code_tool_delegates_to_project_search(monkeypatch) -> None:
    fake_search = FakeLexicalIndex()
    monkeypatch.setattr(server, "search_code_records", fake_search)

    result = server.search_code("hello world", project="demo", scope_type="symbol", limit=4)

    assert fake_search.calls == [
        {"query": "hello world", "project": "demo", "scope_type": "symbol", "limit": 4, "exclude_files": None, "exclude_symbols": None}
    ]
    assert result["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/2"


class FakeProjectLookup:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, project: str) -> dict[str, object]:
        self.calls.append(project)
        return {"name": project}


class FakeSemanticRebuild:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, project: str, refresh: bool = False) -> dict[str, object]:
        self.calls.append({"project": project, "refresh": refresh})
        return {"project": project, "indexed_at": "2026-06-20T06:30:00"}


class FakeSemanticRefresh:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, project: str) -> dict[str, object]:
        self.calls.append(project)
        return {"project": project, "changed_file_count": 2, "deleted_file_count": 1}


def test_semantic_rebuild_tool_exposes_mass_ingestion_mode(monkeypatch) -> None:
    fake_get_project = FakeProjectLookup()
    fake_ingest = FakeSemanticRebuild()
    monkeypatch.setattr(server, "get_project", fake_get_project)
    monkeypatch.setattr(server, "ingest_project_index", fake_ingest)

    result = server.semantic_rebuild("demo")

    assert fake_get_project.calls == ["demo"]
    assert fake_ingest.calls == [{"project": "demo", "refresh": True}]
    assert result["operation"] == "semantic_rebuild"
    assert result["semantic_mode"] == "mass_ingestion"
    assert result["project"] == "demo"


def test_semantic_refresh_tool_exposes_fswatch_mode(monkeypatch) -> None:
    fake_get_project = FakeProjectLookup()
    fake_sync = FakeSemanticRefresh()
    monkeypatch.setattr(server, "get_project", fake_get_project)
    monkeypatch.setattr(server, "sync_project_index", fake_sync)

    result = server.semantic_refresh("demo")

    assert fake_get_project.calls == ["demo"]
    assert fake_sync.calls == ["demo"]
    assert result["operation"] == "semantic_refresh"
    assert result["semantic_mode"] == "fswatch_diff"
    assert result["changed_file_count"] == 2


def test_file_excerpt_renderer_clamps_and_handles_reversed_bounds(tmp_path: Path) -> None:
    renderer = server.FileExcerptRenderer()
    path = tmp_path / "sample.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    assert renderer.render(path, start_line=0, end_line=2) == "1: alpha\n2: beta"
    assert renderer.render(path, start_line=3, end_line=2) == ""
