"""Structured logging helpers used by the modernised application."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import AppConfig


class JsonLogFormatter(logging.Formatter):
    """Format log records as JSON payloads for downstream ingestion."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - inherited docstring
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for attr in ("user", "request_id", "component"):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(config: AppConfig, *, log_level: Optional[str] = None) -> None:
    """Initialise application logging.

    The configuration aims to mimic production logging practices by
    emitting JSON lines suitable for aggregation tools (ELK, Datadog,
    Splunk, etc.) while remaining backwards compatible with the
    proof-of-concept development workflow.
    """

    if logging.getLogger().handlers:
        # Avoid double-configuration when running inside unit tests that
        # may reload the module.
        return

    level_name = log_level or os.environ.get("ABA_LOG_LEVEL", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)
    handler: logging.Handler

    if config.audit_log_enabled:
        audit_path = config.runtime_dir / "audit.log"
        handler = logging.FileHandler(audit_path, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Suppress overly verbose third-party loggers should the application be
    # embedded in a richer stack later on.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
