from __future__ import annotations

from pathlib import Path

from agent_code_analyzer.parsing import _symbol_health_report, analyze_file
from agent_code_analyzer.projects import add_project, project_file_summary
from agent_code_analyzer.server import parse_source


def _isolate_project_state(tmp_path: Path, monkeypatch):
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_symbol_health_report_flags_parse_errors_duplicates_missing_names_and_depth() -> None:
    report = _symbol_health_report(
        [
            {"type": "function_definition", "name": "alpha", "depth": 0},
            {"type": "function_definition", "name": "alpha", "depth": 0},
            {"type": "function_definition", "name": "alpha", "depth": 0},
            {"type": "function_definition", "name": "", "depth": 1},
            {"type": "class_definition", "name": "deep", "depth": 4},
        ],
        has_error=True,
        max_depth=2,
    )

    assert report["healthy"] is False
    assert report["symbol_count"] == 5
    assert report["max_depth"] == 2
    assert "parse tree contains error nodes" in report["issues"]
    assert "symbol #3 is missing a name" in report["issues"]
    assert any("duplicate symbol name 'alpha'" in issue for issue in report["issues"])
    assert any("exceeds max depth 2" in issue for issue in report["issues"])


def test_analyze_file_exposes_symbol_health_for_duplicate_symbols(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.py"
    source.write_text(
        "def alpha():\n    return 1\n\n\ndef alpha():\n    return 2\n",
        encoding="utf-8",
    )

    analysis = analyze_file(str(source))
    health = analysis["symbol_health"]

    assert health["healthy"] is False
    assert health["symbol_count"] == 2
    assert any("duplicate symbol name 'alpha'" in issue for issue in health["issues"])


def test_project_summary_and_server_parse_source_surface_symbol_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "project"
    root.mkdir()
    source = root / "main.py"
    source.write_text("def hi():\n    return 1\n", encoding="utf-8")

    added = add_project("project", str(root), mode="directory")
    assert added["name"] == "project"

    summary = project_file_summary("project", "main.py")
    assert summary["symbol_health"]["healthy"] is True
    assert summary["symbol_health"]["issues"] == []
    assert summary["symbol_health"]["symbol_count"] == 1

    parsed = parse_source("project", "main.py")
    assert parsed["supported"] is True
    assert parsed["symbol_health"]["healthy"] is True
    assert parsed["symbol_health"]["issues"] == []
