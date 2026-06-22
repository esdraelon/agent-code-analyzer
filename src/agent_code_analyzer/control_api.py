from __future__ import annotations

import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse, unquote

from . import projects
from .control_models import IngestionJob, ProjectListItem, SearchResultEnvelope, SourceLink
from .ingestion_state import begin_ingestion_checkpoint


DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8010
_ACTIVE_INGESTION_THREADS: dict[str, threading.Thread] = {}
_ACTIVE_INGESTION_THREADS_LOCK = threading.Lock()
_ACTIVE_JOB_STATUSES = {"queued", "running", "recovering"}


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or 0)
    if content_length <= 0:
        return {}
    raw = handler.rfile.read(content_length)
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def _send_json(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    body = _json_dumps(payload)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, status: HTTPStatus, message: str) -> None:
    _send_json(handler, status, {"ok": False, "error": message})


def _split_path(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment]


def _coerce_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _query_value(params: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = params.get(name)
    if not values:
        return default
    value = values[0].strip()
    return value if value else default


def _query_list(params: dict[str, list[str]], name: str) -> list[str] | None:
    value = _query_value(params, name)
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _project_status(project_name: str) -> dict[str, Any]:
    project = projects.get_project(project_name)
    job = projects.project_ingestion_job(project_name)
    job_status = job["status"] if job is not None else "idle"
    return {
        **project,
        "index_summary": projects.project_index_summary(project_name),
        "status": job_status,
        "ingestion_job": job,
    }


def _project_list_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in projects.list_projects():
        job = projects.project_ingestion_job(record["name"])
        status = job["status"] if job is not None else "idle"
        item = ProjectListItem(
            name=record["name"],
            root_path=record["root_path"],
            mode=record["mode"],
            description=record.get("description", ""),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            indexed_at=record.get("indexed_at"),
            file_count=int(record.get("file_count", 0)),
            supported_file_count=int(record.get("supported_file_count", 0)),
            symbol_count=int(record.get("symbol_count", 0)),
            languages=list(record.get("languages", [])),
            status=status,
        )
        items.append(item.to_dict())
    return items


def _job_from_project(project_name: str) -> dict[str, Any] | None:
    job = projects.project_ingestion_job(project_name)
    if job is None:
        return None
    normalized = IngestionJob(
        project=job["project"],
        job_id=job["job_id"],
        action=job["action"],
        phase=job["phase"],
        status=job["status"],
        queued_at=job["queued_at"],
        started_at=job["started_at"],
        updated_at=job["updated_at"],
        completed_at=job["completed_at"],
        total_count=int(job["total_count"]),
        processed_count=int(job["processed_count"]),
        last_file_path=job["last_file_path"],
        last_file_mtime_ns=job["last_file_mtime_ns"],
        last_file_content_hash=job["last_file_content_hash"],
        last_error=job["last_error"],
    )
    return normalized.to_dict()


def _active_ingestion_thread(project_name: str) -> threading.Thread | None:
    with _ACTIVE_INGESTION_THREADS_LOCK:
        thread = _ACTIVE_INGESTION_THREADS.get(project_name)
        if thread is not None and not thread.is_alive():
            _ACTIVE_INGESTION_THREADS.pop(project_name, None)
            return None
        return thread


def _register_ingestion_thread(project_name: str, thread: threading.Thread) -> None:
    with _ACTIVE_INGESTION_THREADS_LOCK:
        _ACTIVE_INGESTION_THREADS[project_name] = thread


def _clear_ingestion_thread(project_name: str) -> None:
    with _ACTIVE_INGESTION_THREADS_LOCK:
        _ACTIVE_INGESTION_THREADS.pop(project_name, None)


def _start_ingestion_thread(project_name: str, mode: str, refresh: bool) -> None:
    def _worker() -> None:
        try:
            if mode in {"sync", "gap", "reconcile"}:
                projects.sync_project_tree(project_name)
            else:
                projects.ingest_project_tree(project_name, refresh=refresh)
        except Exception as exc:  # pragma: no cover - background safety net
            try:
                print(f"ingestion worker failed for {project_name}: {exc}", flush=True)
            except Exception:
                pass
        finally:
            _clear_ingestion_thread(project_name)

    thread = threading.Thread(target=_worker, name=f"agent-code-analyzer-ingest-{project_name}", daemon=True)
    _register_ingestion_thread(project_name, thread)
    thread.start()


def _source_link_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    project = result.get("project_name") or result.get("project")
    file_path = result.get("file_path")
    if not project or not file_path:
        return None
    start_row = result.get("start_row")
    end_row = result.get("end_row")
    symbol_name = result.get("symbol_name")
    return SourceLink(
        project=str(project),
        file_path=str(file_path),
        start_line=int(start_row) + 1 if isinstance(start_row, int) else None,
        end_line=int(end_row) + 1 if isinstance(end_row, int) else None,
        symbol_name=str(symbol_name) if symbol_name else None,
    ).to_dict()


def _frontend_source_href(result: dict[str, Any]) -> str | None:
    project = result.get("project_name") or result.get("project")
    file_path = result.get("file_path")
    if not project or not file_path:
        return None

    query: dict[str, Any] = {
        "project": str(project),
        "file_path": str(file_path),
    }
    start_row = result.get("start_row")
    end_row = result.get("end_row")
    symbol_name = result.get("symbol_name")
    if isinstance(start_row, int):
        query["start_line"] = start_row + 1
    if isinstance(end_row, int):
        query["end_line"] = end_row + 1
    if symbol_name:
        query["symbol_name"] = str(symbol_name)
    return "/source?" + urlencode(query)


def _frontend_search_href(mode: str, result: dict[str, Any]) -> str | None:
    project = result.get("project_name") or result.get("project")
    file_path = result.get("file_path")
    if not project or not file_path:
        return None

    query: dict[str, Any] = {
        "mode": mode,
        "project": str(project),
    }
    if mode in {"tree-sitter", "ast"}:
        query["file_path"] = str(file_path)
    else:
        symbol_name = result.get("symbol_name")
        query["query"] = str(symbol_name) if symbol_name else str(file_path)
    return "/search?" + urlencode(query)


def _search_result_excerpt(result: dict[str, Any], line_count: int = 3) -> dict[str, Any] | None:
    project = result.get("project_name") or result.get("project")
    file_path = result.get("file_path")
    if not project or not file_path:
        return None

    start_row = result.get("start_row")
    start_line = (int(start_row) + 1) if isinstance(start_row, int) and start_row >= 0 else 1
    try:
        resolved = projects.resolve_project_path(str(project), str(file_path))
    except Exception:
        return None

    excerpt = _file_excerpt(resolved, start_line, start_line + max(1, line_count) - 1)
    if excerpt.strip() == "":
        return None

    excerpt_lines = excerpt.splitlines()
    end_line = start_line + max(len(excerpt_lines), 1) - 1
    return {
        "start_line": start_line,
        "end_line": end_line,
        "content": excerpt,
    }


def _related_index_links(result: dict[str, Any], index_type: str) -> list[dict[str, Any]]:
    project = result.get("project_name") or result.get("project")
    file_path = result.get("file_path")
    links: list[dict[str, Any]] = []
    if not project or not file_path:
        return links

    source_href = _frontend_source_href(result)
    if source_href:
        links.append({"rel": "source", "index_type": index_type, "href": source_href})

    for alternate in ("tree-sitter", "lexical", "semantic", "ast"):
        if alternate == index_type:
            continue
        href = _frontend_search_href(alternate, result)
        if href:
            links.append({"rel": alternate, "href": href, "index_type": alternate})
    return links


def _normalize_search_result(result: dict[str, Any], index_type: str) -> dict[str, Any]:
    envelope = SearchResultEnvelope(
        index_type=index_type,
        scope_type=result.get("scope_type"),
        project=result.get("project_name") or result.get("project"),
        file_path=result.get("file_path"),
        symbol_name=result.get("symbol_name"),
        start_row=result.get("start_row"),
        start_column=result.get("start_column"),
        end_row=result.get("end_row"),
        end_column=result.get("end_column"),
        sqlite_uri=result.get("sqlite_uri"),
        score=float(result["score"]) if result.get("score") is not None else None,
        source_link=SourceLink(
            project=str(result.get("project_name") or result.get("project") or ""),
            file_path=str(result.get("file_path") or ""),
            start_line=(int(result["start_row"]) + 1) if isinstance(result.get("start_row"), int) else None,
            end_line=(int(result["end_row"]) + 1) if isinstance(result.get("end_row"), int) else None,
            symbol_name=str(result.get("symbol_name")) if result.get("symbol_name") else None,
        )
        if result.get("project_name") or result.get("project")
        else None,
        related_index_links=_related_index_links(result, index_type),
        excerpt=_search_result_excerpt(result),
        extra={
            "unit_type": result.get("unit_type"),
            "source_kind": result.get("source_kind"),
            "root_type": result.get("root_type"),
            "languages": result.get("languages", []),
        },
    )
    return envelope.to_dict()


def _result_within_directory(result: dict[str, Any], directory: str | None) -> bool:
    if directory is None:
        return True
    normalized_directory = directory.strip().replace("\\", "/").rstrip("/")
    if normalized_directory == "":
        return True
    file_path = str(result.get("file_path", "")).strip().replace("\\", "/").rstrip("/")
    return file_path == normalized_directory or file_path.startswith(f"{normalized_directory}/")


def _normalize_unified_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    lexical = result.get("lexical", {}).get("results", [])
    semantic = result.get("semantic", {}).get("results", [])
    lexical_uris = {str(item.get("sqlite_uri", "")) for item in lexical}
    semantic_uris = {str(item.get("sqlite_uri", "")) for item in semantic}
    normalized: list[dict[str, Any]] = []
    for item in result.get("results", []):
        uri = str(item.get("sqlite_uri", ""))
        backends = [name for name, seen in (("lexical", uri in lexical_uris), ("semantic", uri in semantic_uris)) if seen]
        payload = _normalize_search_result(item, "unified")
        payload["backends"] = backends
        normalized.append(payload)
    return normalized


def _file_excerpt(path: Path, start_line: int, end_line: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if end_line < start_line:
        return ""
    start = max(start_line, 1) - 1
    end = min(end_line, len(lines))
    return "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(lines[start:end], start=start + 1))


def _handle_projects(handler: BaseHTTPRequestHandler, segments: list[str], query: dict[str, list[str]]) -> None:
    if len(segments) == 2 and handler.command == "GET":
        _send_json(handler, HTTPStatus.OK, {"ok": True, "projects": _project_list_items()})
        return

    if len(segments) == 2 and handler.command == "POST":
        payload = _read_json_body(handler)
        project = str(payload.get("name", "")).strip()
        root_path = str(payload.get("root_path", "")).strip()
        mode = str(payload.get("mode", "file")).strip()
        description = str(payload.get("description", "")).strip()
        if not project or not root_path:
            _send_error(handler, HTTPStatus.BAD_REQUEST, "name and root_path are required")
            return
        try:
            result = projects.add_project(project, root_path, mode=mode, description=description)
        except Exception as exc:
            _send_error(handler, HTTPStatus.BAD_REQUEST, str(exc))
            return
        _send_json(handler, HTTPStatus.CREATED, {"ok": True, "project": result})
        return

    if len(segments) >= 3:
        project_name = unquote(segments[2])
        if len(segments) == 3 and handler.command == "DELETE":
            result = projects.remove_project(project_name)
            status = HTTPStatus.OK if result.get("removed") else HTTPStatus.NOT_FOUND
            _send_json(handler, status, {"ok": result.get("removed", False), "result": result})
            return

        if len(segments) == 4 and segments[3] == "reingest" and handler.command == "POST":
            payload = _read_json_body(handler) if int(handler.headers.get("Content-Length", "0") or 0) else {}
            refresh = _coerce_bool(_query_value(query, "refresh"), _coerce_bool(str(payload.get("refresh", "true"))))
            mode = str(payload.get("mode", _query_value(query, "mode", "refresh")) or "refresh").strip().lower()
            try:
                current_job = _job_from_project(project_name)
            except Exception as exc:
                _send_error(handler, HTTPStatus.NOT_FOUND, str(exc))
                return
            if current_job is not None and current_job.get("status") in _ACTIVE_JOB_STATUSES:
                _send_json(handler, HTTPStatus.ACCEPTED, {"ok": True, "job": current_job, "result": None})
                return
            try:
                project = projects.get_project(project_name)
                phase = "gap_sweep" if mode in {"sync", "gap", "reconcile"} else "full_rebuild"
                checkpoint = begin_ingestion_checkpoint(
                    Path(project["db_path"]),
                    project=project_name,
                    root_path=Path(project["root_path"]),
                    mode="semantic_refresh" if mode in {"sync", "gap", "reconcile"} else "semantic_rebuild",
                    phase=phase,
                    total_file_count=0,
                )
                _start_ingestion_thread(project_name, mode, refresh)
                result = {
                    "project": checkpoint.project_name,
                    "job_id": checkpoint.project_name,
                    "action": checkpoint.mode,
                    "phase": checkpoint.phase,
                    "status": checkpoint.status,
                    "queued_at": checkpoint.queued_at,
                    "started_at": checkpoint.started_at,
                    "updated_at": checkpoint.updated_at,
                    "completed_at": checkpoint.completed_at,
                    "total_count": checkpoint.total_file_count,
                    "processed_count": checkpoint.processed_file_count,
                    "percent_complete": 0.0,
                    "last_file_path": checkpoint.last_file_path,
                    "last_file_mtime_ns": checkpoint.last_file_mtime_ns,
                    "last_file_content_hash": checkpoint.last_file_content_hash,
                    "last_error": checkpoint.error_state,
                }
            except Exception as exc:
                _send_error(handler, HTTPStatus.BAD_REQUEST, str(exc))
                return
            _send_json(handler, HTTPStatus.ACCEPTED, {"ok": True, "job": result, "result": None})
            return

        if len(segments) == 4 and segments[3] == "status" and handler.command == "GET":
            try:
                _send_json(handler, HTTPStatus.OK, {"ok": True, "project": _project_status(project_name)})
            except Exception as exc:
                _send_error(handler, HTTPStatus.NOT_FOUND, str(exc))
            return

        if len(segments) == 4 and segments[3] == "jobs" and handler.command == "GET":
            try:
                job = _job_from_project(project_name)
            except Exception as exc:
                _send_error(handler, HTTPStatus.NOT_FOUND, str(exc))
                return
            _send_json(handler, HTTPStatus.OK, {"ok": True, "jobs": [job] if job is not None else []})
            return

        if len(segments) == 4 and segments[3] == "paths" and handler.command == "GET":
            kind = _query_value(query, "kind") or "all"
            prefix = _query_value(query, "prefix") or ""
            limit = _coerce_int(_query_value(query, "limit"), 50)
            try:
                payload = projects.project_paths(project_name, kind=kind, prefix=prefix, limit=limit)
            except Exception as exc:
                _send_error(handler, HTTPStatus.BAD_REQUEST, str(exc))
                return
            _send_json(handler, HTTPStatus.OK, {"ok": True, **payload})
            return

        if len(segments) >= 4 and segments[3] == "files" and handler.command == "GET":
            file_path = "/".join(unquote(segment) for segment in segments[4:])
            start_line = _coerce_int(_query_value(query, "start_line"), 1)
            end_line = _coerce_int(_query_value(query, "end_line"), 200)
            try:
                file_summary = projects.project_file_summary(project_name, file_path)
                resolved = projects.resolve_project_path(project_name, file_path)
                excerpt = _file_excerpt(resolved, start_line, end_line)
            except Exception as exc:
                _send_error(handler, HTTPStatus.BAD_REQUEST, str(exc))
                return
            payload = {
                "ok": True,
                "project": project_name,
                "file_path": file_summary["file_path"],
                "summary": file_summary,
                "excerpt": {
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": excerpt,
                },
            }
            _send_json(handler, HTTPStatus.OK, payload)
            return

    _send_error(handler, HTTPStatus.NOT_FOUND, "Unknown projects route")


def _handle_search(handler: BaseHTTPRequestHandler, segments: list[str], query: dict[str, list[str]]) -> None:
    if handler.command != "GET":
        _send_error(handler, HTTPStatus.METHOD_NOT_ALLOWED, "Search endpoints are GET only")
        return

    search_type = segments[2] if len(segments) > 2 else ""
    if search_type in {"tree-sitter", "ast"}:
        project = _query_value(query, "project")
        file_path = _query_value(query, "file_path")
        if not project or not file_path:
            _send_error(handler, HTTPStatus.BAD_REQUEST, "project and file_path are required")
            return
        try:
            summary = projects.project_file_summary(project, file_path)
        except Exception as exc:
            _send_error(handler, HTTPStatus.BAD_REQUEST, str(exc))
            return
        result = {
            "index_type": search_type,
            "scope_type": "file",
            "project": project,
            "file_path": summary["file_path"],
            "symbol_name": None,
            "start_row": 0,
            "start_column": 0,
            "end_row": None,
            "end_column": None,
            "sqlite_uri": None,
            "score": None,
            "source_link": SourceLink(project=project, file_path=summary["file_path"]).to_dict(),
            "related_index_links": _related_index_links({"project": project, "file_path": summary["file_path"]}, search_type),
            "supported": summary["supported"],
            "language": summary["language"],
            "skeleton": summary["skeleton"],
            "symbols": summary["symbols"],
            "symbol_health": summary["symbol_health"],
        }
        _send_json(handler, HTTPStatus.OK, {"ok": True, "query": {"project": project, "file_path": file_path}, "results": [result]})
        return

    project = _query_value(query, "project")
    scope_type = _query_value(query, "scope_type")
    directory = _query_value(query, "directory")
    limit = _coerce_int(_query_value(query, "limit"), 10)
    offset = _coerce_int(_query_value(query, "offset"), 0)
    exclude_files = _query_list(query, "exclude_files")
    exclude_symbols = _query_list(query, "exclude_symbols")
    search_query = _query_value(query, "query")
    if not search_query:
        _send_error(handler, HTTPStatus.BAD_REQUEST, "query is required")
        return

    if search_type == "lexical":
        raw = projects.lexical_search(
            search_query,
            project=project,
            scope_type=scope_type,
            directory=directory,
            limit=limit,
            offset=offset,
            exclude_files=exclude_files,
            exclude_symbols=exclude_symbols,
        )
        results = [
            _normalize_search_result(item, "lexical")
            for item in raw.get("results", [])
            if _result_within_directory(item, directory)
        ]
        payload = {"ok": True, "query": raw, "results": results}
    elif search_type == "semantic":
        raw = projects.search_code(
            search_query,
            project=project,
            scope_type=scope_type,
            directory=directory,
            limit=limit,
            offset=offset,
            exclude_files=exclude_files,
            exclude_symbols=exclude_symbols,
        )["semantic"]
        results = [
            _normalize_search_result(item, "semantic")
            for item in raw.get("results", [])[offset : offset + limit]
            if _result_within_directory(item, directory)
        ]
        payload = {"ok": True, "query": raw, "results": results}
    elif search_type == "unified":
        raw = projects.search_code(
            search_query,
            project=project,
            scope_type=scope_type,
            directory=directory,
            limit=limit,
            offset=offset,
            exclude_files=exclude_files,
            exclude_symbols=exclude_symbols,
        )
        payload = {
            "ok": True,
            "query": raw,
            "results": [
                item
                for item in _normalize_unified_results(raw)
                if _result_within_directory(item, directory)
            ],
        }
    else:
        _send_error(handler, HTTPStatus.NOT_FOUND, "Unknown search route")
        return
    _send_json(handler, HTTPStatus.OK, payload)


class ControlPlaneHandler(BaseHTTPRequestHandler):
    server_version = "AgentCodeAnalyzerControlPlane/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        segments = _split_path(parsed.path)
        query = parse_qs(parsed.query)
        if parsed.path in {"/", "/api", "/api/health"}:
            _send_json(self, HTTPStatus.OK, {"ok": True, "service": "agent-code-analyzer-control-plane"})
            return
        if len(segments) >= 2 and segments[0] == "api" and segments[1] == "projects":
            _handle_projects(self, segments, query)
            return
        if len(segments) >= 2 and segments[0] == "api" and segments[1] == "search":
            _handle_search(self, segments, query)
            return
        _send_error(self, HTTPStatus.NOT_FOUND, "Unknown route")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        segments = _split_path(parsed.path)
        query = parse_qs(parsed.query)
        if len(segments) >= 2 and segments[0] == "api" and segments[1] == "projects":
            _handle_projects(self, segments, query)
            return
        _send_error(self, HTTPStatus.NOT_FOUND, "Unknown route")

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        segments = _split_path(parsed.path)
        query = parse_qs(parsed.query)
        if len(segments) >= 2 and segments[0] == "api" and segments[1] == "projects":
            _handle_projects(self, segments, query)
            return
        _send_error(self, HTTPStatus.NOT_FOUND, "Unknown route")


def create_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    resolved_host = host or os.environ.get("AGENT_CODE_ANALYZER_API_HOST", DEFAULT_API_HOST)
    resolved_port = port if port is not None else int(os.environ.get("AGENT_CODE_ANALYZER_API_PORT", str(DEFAULT_API_PORT)))
    return ThreadingHTTPServer((resolved_host, resolved_port), ControlPlaneHandler)


def main() -> None:
    host = os.environ.get("AGENT_CODE_ANALYZER_API_HOST", DEFAULT_API_HOST)
    port = int(os.environ.get("AGENT_CODE_ANALYZER_API_PORT", str(DEFAULT_API_PORT)))
    server = create_server(host=host, port=port)
    try:
        print(f"control plane listening on http://{host}:{port}", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
