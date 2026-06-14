#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_PYTHON = (3, 11)
REQUIRED_COMMANDS = ("uv", "fswatch")
REQUIRED_MODULES = (
    "agent_code_analyzer",
    "mcp",
    "tree_sitter",
    "tree_sitter_languages",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _missing_commands() -> list[str]:
    return [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]


def validate_requirements() -> None:
    if sys.version_info < REQUIRED_PYTHON:
        raise RuntimeError(
            f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ is required, "
            f"but this interpreter is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

    missing = _missing_commands()
    if missing:
        missing_list = ", ".join(missing)
        hint = "Install the missing command(s) and retry."
        if "fswatch" in missing:
            hint = (
                "Install fswatch with your platform package manager before running this script. "
                "For example: macOS (brew install fswatch) or Linux (apt install fswatch / your distro equivalent)."
            )
        raise RuntimeError(f"Missing required command(s): {missing_list}. {hint}")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    if completed.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {joined}")


def install() -> None:
    validate_requirements()

    uv = shutil.which("uv") or "uv"
    root = repo_root()

    print("[install] syncing dependencies with uv")
    _run([uv, "sync", "--all-extras", "--locked"], cwd=root)

    import_check = "import agent_code_analyzer, mcp, tree_sitter, tree_sitter_languages"
    print("[install] verifying package imports")
    _run([uv, "run", "python", "-c", import_check], cwd=root)

    print("[install] requirements validated and installation complete")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install and validate agent-code-analyzer requirements.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate prerequisites without syncing dependencies.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_requirements()

    if args.check_only:
        print("[install] requirements look good")
        return 0

    install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
