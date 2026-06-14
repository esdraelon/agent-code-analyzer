from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_code_analyzer.projects import add_project, list_projects, project_file_summary
from agent_code_analyzer.server import parse_source


def _isolate_project_state(tmp_path: Path, monkeypatch):
    import agent_code_analyzer.projects as projects

    state_dir = tmp_path / "state"
    monkeypatch.setattr(projects, "DATA_DIR", state_dir)
    monkeypatch.setattr(projects, "METADATA_DB", state_dir / "metadata.sqlite3")
    monkeypatch.setattr(projects, "PROJECTS_DIR", state_dir / "projects")
    return projects


def test_html_file_and_symbol_languages_cover_embedded_script_and_style(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "site"
    root.mkdir()
    sample = root / "index.html"
    sample.write_text(
        """
<!doctype html>
<html>
<head>
<style>
body { color: red; }
</style>
<script>
function hi() {
  return 1;
}
</script>
</head>
<body>Hello</body>
</html>
""".strip()
        + "\n",
        encoding="utf-8",
    )

    added = add_project("site", str(root), mode="directory")
    assert added["ingest"]["file_count"] == 1

    parsed = parse_source("site", "index.html")
    assert parsed["supported"] is True
    assert parsed["language"] == "html"
    assert parsed["languages"] == ["html", "javascript", "css"]
    assert any(symbol["name"] == "hi" and symbol["languages"] == ["javascript"] for symbol in parsed["symbols"])

    summary = project_file_summary("site", "index.html")
    assert summary["languages"] == ["html", "javascript", "css"]
    assert any(symbol["name"] == "hi" and symbol["languages"] == ["javascript"] for symbol in summary["symbols"])

    project_row = list_projects()[0]
    assert project_row["languages"] == ["html", "javascript", "css"]

    with sqlite3.connect(projects.METADATA_DB) as conn:
        file_row = conn.execute("SELECT languages FROM projects WHERE name = ?", ("site",)).fetchone()
        assert json.loads(file_row[0]) == ["html", "javascript", "css"]

        db_path = Path(added["db_path"])
    with sqlite3.connect(db_path) as conn:
        file_row = conn.execute("SELECT languages FROM files WHERE rel_path = ?", ("index.html",)).fetchone()
        assert json.loads(file_row[0]) == ["html", "javascript", "css"]


def test_php_symbols_collect_sql_language_coverage(tmp_path: Path, monkeypatch) -> None:
    projects = _isolate_project_state(tmp_path, monkeypatch)

    root = tmp_path / "api"
    root.mkdir()
    source = root / "query.php"
    source.write_text(
        """
<?php
function fetch_users() {
    $sql = "SELECT id, name FROM users WHERE active = 1";
    return $sql;
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    add_project("api", str(root), mode="file")

    parsed = parse_source("api", "query.php")
    assert parsed["supported"] is True
    assert parsed["language"] == "php"
    assert parsed["languages"] == ["php", "sql"]
    assert any(symbol["name"] == "fetch_users" and symbol["languages"] == ["php", "sql"] for symbol in parsed["symbols"])

    summary = project_file_summary("api", "query.php")
    assert summary["languages"] == ["php", "sql"]

    project_row = list_projects()[0]
    assert project_row["languages"] == ["php", "sql"]

    with sqlite3.connect(Path(projects.get_project("api")["db_path"])) as conn:
        file_row = conn.execute("SELECT languages FROM files WHERE rel_path = ?", ("query.php",)).fetchone()
        assert json.loads(file_row[0]) == ["php", "sql"]
        symbol_row = conn.execute("SELECT languages FROM symbols ORDER BY id ASC LIMIT 1").fetchone()
        assert json.loads(symbol_row[0]) == ["php", "sql"]
