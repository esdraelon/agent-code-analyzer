from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from agent_code_analyzer.agents.base import AgentKind, AgentRequest, AgentResponse
from agent_code_analyzer.parsing import analyze_file
from agent_code_analyzer.semantic_agent import (
    NO_SEMANTIC_DESCRIPTION,
    AgentSemanticWriter,
    NoSemanticDescription,
    SemanticTransportError,
    SemanticWriteRequest,
    SemanticWriteResult,
    StubSemanticWriter,
    is_no_semantic_description,
)
from agent_code_analyzer.semantic_descriptions import build_semantic_description_record
from agent_code_analyzer.vector_index import QdrantVectorIndex


class FakeEmbeddingProvider:
    vector_size = 3

    def embed_document(self, text: str) -> list[float]:
        base = float(len(text) % 7)
        return [base, base + 1.0, base + 2.0]

    def embed_query(self, text: str) -> list[float]:
        base = float(len(text) % 5)
        return [base + 3.0, base + 4.0, base + 5.0]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.deleted_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []
        self.collection_exists_value = True

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_exists_value

    def create_collection(self, **kwargs) -> None:
        self.collection_exists_value = True

    def delete(self, **kwargs) -> None:
        self.deleted_calls.append(kwargs)

    def upsert(self, **kwargs) -> None:
        self.upsert_calls.append(kwargs)


class EchoAgent:
    kind: ClassVar[AgentKind] = "fake"

    def __init__(self, response: str) -> None:
        self.response = response
        self.seen: list[AgentRequest] = []

    def complete(self, request: AgentRequest) -> AgentResponse:
        self.seen.append(request)
        return AgentResponse(content=self.response, agent_kind=self.kind, raw_output=self.response, parsed=self.response)


class ExplodingAgent:
    kind: ClassVar[AgentKind] = "fake"

    def complete(self, request: AgentRequest) -> AgentResponse:
        raise RuntimeError("backend offline")


class CapturingWriter:
    kind: ClassVar[str] = "capture"

    def __init__(self) -> None:
        self.requests: list[SemanticWriteRequest] = []

    def write(self, request: SemanticWriteRequest) -> SemanticWriteResult:
        self.requests.append(request)
        return SemanticWriteResult(
            request=request,
            response=NO_SEMANTIC_DESCRIPTION,
            backend=self.kind,
            metadata={"mode": "test"},
        )


def test_stub_writer_returns_explicit_sentinel() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
    )
    request = SemanticWriteRequest(record=record, source_text="def hello():\n    return 1\n")

    result = StubSemanticWriter().write(request)

    assert result.backend == "semantic-stub"
    assert result.response is NO_SEMANTIC_DESCRIPTION
    assert result.is_no_response is True
    assert result.description_text is None
    assert result.metadata["mode"] == "stub"
    assert is_no_semantic_description(result.response) is True
    assert isinstance(NO_SEMANTIC_DESCRIPTION, NoSemanticDescription)


def test_agent_semantic_writer_returns_text_and_records_request() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="method",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
        symbol_path="App.run",
        line_start=10,
        line_end=20,
    )
    agent = EchoAgent("Summarizes the method intent.")
    writer = AgentSemanticWriter(agent, system_prompt="You are concise.")

    result = writer.write(SemanticWriteRequest(record=record, source_text="def run():\n    return 1\n", outline_text="Function: run"))

    assert result.backend == "fake"
    assert result.response == "Summarizes the method intent."
    assert result.description_text == "Summarizes the method intent."
    assert result.is_no_response is False
    assert agent.seen[0].system_prompt == "You are concise."
    assert "Output hint: concise" in agent.seen[0].prompt
    assert "Function: run" in agent.seen[0].prompt


def test_agent_semantic_writer_returns_sentinel_for_blank_output() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
    )
    writer = AgentSemanticWriter(EchoAgent("   "))

    result = writer.write(SemanticWriteRequest(record=record, source_text="print('hi')\n"))

    assert result.is_no_response is True
    assert result.response is NO_SEMANTIC_DESCRIPTION
    assert result.description_text is None


def test_agent_semantic_writer_wraps_backend_failures() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
    )
    writer = AgentSemanticWriter(ExplodingAgent())

    with pytest.raises(SemanticTransportError, match="backend offline"):
        writer.write(SemanticWriteRequest(record=record, source_text="print('hi')\n"))


def test_vector_index_calls_semantic_writer_without_crashing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    file_path = root / "app.py"
    file_path.write_text("def hello(name):\n    return name.upper()\n", encoding="utf-8")

    analysis = analyze_file(str(file_path))
    writer = CapturingWriter()
    index = QdrantVectorIndex(url="http://example.test", embedding_provider=FakeEmbeddingProvider(), semantic_writer=writer)
    fake_client = FakeQdrantClient()
    object.__setattr__(index, "_client", fake_client)

    result = index.sync_analysis(
        project="demo",
        project_root=root,
        file_id=7,
        file_path=str(file_path),
        analysis=analysis,
        indexed_at="2026-06-19T21:00:00",
        file_size=file_path.stat().st_size,
        file_mtime_ns=file_path.stat().st_mtime_ns,
    )

    assert result["synced"] is True
    assert len(writer.requests) == 2
    assert writer.requests[0].record.scope_type == "file"
    assert writer.requests[1].record.scope_type == "method"
    assert fake_client.upsert_calls
    payloads = fake_client.upsert_calls[0]["points"]
    assert payloads[0].payload["semantic_description_state"] == "no_response"
    assert payloads[0].payload["semantic_description_backend"] == "capture"
    assert payloads[1].payload["semantic_description_state"] == "no_response"
