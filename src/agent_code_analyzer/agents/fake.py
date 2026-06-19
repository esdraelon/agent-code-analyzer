from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .base import AgentKind, AgentRequest, AgentResponse, BaseAgent


@dataclass(slots=True)
class FakeAgent(BaseAgent):
    """Deterministic backend for proof-of-concept and offline tests."""

    kind: ClassVar[AgentKind] = "fake"

    def __init__(self, *, log_dir: str | Path | None = None, placeholder: str = "No detail here") -> None:
        BaseAgent.__init__(self, log_dir=log_dir)
        self.placeholder = placeholder

    def _fake_parsed_output(self, request: AgentRequest) -> Any:
        if request.response_format == "json":
            return {
                "detail": self.placeholder,
                "metadata": dict(request.metadata),
                "prompt_length": len(request.prompt),
            }
        return self.placeholder

    def complete(self, request: AgentRequest) -> AgentResponse:
        parsed = self._fake_parsed_output(request)
        response = AgentResponse(
            content=self.placeholder,
            agent_kind="fake",
            raw_output=self.placeholder,
            parsed=parsed,
            metadata=self._normalized_metadata(request, placeholder=self.placeholder),
        )
        self._write_jsonl(self._request_record(request, backend="fake", response=response.content))
        return response
