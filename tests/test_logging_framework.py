from __future__ import annotations

import logging
from pathlib import Path

from agent_code_analyzer import config as analyzer_config
from agent_code_analyzer.agents import AgentRequest, FakeAgent
from agent_code_analyzer.logging_config import setup_logging


def test_setup_logging_writes_to_configured_file(tmp_path: Path, monkeypatch) -> None:
    home_dir = tmp_path / "home"
    log_dir = tmp_path / "logs"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'''
[storage]
home_dir = "{home_dir}"

[logging]
level = "INFO"
log_dir = "{log_dir}"
log_file = "analyzer.log"
log_to_stderr = false
'''.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CODE_ANALYZER_CONFIG", str(config_file))
    analyzer_config.get_config.cache_clear()

    resolved = analyzer_config.get_config()
    root = setup_logging(resolved)
    root.info("framework smoke test")
    for handler in root.handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()

    log_path = Path(resolved.logging.log_dir or log_dir) / resolved.logging.log_file
    assert log_path.exists()
    assert "framework smoke test" in log_path.read_text(encoding="utf-8")

    analyzer_config.get_config.cache_clear()


def test_fake_agent_uses_default_request_log_dir(tmp_path: Path, monkeypatch, caplog) -> None:
    home_dir = tmp_path / "home"
    log_dir = home_dir / "logs"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'''
[storage]
home_dir = "{home_dir}"

[logging]
level = "INFO"
log_dir = "{log_dir}"
log_file = "analyzer.log"
log_to_stderr = false
'''.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CODE_ANALYZER_CONFIG", str(config_file))
    analyzer_config.get_config.cache_clear()

    resolved = analyzer_config.get_config()
    setup_logging(resolved)
    caplog.set_level(logging.INFO)

    agent = FakeAgent()
    response = agent.complete(AgentRequest(prompt="Summarize the subsystem", metadata={"scope": "file"}))

    assert response.content == "No detail here"
    request_log = Path(resolved.logging.log_dir or log_dir) / "requests.jsonl"
    assert request_log.exists()
    content = request_log.read_text(encoding="utf-8")
    assert "fake" in content
    assert "Summarize the subsystem" in content
    assert any("fake_agent_request" in record.message for record in caplog.records)
    assert any("agent_request_logged" in record.message for record in caplog.records)

    analyzer_config.get_config.cache_clear()
