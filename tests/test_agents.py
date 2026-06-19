from __future__ import annotations

from typing import Any, cast
from pathlib import Path

import json
import pytest

from agent_code_analyzer.agents import (
    AgentCaller,
    AgentRequest,
    FakeAgent,
    HermesLibAgent,
    HermesShellAgent,
    build_agent,
)


class _CompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_fake_agent_returns_placeholder_and_logs(tmp_path: Path) -> None:
    agent = FakeAgent(log_dir=tmp_path)
    response = agent.complete(
        AgentRequest(
            prompt="Evaluate the semantic summary",
            metadata={"scope": "method"},
        )
    )

    assert response.content == "No detail here"
    assert response.agent_kind == "fake"
    assert response.parsed == "No detail here"

    log_path = tmp_path / "requests.jsonl"
    assert log_path.exists()
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["backend"] == "fake"
    assert record["prompt"] == "Evaluate the semantic summary"
    assert record["response"] == "No detail here"


def test_fake_agent_can_emit_placeholder_json(tmp_path: Path) -> None:
    agent = FakeAgent(log_dir=tmp_path)
    response = agent.complete(
        AgentRequest(
            prompt="Return structured output",
            response_format="json",
            metadata={"kind": "structured"},
        )
    )

    assert response.content == "No detail here"
    assert response.parsed == {
        "detail": "No detail here",
        "metadata": {"kind": "structured"},
        "prompt_length": len("Return structured output"),
    }


def test_shell_agent_builds_command_and_parses_output(monkeypatch) -> None:
    seen = {}

    def fake_run(command, capture_output, text, check):  # noqa: ANN001
        seen["command"] = command
        seen["capture_output"] = capture_output
        seen["text"] = text
        seen["check"] = check
        return _CompletedProcess(stdout="No detail here\n")

    monkeypatch.setattr("agent_code_analyzer.agents.hermes.subprocess.run", fake_run)
    agent = HermesShellAgent(hermes_executable="hermes-bin", model="m1", provider="p1")
    response = agent.complete(AgentRequest(prompt="Assess the plan"))

    assert response.content == "No detail here"
    assert response.agent_kind == "hermes-shell"
    assert seen["command"] == [
        "hermes-bin",
        "chat",
        "--quiet",
        "--ignore-rules",
        "--source",
        "agent-code-analyzer-eval",
        "--query",
        "Assess the plan",
        "--model",
        "m1",
        "--provider",
        "p1",
    ]


def test_shell_agent_raises_on_nonzero_exit(monkeypatch) -> None:
    def fake_run(command, capture_output, text, check):  # noqa: ANN001
        return _CompletedProcess(stdout="", stderr="bad stuff", returncode=2)

    monkeypatch.setattr("agent_code_analyzer.agents.hermes.subprocess.run", fake_run)
    agent = HermesShellAgent()

    with pytest.raises(RuntimeError, match="exit code 2"):
        agent.complete(AgentRequest(prompt="Assess"))


def test_lib_agent_calls_run_agent_module(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes"
    hermes_root.mkdir()
    (hermes_root / "run_agent.py").write_text(
        """
class AIAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    def chat(self, prompt):
        return f"lib:{prompt}"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    agent = HermesLibAgent(hermes_repo_root=hermes_root, model="m2", provider="p2")
    response = agent.complete(AgentRequest(prompt="Summarize the architecture"))

    assert response.content == "lib:Summarize the architecture"
    assert response.agent_kind == "hermes-lib"
    assert response.parsed == "lib:Summarize the architecture"


def test_agent_caller_and_factory() -> None:
    fake = build_agent("fake")
    caller = AgentCaller(fake)
    response = caller.call("Hello")
    assert response.content == "No detail here"

    assert build_agent("hermes-shell", hermes_executable="hermes")
    assert build_agent("hermes-lib")


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(Exception, match="Unknown agent kind"):
        build_agent(cast(Any, "bogus"))
