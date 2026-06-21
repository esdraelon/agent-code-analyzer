from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
import tomllib
from typing import Any


@dataclass(frozen=True, slots=True)
class StorageConfig:
    home_dir: Path
    sqlite_connect_timeout_seconds: float = 5.0
    sqlite_busy_timeout_ms: int = 5000


@dataclass(frozen=True, slots=True)
class VectorConfig:
    qdrant_url: str
    qdrant_collection: str
    embedding_model: str


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    max_chunk_lines: int = 12
    min_split_lines: int = 8


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    capacity: int = 8
    refill_per_second: float = 8.0
    concurrency_limit: int = 4


@dataclass(frozen=True, slots=True)
class SemanticConfig:
    backend: str = "fake"
    hermes_repo_root: Path | None = None
    hermes_executable: str = "hermes"
    model: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"
    log_dir: Path | None = None
    log_file: str = "agent-code-analyzer.log"
    format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    datefmt: str = "%Y-%m-%dT%H:%M:%S%z"
    log_to_stderr: bool = True


@dataclass(frozen=True, slots=True)
class AnalyzerConfig:
    storage: StorageConfig
    vector: VectorConfig
    chunking: ChunkingConfig
    rate_limit: RateLimitConfig
    semantic: SemanticConfig
    logging: LoggingConfig


_DEFAULT_STORAGE_HOME = Path.home() / ".agent-code-analyzer"
_DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
_DEFAULT_QDRANT_COLLECTION = "agent_code_analyzer_chunks_v2"
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_CONFIG_FILENAMES = ("config.toml",)


def _coerce_path(value: Any, default: Path) -> Path:
    if value is None:
        return default
    if isinstance(value, Path):
        return value.expanduser()
    return Path(str(value)).expanduser()


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _candidate_config_paths() -> list[Path]:
    env_path = os.environ.get("AGENT_CODE_ANALYZER_CONFIG")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(Path.cwd() / "config.toml")
    candidates.append(_DEFAULT_STORAGE_HOME / "config.toml")
    return candidates


@lru_cache(maxsize=1)
def get_config() -> AnalyzerConfig:
    raw: dict[str, Any] = {}
    for candidate in _candidate_config_paths():
        if candidate.exists():
            raw = _load_toml_file(candidate)
            break

    storage_raw = raw.get("storage", {}) if isinstance(raw.get("storage", {}), dict) else {}
    vector_raw = raw.get("vector", {}) if isinstance(raw.get("vector", {}), dict) else {}
    chunking_raw = raw.get("chunking", {}) if isinstance(raw.get("chunking", {}), dict) else {}
    rate_limit_raw = raw.get("rate_limit", {}) if isinstance(raw.get("rate_limit", {}), dict) else {}
    semantic_raw = raw.get("semantic", {}) if isinstance(raw.get("semantic", {}), dict) else {}
    logging_raw = raw.get("logging", {}) if isinstance(raw.get("logging", {}), dict) else {}

    storage_home = _coerce_path(storage_raw.get("home_dir"), _DEFAULT_STORAGE_HOME)
    storage_home = _coerce_path(os.environ.get("AGENT_CODE_ANALYZER_HOME"), storage_home)
    sqlite_connect_timeout_seconds = _coerce_float(storage_raw.get("sqlite_connect_timeout_seconds"), 5.0)
    sqlite_busy_timeout_ms = _coerce_int(storage_raw.get("sqlite_busy_timeout_ms"), 5000)

    qdrant_url = str(vector_raw.get("qdrant_url", _DEFAULT_QDRANT_URL))
    qdrant_url = str(os.environ.get("AGENT_CODE_ANALYZER_QDRANT_URL", qdrant_url))
    qdrant_collection = str(vector_raw.get("qdrant_collection", _DEFAULT_QDRANT_COLLECTION))
    qdrant_collection = str(os.environ.get("AGENT_CODE_ANALYZER_QDRANT_COLLECTION", qdrant_collection))
    embedding_model = str(vector_raw.get("embedding_model", _DEFAULT_EMBEDDING_MODEL))
    embedding_model = str(os.environ.get("AGENT_CODE_ANALYZER_EMBEDDING_MODEL", embedding_model))

    chunking = ChunkingConfig(
        max_chunk_lines=_coerce_int(chunking_raw.get("max_chunk_lines"), 12),
        min_split_lines=_coerce_int(chunking_raw.get("min_split_lines"), 8),
    )
    rate_limit = RateLimitConfig(
        capacity=_coerce_int(rate_limit_raw.get("capacity"), 8),
        refill_per_second=_coerce_float(rate_limit_raw.get("refill_per_second"), 8.0),
        concurrency_limit=_coerce_int(rate_limit_raw.get("concurrency_limit"), 4),
    )
    semantic = SemanticConfig(
        backend=str(os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_BACKEND", semantic_raw.get("backend", "fake"))),
        hermes_repo_root=_coerce_path(
            os.environ.get("AGENT_CODE_ANALYZER_HERMES_REPO_ROOT", semantic_raw.get("hermes_repo_root")),
            Path.home() / ".hermes" / "hermes-agent",
        ),
        hermes_executable=str(
            os.environ.get("AGENT_CODE_ANALYZER_HERMES_EXECUTABLE", semantic_raw.get("hermes_executable", "hermes"))
        ),
        model=(
            None
            if semantic_raw.get("model") is None and os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_MODEL") is None
            else str(os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_MODEL", semantic_raw.get("model")))
        ),
        provider=(
            None
            if semantic_raw.get("provider") is None and os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_PROVIDER") is None
            else str(os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_PROVIDER", semantic_raw.get("provider")))
        ),
        base_url=(
            None
            if semantic_raw.get("base_url") is None and os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_BASE_URL") is None
            else str(os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_BASE_URL", semantic_raw.get("base_url")))
        ),
        api_key=(
            None
            if semantic_raw.get("api_key") is None and os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_API_KEY") is None
            else str(os.environ.get("AGENT_CODE_ANALYZER_SEMANTIC_API_KEY", semantic_raw.get("api_key")))
        ),
    )
    logging = LoggingConfig(
        level=str(os.environ.get("AGENT_CODE_ANALYZER_LOG_LEVEL", logging_raw.get("level", "INFO"))),
        log_dir=_coerce_path(
            os.environ.get("AGENT_CODE_ANALYZER_LOG_DIR", logging_raw.get("log_dir")),
            storage_home / "logs",
        ),
        log_file=str(os.environ.get("AGENT_CODE_ANALYZER_LOG_FILE", logging_raw.get("log_file", "agent-code-analyzer.log"))),
        format=str(os.environ.get("AGENT_CODE_ANALYZER_LOG_FORMAT", logging_raw.get("format", "%(asctime)s %(levelname)s %(name)s %(message)s"))),
        datefmt=str(os.environ.get("AGENT_CODE_ANALYZER_LOG_DATEFMT", logging_raw.get("datefmt", "%Y-%m-%dT%H:%M:%S%z"))),
        log_to_stderr=bool(
            str(os.environ.get("AGENT_CODE_ANALYZER_LOG_TO_STDERR", logging_raw.get("log_to_stderr", True))).strip().lower()
            not in {"0", "false", "no", "off"}
        ),
    )
    return AnalyzerConfig(
        storage=StorageConfig(
            home_dir=storage_home,
            sqlite_connect_timeout_seconds=sqlite_connect_timeout_seconds,
            sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        ),
        vector=VectorConfig(
            qdrant_url=qdrant_url,
            qdrant_collection=qdrant_collection,
            embedding_model=embedding_model,
        ),
        chunking=chunking,
        rate_limit=rate_limit,
        semantic=semantic,
        logging=logging,
    )


__all__ = [
    "AnalyzerConfig",
    "ChunkingConfig",
    "LoggingConfig",
    "RateLimitConfig",
    "SemanticConfig",
    "StorageConfig",
    "VectorConfig",
    "get_config",
]
