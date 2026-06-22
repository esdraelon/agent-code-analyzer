from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agent_code_analyzer import control_api
from agent_code_analyzer import projects


class FakeVectorIndex:
    def __init__(self) -> None:
        self.sync_calls: list[dict[str, Any]] = []
        self.deleted_projects: list[str] = []
        self.deleted_files: list[str] = []
        self.collection_name = "fake"
        self.semantic_counts = {
            (): 10,
            (("source_kind", "file"),): 1,
            (("source_kind", "tree-sitter"),): 2,
            (("source_kind", "chunk"),): 3,
            (("source_kind", "symbol"),): 4,
            (("unit_type", "file"),): 1,
            (("unit_type", "class"),): 2,
            (("unit_type", "method"),): 3,
            (("unit_type", "module"),): 1,
            (("unit_type", "chunk"),): 3,
        }

    def sync_records(self, **kwargs) -> dict[str, Any]:
        self.sync_calls.append(kwargs)
        return {"points": len(kwargs.get("symbol_rows", [])) + 1}

    def delete_project(self, project: str) -> None:
        self.deleted_projects.append(project)

    def delete_file(self, sqlite_uri: str) -> None:
        self.deleted_files.append(sqlite_uri)

    def client(self):
        return self

    def collection_exists(self, collection_name: str) -> bool:
        return True

    def count(self, collection_name: str, count_filter=None, exact: bool = True):
        filters: list[tuple[str, Any]] = []
        for condition in getattr(count_filter, "must", []) or []:
            key = getattr(condition, "key", None)
            match = getattr(condition, "match", None)
            value = getattr(match, "value", None)
            if key is not None:
                filters.append((key, value))
        key = tuple(sorted((item for item in filters if item[0] != "project_name")))
        count = self.semantic_counts.get(key)
        if count is None:
            count = self.semantic_counts.get((), 0)
        return type("CountResult", (), {"count": count})()


@contextmanager
def run_server() -> Any:
    server = control_api.create_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        server_address = server.server_address
        host = server_address[0]
        port = server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def isolate_storage(tmp_path: Path, monkeypatch) -> Path:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return state_dir


def request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    url = f"{base_url}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body)


def test_control_api_project_lifecycle_status_and_source_drillthrough(tmp_path: Path, monkeypatch) -> None:
    isolate_storage(tmp_path, monkeypatch)
    fake_index = FakeVectorIndex()
    monkeypatch.setattr("agent_code_analyzer.vector_index.get_vector_index", lambda: fake_index)

    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("class Box:\n    def hello(self):\n        return 'ok'\n", encoding="utf-8")

    with run_server() as base_url:
        status, response = request_json(
            base_url,
            "POST",
            "/api/projects",
            {"name": "demo", "root_path": str(root), "mode": "directory", "description": "demo project"},
        )
        assert status == 201
        assert response["ok"] is True
        assert response["project"]["name"] == "demo"
        assert response["project"]["ingest"]["file_count"] == 1

        status, response = request_json(base_url, "GET", "/api/projects")
        assert status == 200
        assert response["ok"] is True
        assert response["projects"][0]["name"] == "demo"
        assert response["projects"][0]["status"] == "completed"

        status, response = request_json(base_url, "GET", "/api/projects/demo/status")
        assert status == 200
        assert response["ok"] is True
        assert response["project"]["name"] == "demo"
        assert response["project"]["ingestion_job"]["job_id"] == "demo"
        assert response["project"]["ingestion_job"]["status"] == "completed"
        summary = response["project"]["index_summary"]
        assert summary["files"] == 1
        assert summary["symbols"] >= 1
        assert summary["hard_total"] >= 1
        assert summary["soft_total"] == 10
        hard_symbol_counts = {item["key"]: item["count"] for item in summary["hard"]["symbol_type_counts"]}
        assert hard_symbol_counts["class"] >= 1
        assert hard_symbol_counts["method"] >= 1
        hard_lexical_counts = {item["key"]: item["count"] for item in summary["hard"]["lexical_scope_counts"]}
        assert hard_lexical_counts["file"] == 1
        assert hard_lexical_counts["symbol"] >= 1
        hard_lexical_unit_counts = {item["key"]: item["count"] for item in summary["hard"]["lexical_symbol_unit_counts"]}
        assert hard_lexical_unit_counts["class"] >= 1
        assert hard_lexical_unit_counts["method"] >= 1
        soft_source_counts = {item["key"]: item["count"] for item in summary["soft"]["source_kind_counts"]}
        assert soft_source_counts["file"] == 1
        assert soft_source_counts["tree-sitter"] == 2
        assert soft_source_counts["chunk"] == 3
        assert soft_source_counts["symbol"] == 4

        status, response = request_json(base_url, "GET", "/api/projects/demo/jobs")
        assert status == 200
        assert response["jobs"] and response["jobs"][0]["project"] == "demo"

        original_sync_project_tree = projects.sync_project_tree

        def slow_sync_project_tree(project: str) -> dict[str, Any]:
            time.sleep(0.5)
            return original_sync_project_tree(project)

        monkeypatch.setattr(projects, "sync_project_tree", slow_sync_project_tree)

        started = time.monotonic()
        status, response = request_json(base_url, "POST", "/api/projects/demo/reingest", {"mode": "sync"})
        elapsed = time.monotonic() - started
        assert status == 202
        assert elapsed < 0.75
        assert response["ok"] is True
        assert response["job"]["project"] == "demo"
        assert response["job"]["status"] in {"queued", "running"}
        assert response["result"] is None

        deadline = time.monotonic() + 15
        while True:
            status, response = request_json(base_url, "GET", "/api/projects/demo/jobs")
            assert status == 200
            job = response["jobs"][0]
            if job["status"] == "completed":
                break
            assert time.monotonic() < deadline
            time.sleep(0.1)

        status, response = request_json(base_url, "GET", "/api/projects/demo/files/app.py?start_line=1&end_line=2")
        assert status == 200
        assert response["ok"] is True
        assert response["summary"]["file_path"] == "app.py"
        assert "class Box" in response["excerpt"]["content"]
        assert response["summary"]["ast_svg"].startswith('<svg xmlns="http://www.w3.org/2000/svg"')

        fake_index.deleted_projects.clear()
        status, response = request_json(base_url, "DELETE", "/api/projects/demo")
        assert status == 200
        assert response["ok"] is True
        assert response["result"]["removed"] is True

        status, response = request_json(base_url, "GET", "/api/projects")
        assert status == 200
        assert response["projects"] == []

    assert fake_index.deleted_projects == ["demo"]


def test_control_api_search_endpoints_normalize_results(tmp_path: Path, monkeypatch) -> None:
    isolate_storage(tmp_path, monkeypatch)
    fake_index = FakeVectorIndex()
    monkeypatch.setattr("agent_code_analyzer.vector_index.get_vector_index", lambda: fake_index)

    root = tmp_path / "searchable"
    root.mkdir()
    (root / "lib.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "orkui/controller/controller.Search.php").parent.mkdir(parents=True, exist_ok=True)
    (root / "orkui/controller/controller.Search.php").write_text("<?php\nclass SearchController {\n    public function add() {\n        return true;\n    }\n}\n", encoding="utf-8")
    (root / "system/lib/ork3/class.SearchService.php").parent.mkdir(parents=True, exist_ok=True)
    (root / "system/lib/ork3/class.SearchService.php").write_text("<?php\nclass SearchService {\n    public function search() {\n        return true;\n    }\n}\n", encoding="utf-8")
    projects.add_project("searchable", str(root), mode="directory")

    def fake_lexical_search(query: str, **kwargs: Any) -> dict[str, Any]:
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 10)
        results = [
            {
                "project_name": "searchable",
                "file_path": "orkui/controller/controller.Search.php",
                "symbol_name": "add",
                "start_row": 0,
                "start_column": 0,
                "end_row": 1,
                "end_column": 0,
                "sqlite_uri": "sqlite://projects/searchable/files/1/symbols/0",
                "score": 0.91,
                "scope_type": "symbol",
                "source_kind": "symbol",
                "unit_type": "function",
            },
            {
                "project_name": "searchable",
                "file_path": "system/lib/ork3/class.SearchService.php",
                "symbol_name": "search",
                "start_row": 0,
                "start_column": 0,
                "end_row": 1,
                "end_column": 0,
                "sqlite_uri": "sqlite://projects/searchable/files/2/symbols/0",
                "score": 0.35,
                "scope_type": "symbol",
                "source_kind": "symbol",
                "unit_type": "function",
            },
        ]
        return {
            "query": query,
            "project": kwargs.get("project"),
            "scope_type": kwargs.get("scope_type"),
            "limit": limit,
            "offset": offset,
            "results": results[offset : offset + limit],
        }

    def fake_search_code(query: str, **kwargs: Any) -> dict[str, Any]:
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 10)
        fetch_limit = limit + offset
        lexical = fake_lexical_search(query, **{**kwargs, "limit": fetch_limit, "offset": 0})
        offset = kwargs.get("offset", 0)
        semantic_results = [
            {
                "project_name": "searchable",
                "file_path": "orkui/controller/controller.Search.php",
                "symbol_name": "add",
                "start_row": 0,
                "start_column": 0,
                "end_row": 1,
                "end_column": 0,
                "sqlite_uri": "sqlite://projects/searchable/files/1/symbols/0",
                "score": 0.87,
                "scope_type": "symbol",
                "source_kind": "symbol",
                "unit_type": "function",
            },
            {
                "project_name": "searchable",
                "file_path": "system/lib/ork3/class.SearchService.php",
                "symbol_name": "search",
                "start_row": 0,
                "start_column": 0,
                "end_row": 1,
                "end_column": 0,
                "sqlite_uri": "sqlite://projects/searchable/files/2/symbols/0",
                "score": 0.73,
                "scope_type": "symbol",
                "source_kind": "symbol",
                "unit_type": "function",
            },
        ]
        semantic = {
            "query": query,
            "project": kwargs.get("project"),
            "scope_type": kwargs.get("scope_type"),
            "limit": fetch_limit,
            "offset": 0,
            "results": semantic_results[:fetch_limit],
        }
        return {
            "query": query,
            "project": kwargs.get("project"),
            "scope_type": kwargs.get("scope_type"),
            "limit": limit,
            "offset": offset,
            "lexical": lexical,
            "semantic": semantic,
            "results": lexical["results"][offset : offset + limit],
        }

    monkeypatch.setattr(projects, "lexical_search", fake_lexical_search)
    monkeypatch.setattr(projects, "search_code", fake_search_code)

    with run_server() as base_url:
        status, response = request_json(base_url, "GET", "/api/search/lexical?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["ok"] is True
        assert response["results"][0]["index_type"] == "lexical"
        assert response["results"][0]["source_link"]["href"].startswith("/api/projects/searchable/files/orkui/controller/controller.Search.php")
        assert response["results"][0]["excerpt"]["content"].startswith("1: <?php")
        related_hrefs = {link["rel"]: link["href"] for link in response["results"][0]["related_index_links"]}
        assert related_hrefs["source"].startswith("/source?")
        assert related_hrefs["tree-sitter"].startswith("/search?mode=tree-sitter")
        assert related_hrefs["semantic"].startswith("/search?mode=semantic")
        assert related_hrefs["ast"].startswith("/search?mode=ast")

        status, response = request_json(base_url, "GET", "/api/search/semantic?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "semantic"
        assert response["results"][0]["excerpt"]["content"].startswith("1: <?php")

        status, response = request_json(base_url, "GET", "/api/search/unified?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "unified"
        assert set(response["results"][0]["backends"]) == {"lexical", "semantic"}

        status, response = request_json(base_url, "GET", "/api/search/semantic?" + urlencode({"query": "add", "project": "searchable", "directory": "orkui"}))
        assert status == 200
        assert response["results"]
        assert all(item["file_path"].startswith("orkui/") for item in response["results"])
        assert all(not item["file_path"].startswith("system/lib/ork3/") for item in response["results"])

        status, response = request_json(base_url, "GET", "/api/search/unified?" + urlencode({"query": "add", "project": "searchable", "directory": "orkui"}))
        assert status == 200
        assert response["results"]
        assert all(item["file_path"].startswith("orkui/") for item in response["results"])
        assert all(not item["file_path"].startswith("system/lib/ork3/") for item in response["results"])

        status, response = request_json(base_url, "GET", "/api/search/unified?" + urlencode({"query": "add", "project": "searchable", "limit": "1", "offset": "1"}))
        assert status == 200
        assert len(response["results"]) == 1
        assert response["results"][0]["file_path"] == "system/lib/ork3/class.SearchService.php"

        status, response = request_json(base_url, "GET", "/api/search/semantic?" + urlencode({"query": "add", "project": "searchable", "limit": "1", "offset": "1"}))
        assert status == 200
        assert len(response["results"]) == 1
        assert response["results"][0]["file_path"] == "system/lib/ork3/class.SearchService.php"

        status, response = request_json(base_url, "GET", "/api/search/tree-sitter?" + urlencode({"project": "searchable", "file_path": "lib.py"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "tree-sitter"
        assert response["results"][0]["supported"] is True

        status, response = request_json(base_url, "GET", "/api/search/ast?" + urlencode({"project": "searchable", "file_path": "lib.py"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "ast"
        assert "skeleton" in response["results"][0]
