from __future__ import annotations

import sys
from pathlib import Path

from agent_code_analyzer import config as analyzer_config
from agent_code_analyzer.semantic_agent import build_semantic_writer, SemanticWriteRequest
from agent_code_analyzer.semantic_descriptions import build_semantic_description_record


def test_get_config_reads_file_and_env_overrides(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[storage]
home_dir = "~/custom-agent-home"
sqlite_connect_timeout_seconds = 7.5
sqlite_busy_timeout_ms = 9000

[vector]
qdrant_url = "http://qdrant.example:6333"
qdrant_collection = "custom_collection"
embedding_model = "custom/model"

[chunking]
max_chunk_lines = 21
min_split_lines = 13

[rate_limit]
capacity = 2
refill_per_second = 1.5
concurrency_limit = 1

[semantic]
backend = "hermes-lib"
hermes_repo_root = "/tmp/hermes"
model = "model-a"
provider = "provider-a"
base_url = "https://example.invalid"
api_key = "secret-a"

[logging]
level = "DEBUG"
log_dir = "/tmp/custom-logs"
log_file = "analyzer.log"
log_to_stderr = false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CODE_ANALYZER_CONFIG", str(config_file))
    monkeypatch.setenv("AGENT_CODE_ANALYZER_HOME", str(tmp_path / "override-home"))
    monkeypatch.setenv("AGENT_CODE_ANALYZER_QDRANT_URL", "http://env-qdrant:6333")
    monkeypatch.setenv("AGENT_CODE_ANALYZER_QDRANT_COLLECTION", "env_collection")
    monkeypatch.setenv("AGENT_CODE_ANALYZER_EMBEDDING_MODEL", "env/model")
    analyzer_config.get_config.cache_clear()

    config = analyzer_config.get_config()

    assert config.storage.home_dir == (tmp_path / "override-home")
    assert config.storage.sqlite_connect_timeout_seconds == 7.5
    assert config.storage.sqlite_busy_timeout_ms == 9000
    assert config.vector.qdrant_url == "http://env-qdrant:6333"
    assert config.vector.qdrant_collection == "env_collection"
    assert config.vector.embedding_model == "env/model"
    assert config.chunking.max_chunk_lines == 21
    assert config.chunking.min_split_lines == 13
    assert config.rate_limit.capacity == 2
    assert config.rate_limit.refill_per_second == 1.5
    assert config.rate_limit.concurrency_limit == 1
    assert config.semantic.backend == "hermes-lib"
    assert config.semantic.hermes_repo_root == analyzer_config.Path("/tmp/hermes")
    assert config.semantic.model == "model-a"
    assert config.semantic.provider == "provider-a"
    assert config.semantic.base_url == "https://example.invalid"
    assert config.semantic.api_key == "secret-a"
    assert config.logging.level == "DEBUG"
    assert config.logging.log_dir == Path("/tmp/custom-logs")
    assert config.logging.log_file == "analyzer.log"
    assert config.logging.log_to_stderr is False
    analyzer_config.get_config.cache_clear()


def test_build_semantic_writer_defaults_to_fake_backend() -> None:
    config = analyzer_config.AnalyzerConfig(
        storage=analyzer_config.StorageConfig(home_dir=analyzer_config.Path("/tmp/home")),
        vector=analyzer_config.VectorConfig(
            qdrant_url="http://qdrant",
            qdrant_collection="collection",
            embedding_model="model",
        ),
        chunking=analyzer_config.ChunkingConfig(),
        rate_limit=analyzer_config.RateLimitConfig(),
        semantic=analyzer_config.SemanticConfig(backend="fake"),
        logging=analyzer_config.LoggingConfig(log_dir=analyzer_config.Path("/tmp/home/logs")),
    )
    writer = build_semantic_writer(config)
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
    )
    result = writer.write(SemanticWriteRequest(record=record, source_text="print('hi')\n"))

    assert result.backend == "fake"
    assert result.description_text == "No detail here"


def test_build_semantic_writer_can_use_hermes_lib_backend(tmp_path) -> None:
    hermes_root = tmp_path / "hermes"
    hermes_root.mkdir()
    sys.modules.pop("run_agent", None)
    (hermes_root / "run_agent.py").write_text(
        """
class AIAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    def chat(self, prompt):
        return f"lib:{prompt.splitlines()[0]}"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = analyzer_config.AnalyzerConfig(
        storage=analyzer_config.StorageConfig(home_dir=analyzer_config.Path("/tmp/home")),
        vector=analyzer_config.VectorConfig(
            qdrant_url="http://qdrant",
            qdrant_collection="collection",
            embedding_model="model",
        ),
        chunking=analyzer_config.ChunkingConfig(),
        rate_limit=analyzer_config.RateLimitConfig(),
        semantic=analyzer_config.SemanticConfig(backend="hermes-lib", hermes_repo_root=hermes_root),
        logging=analyzer_config.LoggingConfig(log_dir=analyzer_config.Path("/tmp/home/logs")),
    )
    writer = build_semantic_writer(config)
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="",
        source_fingerprint="abc123",
    )
    result = writer.write(SemanticWriteRequest(record=record, source_text="print('hi')\n"))

    assert result.backend == "hermes-lib"
    assert result.description_text == "lib:Write a concise semantic description for file scope."
