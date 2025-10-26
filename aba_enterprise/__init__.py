"""Enterprise support utilities for the ABA Sign-In application.

This package provides modular building blocks that decouple
configuration, persistence, security, and application services from the
legacy monolithic `app.py` implementation.  The goal is to provide a
progressive migration path towards the enterprise-grade architecture
outlined in ``ENTERPRISE_PLAN.md`` without breaking the existing
interface that powers the educational proof-of-concept.

Each module inside this package is intentionally framework-agnostic so
that the code can be reused whether the application is eventually hosted
inside a modern ASGI framework or remains on top of Python's standard
library HTTP server for the time being.
"""

from .config import AppConfig, load_app_config  # noqa: F401
from .logging import configure_logging  # noqa: F401
from .persistence import (
    AuditLogger,
    CSVDataLoader,
    PersonAssignmentStore,
    RuntimeSnapshotStore,
    SettingsStore,
)  # noqa: F401
from .security import AccessPolicy, Identity, PermissionDenied  # noqa: F401
from .services import (
    EmergencyNotificationService,
    ReportingService,
    SignInService,
)  # noqa: F401
