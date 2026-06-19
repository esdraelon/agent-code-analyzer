from __future__ import annotations

import importlib
import json
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Iterator

from .base import AgentKind, AgentRequest, AgentResponse, BaseAgent


@contextmanager
def _temporarily_on_sys_path(path: Path | None) -> Iterator[None]:
    inserted = False
    candidate: str | None = None
    if path is not None:
        candidate = str(path)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
            inserted = True
    try:
        yield
    finally:
        if inserted and candidate is not None:
            try:
                sys.path.remove(candidate)
            except ValueError:
                pass


@dataclass(slots=True)
class HermesShellAgent(BaseAgent):
    """Hermes adapter that shells out to the CLI."""

    kind: ClassVar[AgentKind] = "hermes-shell"

    def __init__(
        self,
        *,
        hermes_executable: str = "hermes",
        model: str | None = None,
        provider: str | None = None,
        log_dir: str | Path | None = None,
        source: str = "agent-code-analyzer-eval",
    ) -> None:
        BaseAgent.__init__(self, log_dir=log_dir)
        self.hermes_executable = hermes_executable
        self.model = model
        self.provider = provider
        self.source = source

    def _build_command(self, request: AgentRequest) -> list[str]:
        command = [
            self.hermes_executable,
            "chat",
            "--quiet",
            "--ignore-rules",
            "--source",
            self.source,
            "--query",
            request.prompt,
        ]
        if self.model:
            command.extend(["--model", self.model])
        if self.provider:
            command.extend(["--provider", self.provider])
        return command

    def complete(self, request: AgentRequest) -> AgentResponse:
        command = self._build_command(request)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Hermes shell agent failed with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        content = completed.stdout.strip()
        response = AgentResponse(
            content=content,
            agent_kind="hermes-shell",
            raw_output=completed.stdout,
            parsed=content,
            metadata=self._normalized_metadata(
                request,
                command=command,
                returncode=completed.returncode,
                backend="shell",
            ),
        )
        self._write_jsonl(self._request_record(request, backend="shell", response=content))
        return response


@dataclass(slots=True)
class HermesLibAgent(BaseAgent):
    """Hermes adapter that imports and calls the Python library directly."""

    kind: ClassVar[AgentKind] = "hermes-lib"

    def __init__(
        self,
        *,
        hermes_repo_root: str | Path | None = None,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        log_dir: str | Path | None = None,
        source: str = "agent-code-analyzer-eval",
    ) -> None:
        BaseAgent.__init__(self, log_dir=log_dir)
        self.hermes_repo_root = Path(hermes_repo_root) if hermes_repo_root is not None else None
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.source = source

    def _load_run_agent(self) -> Any:
        with _temporarily_on_sys_path(self.hermes_repo_root):
            return importlib.import_module("run_agent")

    def _build_agent_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "quiet_mode": True,
            "skip_context_files": True,
            "skip_memory": True,
            "save_trajectories": False,
            "enabled_toolsets": [],
            "disabled_toolsets": [],
            "platform": self.source,
        }
        if self.model:
            kwargs["model"] = self.model
        if self.provider:
            kwargs["provider"] = self.provider
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs

    def complete(self, request: AgentRequest) -> AgentResponse:
        run_agent = self._load_run_agent()
        hermes_agent = run_agent.AIAgent(**self._build_agent_kwargs())
        content = hermes_agent.chat(request.prompt)
        if isinstance(content, dict):
            content_text = json.dumps(content, ensure_ascii=False)
            parsed: Any = content
        else:
            content_text = str(content)
            parsed = content_text
        response = AgentResponse(
            content=content_text,
            agent_kind="hermes-lib",
            raw_output=content_text,
            parsed=parsed,
            metadata=self._normalized_metadata(
                request,
                backend="library",
                hermes_repo_root=str(self.hermes_repo_root) if self.hermes_repo_root else None,
            ),
        )
        self._write_jsonl(self._request_record(request, backend="library", response=content_text))
        return response
