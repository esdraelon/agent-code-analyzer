from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import AnalyzerConfig, LoggingConfig, get_config


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _remove_managed_handlers(root: logging.Logger, *, kind: str) -> None:
    for handler in list(root.handlers):
        if getattr(handler, "_agent_code_analyzer_logging_kind", None) == kind:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass


def _build_stream_handler(config: LoggingConfig) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setLevel(_resolve_level(config.level))
    handler.setFormatter(logging.Formatter(config.format, datefmt=config.datefmt))
    setattr(handler, "_agent_code_analyzer_logging_kind", "stream")
    return handler


def _build_file_handler(config: LoggingConfig) -> logging.Handler | None:
    if config.log_dir is None:
        return None
    log_dir = Path(config.log_dir).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / config.log_file, encoding="utf-8")
    handler.setLevel(_resolve_level(config.level))
    handler.setFormatter(logging.Formatter(config.format, datefmt=config.datefmt))
    setattr(handler, "_agent_code_analyzer_logging_kind", "file")
    return handler


def _resolve_level(level_name: str) -> int:
    candidate = getattr(logging, str(level_name).strip().upper(), None)
    if isinstance(candidate, int):
        return candidate
    return logging.INFO


def setup_logging(config: AnalyzerConfig | None = None) -> logging.Logger:
    """Configure the analyzer's logging pipeline.

    The setup is idempotent for the handlers we manage, so it can be called from
    the CLI entrypoint and test fixtures without duplicating output.
    """

    resolved = config or get_config()
    logging_config = resolved.logging
    root = logging.getLogger()
    root.setLevel(_resolve_level(logging_config.level))

    _remove_managed_handlers(root, kind="stream")
    _remove_managed_handlers(root, kind="file")

    if _coerce_bool(logging_config.log_to_stderr, True):
        root.addHandler(_build_stream_handler(logging_config))

    try:
        file_handler = _build_file_handler(logging_config)
    except OSError as exc:  # pragma: no cover - depends on filesystem permissions
        root.warning("logging_file_handler_unavailable log_dir=%r error=%s", logging_config.log_dir, exc)
    else:
        if file_handler is not None:
            root.addHandler(file_handler)

    root.info(
        "logging_configured level=%s log_dir=%r log_file=%r log_to_stderr=%s",
        logging_config.level,
        logging_config.log_dir,
        logging_config.log_file,
        _coerce_bool(logging_config.log_to_stderr, True),
    )
    return root


__all__ = ["LoggingConfig", "setup_logging"]
