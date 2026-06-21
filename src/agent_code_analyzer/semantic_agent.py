from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, ClassVar, Mapping, Protocol

from .agents.base import Agent, AgentCaller, ResponseFormat, _preview_text, build_agent
from .config import AnalyzerConfig, get_config
from .semantic_descriptions import SemanticDescriptionRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NoSemanticDescription:
    """Explicit sentinel for intentional no-response writer outcomes."""

    reason: str = "stub"
    detail: str = "no semantic description generated"


NO_SEMANTIC_DESCRIPTION = NoSemanticDescription()


@dataclass(frozen=True, slots=True)
class SemanticWriteRequest:
    """Narrow request shape for semantic description generation."""

    record: SemanticDescriptionRecord
    source_text: str
    outline_text: str = ""
    output_hint: str = "concise"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SemanticWriteResult:
    """Normalized result for writer outcomes and sentinels."""

    request: SemanticWriteRequest
    response: str | NoSemanticDescription
    backend: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_no_response(self) -> bool:
        return isinstance(self.response, NoSemanticDescription)

    @property
    def description_text(self) -> str | None:
        if self.is_no_response:
            return None
        return self.response if isinstance(self.response, str) else None


class SemanticWriter(Protocol):
    kind: ClassVar[str]

    def write(self, request: SemanticWriteRequest) -> SemanticWriteResult:
        ...


class SemanticWriterError(RuntimeError):
    """Base error for semantic writer failures."""


class SemanticTransportError(SemanticWriterError):
    """Raised when the writer adapter cannot talk to its backend."""


class StubSemanticWriter:
    """Null-object semantic writer used until a real model backend exists."""

    kind: ClassVar[str] = "semantic-stub"

    def write(self, request: SemanticWriteRequest) -> SemanticWriteResult:
        return SemanticWriteResult(
            request=request,
            response=NO_SEMANTIC_DESCRIPTION,
            backend=self.kind,
            metadata={"mode": "stub", **dict(request.metadata)},
        )


class AgentSemanticWriter:
    """Adapter that routes semantic prompts through the agent abstraction."""

    kind: ClassVar[str] = "semantic-agent"

    def __init__(
        self,
        agent: Agent | AgentCaller,
        *,
        system_prompt: str = "",
        response_format: ResponseFormat = "text",
    ) -> None:
        if isinstance(agent, AgentCaller):
            self._caller = agent
        else:
            self._caller = AgentCaller(agent)
        self.system_prompt = system_prompt
        self.response_format: ResponseFormat = response_format

    def _build_prompt(self, request: SemanticWriteRequest) -> str:
        record = request.record
        parts = [
            f"Write a concise semantic description for {record.scope_type} scope.",
            f"Project: {record.project}",
            f"File: {record.file_path}",
        ]
        if record.symbol_path:
            parts.append(f"Symbol path: {record.symbol_path}")
        if record.line_start is not None or record.line_end is not None:
            parts.append(f"Lines: {record.line_start!r}-{record.line_end!r}")
        if record.parent_scope_id:
            parts.append(f"Parent scope: {record.parent_scope_id}")
        if request.outline_text.strip():
            parts.append("Outline:")
            parts.append(request.outline_text.strip())
        if request.source_text.strip():
            parts.append("Source:")
            parts.append(request.source_text.strip())
        parts.append(f"Output hint: {request.output_hint}")
        return "\n".join(parts)

    def write(self, request: SemanticWriteRequest) -> SemanticWriteResult:
        prompt = self._build_prompt(request)
        logger.info(
            "semantic_write_dispatch scope_type=%s file_path=%s backend_prompt_length=%d output_hint=%s",
            request.record.scope_type,
            request.record.file_path,
            len(prompt),
            request.output_hint,
        )
        try:
            response = self._caller.call(
                prompt,
                system_prompt=self.system_prompt,
                metadata=dict(request.metadata),
                response_format=self.response_format,
            )
        except Exception as exc:  # pragma: no cover - exercised through adapter failure tests
            logger.warning(
                "semantic_write_failed scope_type=%s file_path=%s error=%s prompt_preview=%s",
                request.record.scope_type,
                request.record.file_path,
                exc,
                _preview_text(prompt),
            )
            raise SemanticTransportError(str(exc)) from exc

        content = response.content.strip()
        if not content:
            logger.info(
                "semantic_write_empty scope_type=%s file_path=%s backend=%s",
                request.record.scope_type,
                request.record.file_path,
                response.agent_kind,
            )
            return SemanticWriteResult(
                request=request,
                response=NO_SEMANTIC_DESCRIPTION,
                backend=response.agent_kind,
                metadata={"mode": "agent", **dict(request.metadata)},
            )
        logger.info(
            "semantic_write_complete scope_type=%s file_path=%s backend=%s response_length=%d",
            request.record.scope_type,
            request.record.file_path,
            response.agent_kind,
            len(content),
        )
        return SemanticWriteResult(
            request=request,
            response=content,
            backend=response.agent_kind,
            metadata={"mode": "agent", **dict(request.metadata)},
        )


def build_semantic_writer(config: AnalyzerConfig | None = None) -> SemanticWriter:
    """Build the configured semantic writer backend.

    Defaults to the deterministic FakeAgent backend.
    """

    resolved = config or get_config()
    semantic = resolved.semantic
    backend = semantic.backend.strip().lower() or "fake"
    logger.info(
        "semantic_writer_backend_selected backend=%s model=%r provider=%r base_url=%r hermes_repo_root=%r",
        backend,
        semantic.model,
        semantic.provider,
        semantic.base_url,
        semantic.hermes_repo_root,
    )
    if backend == "stub":
        return StubSemanticWriter()
    if backend == "fake":
        return AgentSemanticWriter(build_agent("fake"), response_format="text")
    if backend == "hermes-shell":
        return AgentSemanticWriter(
            build_agent(
                "hermes-shell",
                hermes_executable=semantic.hermes_executable,
                model=semantic.model,
                provider=semantic.provider,
                source="agent-code-analyzer-semantic",
            ),
            response_format="text",
        )
    if backend == "hermes-lib":
        return AgentSemanticWriter(
            build_agent(
                "hermes-lib",
                hermes_repo_root=semantic.hermes_repo_root,
                model=semantic.model,
                provider=semantic.provider,
                base_url=semantic.base_url,
                api_key=semantic.api_key,
                source="agent-code-analyzer-semantic",
            ),
            response_format="text",
        )
    raise SemanticWriterError(f"Unknown semantic backend: {semantic.backend}")


def is_no_semantic_description(value: Any) -> bool:
    return isinstance(value, NoSemanticDescription)
