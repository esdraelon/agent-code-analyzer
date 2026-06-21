from __future__ import annotations

import json
import threading
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

    def sync_records(self, **kwargs) -> dict[str, Any]:
        self.sync_calls.append(kwargs)
        return {"points": len(kwargs.get("symbol_rows", [])) + 1}

    def delete_project(self, project: str) -> None:
        self.deleted_projects.append(project)

    def delete_file(self, sqlite_uri: str) -> None:
        self.deleted_files.append(sqlite_uri)


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
    (root / "app.py").write_text("def hello():\n    return 'ok'\n", encoding="utf-8")

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

        status, response = request_json(base_url, "GET", "/api/projects/demo/jobs")
        assert status == 200
        assert response["jobs"] and response["jobs"][0]["project"] == "demo"

        status, response = request_json(base_url, "POST", "/api/projects/demo/reingest", {"mode": "sync"})
        assert status == 202
        assert response["ok"] is True
        assert response["job"]["project"] == "demo"

        status, response = request_json(base_url, "GET", "/api/projects/demo/files/app.py?start_line=1&end_line=2")
        assert status == 200
        assert response["ok"] is True
        assert response["summary"]["file_path"] == "app.py"
        assert "def hello()" in response["excerpt"]["content"]

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
    projects.add_project("searchable", str(root), mode="directory")

    def fake_lexical_search(query: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "query": query,
            "project": kwargs.get("project"),
            "scope_type": kwargs.get("scope_type"),
            "limit": kwargs.get("limit", 10),
            "results": [
                {
                    "project_name": "searchable",
                    "file_path": "lib.py",
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
                }
            ],
        }

    def fake_search_code(query: str, **kwargs: Any) -> dict[str, Any]:
        lexical = fake_lexical_search(query, **kwargs)
        semantic = {
            "query": query,
            "project": kwargs.get("project"),
            "scope_type": kwargs.get("scope_type"),
            "limit": kwargs.get("limit", 10),
            "results": [
                {
                    "project_name": "searchable",
                    "file_path": "lib.py",
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
                }
            ],
        }
        return {"query": query, "project": kwargs.get("project"), "scope_type": kwargs.get("scope_type"), "limit": kwargs.get("limit", 10), "lexical": lexical, "semantic": semantic, "results": lexical["results"]}

    monkeypatch.setattr(projects, "lexical_search", fake_lexical_search)
    monkeypatch.setattr(projects, "search_code", fake_search_code)

    with run_server() as base_url:
        status, response = request_json(base_url, "GET", "/api/search/lexical?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["ok"] is True
        assert response["results"][0]["index_type"] == "lexical"
        assert response["results"][0]["source_link"]["href"].startswith("/api/projects/searchable/files/lib.py")
        assert response["results"][0]["related_index_links"]

        status, response = request_json(base_url, "GET", "/api/search/semantic?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "semantic"

        status, response = request_json(base_url, "GET", "/api/search/unified?" + urlencode({"query": "add", "project": "searchable"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "unified"
        assert set(response["results"][0]["backends"]) == {"lexical", "semantic"}

        status, response = request_json(base_url, "GET", "/api/search/tree-sitter?" + urlencode({"project": "searchable", "file_path": "lib.py"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "tree-sitter"
        assert response["results"][0]["supported"] is True

        status, response = request_json(base_url, "GET", "/api/search/ast?" + urlencode({"project": "searchable", "file_path": "lib.py"}))
        assert status == 200
        assert response["results"][0]["index_type"] == "ast"
        assert "skeleton" in response["results"][0]
