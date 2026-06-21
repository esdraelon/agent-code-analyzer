from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .base import AgentKind, AgentRequest, AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


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
        with self._rate_limit_context():
            logger.info(
                "fake_agent_request prompt_length=%d response_format=%s metadata_keys=%s",
                len(request.prompt),
                request.response_format,
                sorted(request.metadata.keys()),
            )
            parsed = self._fake_parsed_output(request)
            response = AgentResponse(
                content=self.placeholder,
                agent_kind="fake",
                raw_output=self.placeholder,
                parsed=parsed,
                metadata=self._normalized_metadata(request, placeholder=self.placeholder),
            )
            self._write_jsonl(self._request_record(request, backend="fake", response=response.content))
            logger.info(
                "fake_agent_response response_length=%d parsed_type=%s",
                len(response.content),
                type(response.parsed).__name__,
            )
            return response
