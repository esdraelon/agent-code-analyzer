from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_code_analyzer.parsing import analyze_file
from agent_code_analyzer.projects import add_project
from agent_code_analyzer import projects as projects_module
from agent_code_analyzer.vector_index import QdrantVectorIndex


class FakeQdrantClient:
    def __init__(self, collection_exists: bool = True) -> None:
        self.collection_exists_value = collection_exists
        self.created_collections: list[dict[str, Any]] = []
        self.deleted_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_exists_value

    def create_collection(self, **kwargs) -> None:
        self.created_collections.append(kwargs)
        self.collection_exists_value = True

    def delete(self, **kwargs) -> None:
        self.deleted_calls.append(kwargs)

    def upsert(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)

    def query_points(self, **kwargs):
        raise AssertionError("query_points should be monkeypatched in semantic search tests")


class FakeBestEffortIndex:
    def __init__(self) -> None:
        self.deleted_projects: list[str] = []
        self.synced_files: list[dict[str, Any]] = []

    def delete_project(self, project: str) -> None:
        self.deleted_projects.append(project)

    def delete_file(self, sqlite_uri: str) -> None:
        self.deleted_projects.append(sqlite_uri)

    def sync_records(self, **kwargs) -> None:
        self.synced_files.append(kwargs)


def _isolate_project_state(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects_module, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects_module, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", state_dir / "projects")
    projects_module._sync_storage()


def test_sync_analysis_payloads_include_project_and_sqlite_links(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "app.py"
    file_path.write_text("def hello(name):\n    return f'hi {name}'\n", encoding="utf-8")

    analysis = analyze_file(str(file_path))
    fake_client = FakeQdrantClient()
    index = QdrantVectorIndex(url="http://example.test")
    index._client = fake_client

    result = index.sync_analysis(
        project="demo",
        project_root=root,
        file_id=7,
        file_path=str(file_path),
        analysis=analysis,
        indexed_at="2026-06-14T18:00:00",
        file_size=file_path.stat().st_size,
        file_mtime_ns=file_path.stat().st_mtime_ns,
    )

    assert result["synced"] is True
    assert result["sqlite_uri"] == "sqlite://projects/demo/files/7"
    assert fake_client.deleted_calls
    assert fake_client.upsert_calls

    points = fake_client.upsert_calls[0]["points"]
    file_point = points[0]
    assert file_point.payload["project_name"] == "demo"
    assert file_point.payload["scope_type"] == "file"
    assert file_point.payload["sqlite_uri"] == "sqlite://projects/demo/files/7"
    assert file_point.payload["sqlite_file_uri"] == "sqlite://projects/demo/files/7"
    assert file_point.payload["content_text"]

    symbol_point = points[1]
    assert symbol_point.payload["scope_type"] == "symbol"
    assert symbol_point.payload["sqlite_file_uri"] == "sqlite://projects/demo/files/7"
    assert symbol_point.payload["sqlite_uri"].startswith("sqlite://projects/demo/files/7/symbols/")
    assert symbol_point.payload["symbol_name"] == "hello"


def test_bootstrap_existing_project_reads_sqlite_and_preserves_symbol_row_links(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)
    fake_index = FakeBestEffortIndex()
    monkeypatch.setattr("agent_code_analyzer.vector_index.get_vector_index", lambda: fake_index)

    root = tmp_path / "existing"
    root.mkdir()
    (root / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    add_project("existing", str(root), mode="directory")

    fake_client = FakeQdrantClient()
    index = QdrantVectorIndex(url="http://example.test")
    index._client = fake_client

    summary = index.bootstrap_project("existing")
    assert summary["project"] == "existing"
    assert summary["files"] == 1
    assert summary["points"] >= 1
    assert fake_client.upsert_calls

    points = fake_client.upsert_calls[0]["points"]
    assert points[0].payload["sqlite_file_uri"] == "sqlite://projects/existing/files/1"
    if len(points) > 1:
        assert points[1].payload["sqlite_symbol_id"] == 1
        assert points[1].payload["sqlite_file_uri"] == "sqlite://projects/existing/files/1"


def test_semantic_search_filters_and_returns_payloads(monkeypatch) -> None:
    fake_client = FakeQdrantClient()
    index = QdrantVectorIndex(url="http://example.test")
    index._client = fake_client

    captured: dict[str, Any] = {}

    class FakePoint:
        def __init__(self, score: float, payload: dict[str, Any]) -> None:
            self.score = score
            self.payload = payload

    class FakeQueryResponse:
        def __init__(self, points: list[FakePoint]) -> None:
            self.points = points

    def fake_query_points(**kwargs):
        captured.update(kwargs)
        return FakeQueryResponse(
            [
                FakePoint(
                    0.88,
                    {
                        "project_name": "demo",
                        "scope_type": "symbol",
                        "sqlite_uri": "sqlite://projects/demo/files/7/symbols/0",
                        "sqlite_file_uri": "sqlite://projects/demo/files/7",
                        "file_path": "src/app.py",
                        "symbol_name": "hello",
                        "content_text": "def hello(name):",
                    },
                )
            ]
        )

    monkeypatch.setattr(fake_client, "query_points", fake_query_points)

    result = index.search("hello world", project="demo", scope_type="symbol", limit=3)

    assert captured["collection_name"] == index.collection_name
    assert captured["limit"] == 3
    assert captured["query_filter"].must[0].key == "project_name"
    assert captured["query_filter"].must[1].key == "scope_type"
    assert result["query"] == "hello world"
    assert result["project"] == "demo"
    assert result["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/7/symbols/0"
    assert result["results"][0]["symbol_name"] == "hello"
