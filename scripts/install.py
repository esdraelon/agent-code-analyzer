#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

REQUIRED_PYTHON = (3, 11)
REQUIRED_COMMANDS = ("uv", "fswatch")
REQUIRED_MODULES = (
    "agent_code_analyzer",
    "mcp",
    "tree_sitter",
    "tree_sitter_languages",
)


class InstallConfig:
    def __init__(
        self,
        required_python: tuple[int, int] = REQUIRED_PYTHON,
        required_commands: tuple[str, ...] = REQUIRED_COMMANDS,
        required_modules: tuple[str, ...] = REQUIRED_MODULES,
    ) -> None:
        self.required_python = required_python
        self.required_commands = required_commands
        self.required_modules = required_modules


class InstallRunner:
    def __init__(
        self,
        config: InstallConfig | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess] | None = None,
        command_resolver: Callable[[str], str | None] | None = None,
        root_resolver: Callable[[], Path] | None = None,
    ) -> None:
        self.config = config or InstallConfig()
        self.command_runner = command_runner or subprocess.run
        self.command_resolver = command_resolver or shutil.which
        self.root_resolver = root_resolver or (lambda: Path(__file__).resolve().parent.parent)

    def missing_commands(self) -> list[str]:
        return [command for command in self.config.required_commands if self.command_resolver(command) is None]

    def validate_requirements(self) -> None:
        if sys.version_info < self.config.required_python:
            raise RuntimeError(
                f"Python {self.config.required_python[0]}.{self.config.required_python[1]}+ is required, "
                f"but this interpreter is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            )

        missing = self.missing_commands()
        if missing:
            missing_list = ", ".join(missing)
            hint = "Install the missing command(s) and retry."
            if "fswatch" in missing:
                hint = (
                    "Install fswatch with your platform package manager before running this script. "
                    "For example: macOS (brew install fswatch) or Linux (apt install fswatch / your distro equivalent)."
                )
            raise RuntimeError(f"Missing required command(s): {missing_list}. {hint}")

    def build_sync_command(self) -> list[str]:
        uv = self.command_resolver("uv") or "uv"
        return [uv, "sync", "--all-extras", "--locked"]

    def build_import_check_command(self) -> list[str]:
        uv = self.command_resolver("uv") or "uv"
        import_check = "import " + ", ".join(self.config.required_modules)
        return [uv, "run", "python", "-c", import_check]

    def install(self) -> None:
        self.validate_requirements()
        root = self.root_resolver()

        print("[install] syncing dependencies with uv")
        _run(self.build_sync_command(), cwd=root, command_runner=self.command_runner)

        print("[install] verifying package imports")
        _run(self.build_import_check_command(), cwd=root, command_runner=self.command_runner)

        print("[install] requirements validated and installation complete")


DEFAULT_RUNNER = InstallRunner()




def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    completed = command_runner(command, cwd=str(cwd) if cwd else None, check=False)
    if completed.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {joined}")


def _missing_commands() -> list[str]:
    return [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]


def validate_requirements() -> None:
    InstallRunner().validate_requirements()


def install() -> None:
    InstallRunner().install()


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
