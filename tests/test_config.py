from __future__ import annotations

from agent_code_analyzer import config as analyzer_config


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


def test_repo_config_toml_is_present_and_parseable() -> None:
    repo_root = analyzer_config.Path(__file__).resolve().parents[1]
    config_file = repo_root / "config.toml"
    assert config_file.exists()
    analyzer_config.get_config.cache_clear()
    config = analyzer_config.get_config()
    assert config.vector.qdrant_url.startswith("http://")
    assert config.rate_limit.capacity == 2
    assert config.rate_limit.refill_per_second == 0.1
    assert config.rate_limit.concurrency_limit == 2
