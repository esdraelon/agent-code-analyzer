from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_code_analyzer import __version__
from agent_code_analyzer.parsing import ast_skeleton, detect_language, list_symbols
from agent_code_analyzer.projects import add_project, ingest_project_tree, list_projects, search_projects
from agent_code_analyzer.server import (
    detect_source_language,
    generate_ast_skeleton,
    list_code_symbols,
    parse_source,
)


def test_project_registration_and_directory_ingest(tmp_path: Path, monkeypatch) -> None:
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")

    root = tmp_path / "alpha"
    (root / "src").mkdir(parents=True)
    (root / "src" / "one.py").write_text(
        """
class Greeter:
    def greet(self, name):
        return f\"hello {name}\"\n

def top_level():
    return 42
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "src" / "two.ts").write_text(
        """
export function add(a: number, b: number) {
  return a + b;
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    added = add_project("alpha", str(root), mode="directory", description="primary codebase")
    assert added["name"] == "alpha"
    assert added["mode"] == "directory"
    assert added["ingest"]["file_count"] == 2
    assert added["ingest"]["symbol_count"] >= 2

    project_db = Path(added["db_path"])
    assert projects.METADATA_DB.exists()
    assert project_db.exists()

    with sqlite3.connect(projects.METADATA_DB) as conn:
        row = conn.execute("SELECT name, root_path, db_path FROM projects WHERE name = ?", ("alpha",)).fetchone()
        assert row == ("alpha", str(root.resolve()), str(project_db))

    with sqlite3.connect(project_db) as conn:
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        assert file_count == 2
        assert symbol_count >= 2
        stored = conn.execute("SELECT rel_path, language, skeleton FROM files ORDER BY rel_path ASC").fetchone()
        assert stored[0] == "src/one.py"
        assert stored[1] == "python"
        assert "Greeter" in stored[2]

    projects_list = list_projects()
    assert len(projects_list) == 1
    assert projects_list[0]["name"] == "alpha"

    searched = search_projects("primary")
    assert len(searched) == 1
    assert searched[0]["name"] == "alpha"

    summary = ingest_project_tree("alpha", refresh=False)
    assert summary["project"] == "alpha"
    assert summary["file_count"] == 2

    parsed = parse_source("alpha", "src/one.py")
    assert parsed["supported"] is True
    assert parsed["language"] == "python"
    assert "skeleton" in parsed

    assert "[class_definition] class Greeter:" in generate_ast_skeleton("alpha", "src/one.py")
    assert detect_source_language("alpha", "src/one.py") == "python"
    assert "Greeter" in list_code_symbols("alpha", "src/one.py")


def test_file_level_tools_respect_project_scope(tmp_path: Path, monkeypatch) -> None:
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")

    root = tmp_path / "beta"
    root.mkdir()
    source = root / "notes.py"
    source.write_text("def hi():\n    return 1\n", encoding="utf-8")

    add_project("beta", str(root), mode="file")

    assert detect_language(str(source)) == "python"
    assert ast_skeleton(str(source)).strip() == "[function_definition] def hi():"
    assert list_symbols(str(source))[0]["name"] == "hi"

    parsed = parse_source("beta", "notes.py")
    assert parsed["supported"] is True
    assert parsed["language"] == "python"
    assert __version__ == "0.1.0"
