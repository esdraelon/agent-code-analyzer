from __future__ import annotations

from pathlib import Path

from agent_code_analyzer import project_storage as storage
from agent_code_analyzer.ingestion_state import (
    begin_ingestion_checkpoint,
    complete_ingestion_checkpoint,
    load_active_ingestion_checkpoints,
    load_ingestion_checkpoint,
    recover_incomplete_ingestion,
)
from agent_code_analyzer.projects import add_project, list_projects


def _isolate_project_state(tmp_path: Path, monkeypatch) -> None:
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    monkeypatch.setattr(storage, "DATA_DIR", state_dir)
    monkeypatch.setattr(storage, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(storage, "PROJECTS_DIR", state_dir / "projects")


def test_recover_incomplete_ingestion_runs_only_active_checkpoints_once(tmp_path: Path, monkeypatch) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    active_root = tmp_path / "active"
    complete_root = tmp_path / "complete"
    active_root.mkdir()
    complete_root.mkdir()
    (active_root / "app.py").write_text("def active():\n    return 1\n", encoding="utf-8")
    (complete_root / "done.py").write_text("def done():\n    return 2\n", encoding="utf-8")

    add_project("active", str(active_root), mode="file")
    add_project("complete", str(complete_root), mode="file")

    active_db = Path(list_projects()[0]["db_path"])
    complete_db = Path(list_projects()[1]["db_path"])

    begin_ingestion_checkpoint(
        active_db,
        project="active",
        root_path=active_root,
        mode="semantic_refresh",
        phase="gap_sweep",
        total_file_count=1,
    )
    begin_ingestion_checkpoint(
        complete_db,
        project="complete",
        root_path=complete_root,
        mode="semantic_rebuild",
        phase="full_rebuild",
        total_file_count=1,
    )
    complete_ingestion_checkpoint(complete_db, project="complete")

    calls: list[str] = []

    def fake_sync(project: str) -> dict[str, object]:
        calls.append(project)
        db_path = Path(next(item["db_path"] for item in list_projects() if item["name"] == project))
        complete_ingestion_checkpoint(db_path, project=project)
        return {"project": project, "changed_file_count": 0, "deleted_file_count": 0, "unchanged_file_count": 1}

    recovered = recover_incomplete_ingestion(sync_callback=fake_sync)
    assert calls == ["active"]
    assert recovered == [{"project": "active", "changed_file_count": 0, "deleted_file_count": 0, "unchanged_file_count": 1}]
    assert load_active_ingestion_checkpoints(active_db) == []
    assert load_ingestion_checkpoint(active_db, "active") is not None
    assert load_ingestion_checkpoint(active_db, "active").status == "completed"
    assert load_ingestion_checkpoint(complete_db, "complete") is not None
    assert load_ingestion_checkpoint(complete_db, "complete").status == "completed"

    second_pass = recover_incomplete_ingestion(sync_callback=fake_sync)
    assert second_pass == []
    assert calls == ["active"]
