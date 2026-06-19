from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

AgentKind = Literal["fake", "hermes-shell", "hermes-lib"]
ResponseFormat = Literal["text", "json"]


@dataclass(slots=True)
class AgentRequest:
    """Normalized request payload for every agent backend."""

    prompt: str
    system_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    response_format: ResponseFormat = "text"


@dataclass(slots=True)
class AgentResponse:
    """Normalized response payload returned by every agent backend."""

    content: str
    agent_kind: AgentKind
    raw_output: str = ""
    parsed: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    """Uniform call surface used by callers and wrappers."""

    kind: ClassVar[AgentKind]

    def complete(self, request: AgentRequest) -> AgentResponse:
        ...


class BaseAgent(ABC):
    """Shared helpers for concrete agent implementations."""

    kind: ClassVar[AgentKind]

    def __init__(self, *, log_dir: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir) if log_dir is not None else None

    def _normalized_metadata(self, request: AgentRequest, **extra: Any) -> dict[str, Any]:
        payload = dict(request.metadata)
        payload.update(extra)
        return payload

    def _request_record(self, request: AgentRequest, *, backend: str, response: str | None = None) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_kind": self.kind,
            "backend": backend,
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "response_format": request.response_format,
            "metadata": dict(request.metadata),
        }
        if response is not None:
            record["response"] = response
        return record

    def _write_jsonl(self, record: dict[str, Any]) -> Path | None:
        if self.log_dir is None:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / "requests.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(record, ensure_ascii=False) + "\n")
        return path


class AgentCaller:
    """Thin wrapper that invokes a concrete agent implementation."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def call(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        metadata: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
    ) -> AgentResponse:
        request = AgentRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            metadata=metadata or {},
            response_format=response_format,
        )
        return self.agent.complete(request)


class AgentBuildError(RuntimeError):
    """Raised when a requested backend cannot be constructed."""


def build_agent(kind: AgentKind, **kwargs: Any) -> Agent:
    """Factory for the concrete agent strategies used by the POC."""

    if kind == "fake":
        from .fake import FakeAgent

        return FakeAgent(**kwargs)
    if kind == "hermes-shell":
        from .hermes import HermesShellAgent

        return HermesShellAgent(**kwargs)
    if kind == "hermes-lib":
        from .hermes import HermesLibAgent

        return HermesLibAgent(**kwargs)
    raise AgentBuildError(f"Unknown agent kind: {kind}")
