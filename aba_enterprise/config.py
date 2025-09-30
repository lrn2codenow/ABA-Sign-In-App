"""Configuration utilities for the enterprise-ready ABA Sign-In app."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the application.

    Attributes
    ----------
    runtime_dir:
        Location where runtime artefacts (snapshots, settings) are stored.
    environment:
        Current execution environment. One of ``development``, ``staging`` or
        ``production``.
    timezone:
        IANA timezone identifier used when formatting timestamps.
    data_retention_days:
        Number of days runtime sign-in snapshots are retained before rotation.
    webhook_timeout:
        Timeout, in seconds, used for outbound webhook invocations.
    audit_log_enabled:
        Indicates whether audit logging should be persisted to disk.
    """

    runtime_dir: Path
    environment: str = "development"
    timezone: str = "UTC"
    data_retention_days: int = 30
    webhook_timeout: float = 10.0
    audit_log_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


def _coerce_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _coerce_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _coerce_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def load_app_config(base_dir: Optional[str] = None) -> AppConfig:
    """Load application configuration from environment variables.

    Parameters
    ----------
    base_dir:
        Optional override for the project base directory. Defaults to the
        parent directory of this file when not provided.
    """

    base_path = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    runtime_root = Path(os.environ.get("ABA_RUNTIME_DIR", base_path / "runtime"))
    runtime_root.mkdir(parents=True, exist_ok=True)

    environment = os.environ.get("ABA_ENVIRONMENT", "development")
    timezone = os.environ.get("ABA_TIMEZONE", "UTC")
    retention = _coerce_int(os.environ.get("ABA_DATA_RETENTION_DAYS"), 30)
    webhook_timeout = _coerce_float(os.environ.get("ABA_WEBHOOK_TIMEOUT"), 10.0)
    audit_logging = _coerce_bool(os.environ.get("ABA_AUDIT_LOG_ENABLED"), True)

    return AppConfig(
        runtime_dir=runtime_root,
        environment=environment,
        timezone=timezone,
        data_retention_days=retention,
        webhook_timeout=webhook_timeout,
        audit_log_enabled=audit_logging,
    )
