from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install.py"


def load_install_module():
    spec = importlib.util.spec_from_file_location("install_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_requirements_requires_fswatch(monkeypatch) -> None:
    module = load_install_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: "/usr/bin/uv" if command == "uv" else None)

    with pytest.raises(RuntimeError, match="fswatch"):
        module.validate_requirements()


def test_main_check_only_reports_success(monkeypatch, capsys) -> None:
    module = load_install_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0))

    assert module.main(["--check-only"]) == 0
    captured = capsys.readouterr()
    assert "requirements look good" in captured.out


def test_install_runs_uv_sync_and_import_check(monkeypatch) -> None:
    module = load_install_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/bin/{command}")

    commands: list[list[str]] = []

    def fake_run(command, cwd=None, check=False):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.install()

    assert commands[0][:3] == ["/usr/bin/uv", "sync", "--all-extras"]
    assert commands[1] == [
        "/usr/bin/uv",
        "run",
        "python",
        "-c",
        "import agent_code_analyzer, mcp, tree_sitter, tree_sitter_languages",
    ]


def test_install_runner_exposes_default_requirements() -> None:
    module = load_install_module()
    runner = module.InstallRunner()

    assert runner.config.required_commands == ("uv", "fswatch")
    assert runner.config.required_modules == (
        "agent_code_analyzer",
        "mcp",
        "tree_sitter",
        "tree_sitter_languages",
    )
