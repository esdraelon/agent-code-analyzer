from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parsing import analyze_file, detect_language

DATA_DIR = Path(os.environ.get("AGENT_CODE_ANALYZER_HOME", Path.home() / ".agent-code-analyzer"))
REGISTRY_FILE = DATA_DIR / "projects.json"
INDEX_DIR = DATA_DIR / "indexes"
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "venv",
    "__pycache__",
}


@dataclass(frozen=True)
class ProjectRecord:
    name: str
    root_path: str
    mode: str
    description: str
    created_at: str
    updated_at: str
    indexed_at: str | None = None
    file_count: int = 0
    supported_file_count: int = 0
    symbol_count: int = 0
    index_path: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    slug = slug.strip(".-_")
    return slug or "project"


def _load_registry() -> dict[str, dict[str, Any]]:
    _ensure_storage()
    if not REGISTRY_FILE.exists():
        return {}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_registry(registry: dict[str, dict[str, Any]]) -> None:
    _ensure_storage()
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def _project_index_path(name: str) -> Path:
    return INDEX_DIR / f"{_slugify(name)}.json"


def _normalize_project(project: str) -> str:
    return project.strip()


def list_projects() -> list[dict[str, Any]]:
    registry = _load_registry()
    projects = []
    for name in sorted(registry):
        item = registry[name].copy()
        item["name"] = name
        projects.append(item)
    return projects


def search_projects(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return list_projects()

    matches: list[dict[str, Any]] = []
    for project in list_projects():
        haystack = " ".join(
            str(project.get(key, "")) for key in ("name", "root_path", "mode", "description")
        ).lower()
        if needle in haystack:
            matches.append(project)
    return matches


def get_project(project: str) -> dict[str, Any]:
    project = _normalize_project(project)
    registry = _load_registry()
    if project not in registry:
        raise ValueError(f"Unknown project: {project}")
    result = registry[project].copy()
    result["name"] = project
    return result


def add_project(project: str, root_path: str, mode: str = "file", description: str = "") -> dict[str, Any]:
    project = _normalize_project(project)
    mode = mode.strip().lower()
    if mode not in {"file", "directory"}:
        raise ValueError("mode must be 'file' or 'directory'")

    root = Path(root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")

    registry = _load_registry()
    existing = registry.get(project, {})
    created_at = existing.get("created_at", _now())
    updated_at = _now()
    index_path = str(_project_index_path(project)) if mode == "directory" else existing.get("index_path")

    record = ProjectRecord(
        name=project,
        root_path=str(root),
        mode=mode,
        description=description.strip() or existing.get("description", ""),
        created_at=created_at,
        updated_at=updated_at,
        indexed_at=existing.get("indexed_at"),
        file_count=int(existing.get("file_count", 0) or 0),
        supported_file_count=int(existing.get("supported_file_count", 0) or 0),
        symbol_count=int(existing.get("symbol_count", 0) or 0),
        index_path=index_path,
    )

    registry[project] = {
        "root_path": record.root_path,
        "mode": record.mode,
        "description": record.description,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "indexed_at": record.indexed_at,
        "file_count": record.file_count,
        "supported_file_count": record.supported_file_count,
        "symbol_count": record.symbol_count,
        "index_path": record.index_path,
    }
    _save_registry(registry)

    result = get_project(project)
    if mode == "directory":
        result["ingest"] = ingest_project_tree(project, refresh=True)
    return result


def resolve_project_path(project: str, file_path: str) -> Path:
    project_data = get_project(project)
    root = Path(project_data["root_path"]).resolve()
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside project root: {file_path}") from exc

    if not candidate.exists():
        raise ValueError(f"File does not exist: {candidate}")
    return candidate


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") and path.suffix == "":
            continue
        if detect_language(str(path)):
            files.append(path)
    return sorted(files)


def ingest_project_tree(project: str, refresh: bool = False) -> dict[str, Any]:
    project_data = get_project(project)
    root = Path(project_data["root_path"])
    index_path = Path(project_data["index_path"] or _project_index_path(project))

    if index_path.exists() and not refresh:
        cached = json.loads(index_path.read_text(encoding="utf-8"))
        return cached["summary"]

    files = _iter_source_files(root)
    file_entries: list[dict[str, Any]] = []
    total_symbols = 0

    for path in files:
        analysis = analyze_file(str(path))
        parsed = analysis["parsed"]
        rel_path = str(path.relative_to(root))
        root_node = parsed.tree.root_node
        file_entries.append(
            {
                "path": rel_path,
                "language": parsed.language,
                "root_type": root_node.type,
                "node_count": root_node.descendant_count,
                "has_error": root_node.has_error,
                "skeleton": analysis["skeleton"],
                "symbols": analysis["symbols"],
            }
        )
        total_symbols += len(analysis["symbols"])

    summary = {
        "project": project,
        "root_path": str(root),
        "mode": project_data["mode"],
        "file_count": len(files),
        "supported_file_count": len(files),
        "symbol_count": total_symbols,
        "indexed_at": _now(),
    }
    payload = {"summary": summary, "files": file_entries}
    _ensure_storage()
    index_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    registry = _load_registry()
    if project in registry:
        registry[project]["indexed_at"] = summary["indexed_at"]
        registry[project]["file_count"] = summary["file_count"]
        registry[project]["supported_file_count"] = summary["supported_file_count"]
        registry[project]["symbol_count"] = summary["symbol_count"]
        registry[project]["index_path"] = str(index_path)
        registry[project]["updated_at"] = summary["indexed_at"]
        _save_registry(registry)

    return summary


def project_file_summary(project: str, file_path: str) -> dict[str, Any]:
    project_data = get_project(project)
    resolved = resolve_project_path(project, file_path)
    analysis = analyze_file(str(resolved))
    parsed = analysis["parsed"]
    root_node = parsed.tree.root_node
    return {
        "project": project,
        "file_path": str(resolved.relative_to(Path(project_data["root_path"]))),
        "supported": True,
        "language": parsed.language,
        "root_type": root_node.type,
        "node_count": root_node.descendant_count,
        "has_error": root_node.has_error,
        "byte_length": len(parsed.source_code.encode("utf-8")),
        "skeleton": analysis["skeleton"],
        "symbols": analysis["symbols"],
    }
