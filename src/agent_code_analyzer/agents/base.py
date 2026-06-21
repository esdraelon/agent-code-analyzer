from __future__ import annotations

import json
import logging
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from ..config import get_config
from ..rate_limit import RateLimitError, get_global_rate_limiter, normalized_rate_limit_signal, sleep_for_signal

logger = logging.getLogger(__name__)


def _preview_text(value: str, *, limit: int = 160) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


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
        resolved_log_dir = log_dir
        if resolved_log_dir is None:
            resolved_log_dir = get_config().logging.log_dir
        self.log_dir = Path(resolved_log_dir) if resolved_log_dir is not None else None

    def _rate_limit_context(self):
        return get_global_rate_limiter().acquire()

    def _raise_rate_limited(self, error: Exception, *, backend: str) -> None:
        signal = normalized_rate_limit_signal(error, backend=backend)
        if signal is None:
            raise error
        sleep_for_signal(signal)
        raise RateLimitError(signal) from error

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
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / "requests.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # pragma: no cover - depends on filesystem permissions
            logger.warning(
                "agent_request_log_write_failed agent_kind=%s log_dir=%r error=%s",
                self.kind,
                self.log_dir,
                exc,
            )
            return None
        logger.info(
            "agent_request_logged agent_kind=%s backend=%s log_path=%s prompt_length=%d response_present=%s",
            record.get("agent_kind"),
            record.get("backend"),
            path,
            len(str(record.get("prompt", ""))),
            "response" in record,
        )
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
        logger.info(
            "agent_call_dispatch agent_kind=%s response_format=%s prompt_length=%d metadata_keys=%s",
            getattr(self.agent, "kind", "unknown"),
            response_format,
            len(prompt),
            sorted((metadata or {}).keys()),
        )
        response = self.agent.complete(request)
        logger.info(
            "agent_call_complete agent_kind=%s response_length=%d parsed_type=%s",
            response.agent_kind,
            len(response.content),
            type(response.parsed).__name__,
        )
        return response


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
