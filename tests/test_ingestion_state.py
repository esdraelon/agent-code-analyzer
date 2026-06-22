from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from agent_code_analyzer import project_storage as storage
from agent_code_analyzer.ingestion_state import (
    begin_ingestion_checkpoint,
    complete_ingestion_checkpoint,
    load_active_ingestion_checkpoints,
    load_ingestion_checkpoint,
    update_ingestion_checkpoint,
)
from agent_code_analyzer.projects import add_project


def _isolate_project_state(tmp_path: Path, monkeypatch) -> Any:
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    monkeypatch.setattr(storage, "DATA_DIR", state_dir)
    monkeypatch.setattr(storage, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(storage, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_ingestion_checkpoint_round_trips_through_sqlite(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "demo"
    root.mkdir()
    (root / "app.py").write_text("def hello():\n    return 'ok'\n", encoding="utf-8")

    added = add_project("demo", str(root), mode="file")
    db_path = Path(added["db_path"])

    started = begin_ingestion_checkpoint(
        db_path,
        project="demo",
        root_path=root,
        mode="semantic_refresh",
        phase="gap_sweep",
        total_file_count=1,
    )
    assert started.project_name == "demo"
    assert started.phase == "gap_sweep"
    assert started.status == "running"
    assert started.total_file_count == 1
    assert started.processed_file_count == 0
    assert started.completed_at is None

    updated = update_ingestion_checkpoint(
        db_path,
        project="demo",
        phase="gap_sweep",
        processed_file_count=1,
        last_file_path="app.py",
        last_file_mtime_ns=123,
        last_file_content_hash="abc123",
    )
    assert updated.processed_file_count == 1
    assert updated.last_file_path == "app.py"
    assert updated.last_file_mtime_ns == 123
    assert updated.last_file_content_hash == "abc123"

    loaded = load_ingestion_checkpoint(db_path, "demo")
    assert loaded is not None
    assert loaded.project_name == "demo"
    assert loaded.phase == "gap_sweep"
    assert loaded.status == "running"
    assert loaded.processed_file_count == 1

    active = load_active_ingestion_checkpoints(db_path)
    assert [checkpoint.project_name for checkpoint in active] == ["demo"]

    finished = complete_ingestion_checkpoint(db_path, project="demo")
    assert finished.status == "completed"
    assert finished.completed_at is not None

    assert load_ingestion_checkpoint(db_path, "demo") is not None
    assert load_active_ingestion_checkpoints(db_path) == []


def test_loading_missing_checkpoint_returns_none(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    db_path = tmp_path / "missing.sqlite3"
    with sqlite3.connect(db_path) as conn:
        storage._ensure_project_schema(conn)

    assert load_ingestion_checkpoint(db_path, "missing") is None
    assert load_active_ingestion_checkpoints(db_path) == []
