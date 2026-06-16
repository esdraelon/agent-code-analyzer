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


class FakeEmbeddingProvider:
    vector_size = 3

    def embed_document(self, text: str) -> list[float]:
        base = float(len(text) % 7)
        return [base, base + 1.0, base + 2.0]

    def embed_query(self, text: str) -> list[float]:
        base = float(len(text) % 5)
        return [base + 3.0, base + 4.0, base + 5.0]


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
    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

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
    assert file_point.payload["unit_type"] == "file"
    assert file_point.payload["sqlite_uri"] == "sqlite://projects/demo/files/7"
    assert file_point.payload["sqlite_file_uri"] == "sqlite://projects/demo/files/7"
    assert file_point.payload["content_text"]

    symbol_point = points[1]
    assert symbol_point.payload["scope_type"] == "symbol"
    assert symbol_point.payload["unit_type"] == "method"
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
    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

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
    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

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


def test_sync_analysis_round_trips_symbol_unit_type_into_search_results(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "app.py"
    file_path.write_text("def hello(name):\n    return f'hi {name}'\n", encoding="utf-8")

    analysis = analyze_file(str(file_path))
    fake_client = FakeQdrantClient()
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
        filter_conditions = kwargs["query_filter"].must if kwargs.get("query_filter") else []
        points: list[FakePoint] = []
        for point in fake_client.upsert_calls[-1]["points"]:
            payload = dict(point.payload)
            if any(condition.key == "project_name" and condition.match.value != payload["project_name"] for condition in filter_conditions):
                continue
            if any(condition.key == "scope_type" and condition.match.value != payload["scope_type"] for condition in filter_conditions):
                continue
            points.append(FakePoint(0.99 if payload["scope_type"] == "symbol" else 0.5, payload))
        return FakeQueryResponse(points)

    monkeypatch.setattr(fake_client, "query_points", fake_query_points)

    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

    sync_result = index.sync_analysis(
        project="demo",
        project_root=root,
        file_id=7,
        file_path=str(file_path),
        analysis=analysis,
        indexed_at="2026-06-14T18:00:00",
        file_size=file_path.stat().st_size,
        file_mtime_ns=file_path.stat().st_mtime_ns,
    )
    assert sync_result["points"] >= 2

    search_result = index.search("hello", project="demo", scope_type="symbol", limit=5)

    assert captured["collection_name"] == index.collection_name
    assert search_result["query"] == "hello"
    assert search_result["results"][0]["scope_type"] == "symbol"
    assert search_result["results"][0]["unit_type"] == "method"
    assert search_result["results"][0]["sqlite_uri"] == "sqlite://projects/demo/files/7/symbols/0"
    assert search_result["results"][0]["sqlite_file_uri"] == "sqlite://projects/demo/files/7"
    assert search_result["results"][0]["symbol_name"] == "hello"


def test_qdrant_semantic_search_reranks_exact_identifier_hits_above_generated_noise(monkeypatch) -> None:
    class FakeEmbeddingProvider:
        vector_size = 3

        def embed_document(self, text: str) -> list[float]:
            return [1.0, 2.0, 3.0]

        def embed_query(self, text: str) -> list[float]:
            return [4.0, 5.0, 6.0]

    fake_client = FakeQdrantClient()

    class FakePoint:
        def __init__(self, score: float, payload: dict[str, Any]) -> None:
            self.score = score
            self.payload = payload

    class FakeQueryResponse:
        def __init__(self, points: list[FakePoint]) -> None:
            self.points = points

    def fake_query_points(**kwargs):
        return FakeQueryResponse(
            [
                FakePoint(
                    0.99,
                    {
                        "project_name": "demo",
                        "scope_type": "symbol",
                        "unit_type": "method",
                        "sqlite_uri": "sqlite://projects/demo/files/9/symbols/0",
                        "sqlite_file_uri": "sqlite://projects/demo/files/9",
                        "file_path": "vendor/hello.min.js",
                        "symbol_name": "helloWorld",
                        "content_text": "function helloWorld(){return 1}",
                        "chunk_text": "function helloWorld(){return 1}",
                        "signature": "function helloWorld(){return 1}",
                    },
                ),
                FakePoint(
                    0.80,
                    {
                        "project_name": "demo",
                        "scope_type": "symbol",
                        "unit_type": "method",
                        "sqlite_uri": "sqlite://projects/demo/files/10/symbols/0",
                        "sqlite_file_uri": "sqlite://projects/demo/files/10",
                        "file_path": "src/hello.py",
                        "symbol_name": "hello_world",
                        "content_text": "def hello_world(): pass",
                        "chunk_text": "def hello_world(): pass",
                        "signature": "def hello_world(): pass",
                    },
                ),
            ]
        )

    fake_client.collection_exists_value = True
    monkeypatch.setattr(fake_client, "query_points", fake_query_points)

    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

    result = index.search("hello world", project="demo", scope_type="symbol", limit=2)

    assert [item["sqlite_uri"] for item in result["results"]] == [
        "sqlite://projects/demo/files/10/symbols/0",
        "sqlite://projects/demo/files/9/symbols/0",
    ]


def test_qdrant_index_uses_injected_embedding_provider_for_vectors_and_dimension() -> None:
    class FakeEmbeddingProvider:
        vector_size = 3

        def embed_document(self, text: str) -> list[float]:
            return [1.0, 2.0, 3.0]

        def embed_query(self, text: str) -> list[float]:
            return [4.0, 5.0, 6.0]

    fake_client = FakeQdrantClient(collection_exists=False)
    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider())
    object.__setattr__(index, "_client", fake_client)

    index.ensure_collection()
    assert fake_client.created_collections[0]["vectors_config"].size == 3

    points = [
        index._make_point(
            project="demo",
            project_root="/tmp/demo",
            file_id=1,
            file_path="app.py",
            language="python",
            languages=["python"],
            indexed_at="2026-06-15T12:00:00",
            file_size=12,
            file_mtime_ns=34,
            chunk_text="def hello(): pass",
            source_kind="file",
        )
    ]
    assert points[0].vector == [1.0, 2.0, 3.0]
    assert points[0].payload["sqlite_uri"] == "sqlite://projects/demo/files/1"

