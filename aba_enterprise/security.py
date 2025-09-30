"""Simple security primitives for future authentication integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set


@dataclass(frozen=True)
class Identity:
    """Represents an authenticated identity within the system."""

    subject: str
    roles: Set[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


class PermissionDenied(Exception):
    """Raised when an identity lacks the required privileges."""


class AccessPolicy:
    """Evaluate simple role-based access control (RBAC) decisions."""

    def __init__(self, default_roles: Iterable[str] | None = None) -> None:
        self._default_roles: Set[str] = set(default_roles or {"anonymous"})

    def ensure(self, identity: Identity | None, *, require: Iterable[str]) -> None:
        roles = self._default_roles if identity is None else identity.roles
        required = set(require)
        if required and not (set(roles) & required):
            raise PermissionDenied(
                f"Identity {identity.subject if identity else 'anonymous'} lacks required roles: {sorted(required)}"
            )
