"""Shared Core isolation and environment policy.

This module is the single policy-to-requirements translation used by Local
boundary diagnostics and, later, by the process bootstrap.  It deliberately
does not know about the legacy ``require_core_network_isolation`` switch.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from ledgermind_local.config import CoreSecurityConfig

from .isolation import IsolationRequirements

CORE_ALLOWED_STATIC_ENVIRONMENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "LANG",
        "LC_ALL",
        "RUST_BACKTRACE",
        "LEDGERMIND_CORE_DATA_DIR",
        "LEDGERMIND_SEMANTIC_LANGUAGE",
        "PWD",
    }
)
"""Environment names that are part of the stable Core launch contract."""


CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        # Locale/TZ values are harmless runtime context and may be injected by
        # the launcher without becoming Core configuration or credentials.
        "LANGUAGE",
        "LC_CTYPE",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_COLLATE",
        "LC_MONETARY",
        "LC_MESSAGES",
        "LC_PAPER",
        "LC_NAME",
        "LC_ADDRESS",
        "LC_TELEPHONE",
        "LC_MEASUREMENT",
        "LC_IDENTIFICATION",
        "TZ",
    }
)
"""Safe locale/time-zone names that may be added at launch time."""


CORE_ALLOWED_ENVIRONMENT_KEYS: Final[frozenset[str]] = (
    CORE_ALLOWED_STATIC_ENVIRONMENT_KEYS
    | CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS
)

_SECRET_ENVIRONMENT_MARKERS: Final[tuple[str, ...]] = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "PASSWORD",
    "PROXY",
    "SECRET",
    "TOKEN",
)


def build_core_isolation_requirements(
    core_security: CoreSecurityConfig,
    *,
    verify_core_signature: bool,
) -> IsolationRequirements:
    """Translate the explicit Core security config into launch requirements.

    ``core_security`` is the only policy input.  The old Local-level network
    switch is intentionally not accepted here, so callers cannot accidentally
    make Doctor and the runtime disagree.  Signature verification is a
    separate launch control: either an explicit security requirement or the
    verification switch makes the signature guarantee required.
    """

    return IsolationRequirements(
        require_network_isolation=core_security.require_network_isolation,
        require_rounds_database_hidden=core_security.require_rounds_database_hidden,
        require_filesystem_allowlist=core_security.require_filesystem_allowlist,
        require_environment_sanitized=core_security.require_environment_sanitized,
        require_signature=core_security.require_signature or verify_core_signature,
    )


def is_secret_like_environment_name(name: str) -> bool:
    """Return whether an environment name resembles a credential-bearing key."""

    normalized = name.upper()
    return any(marker in normalized for marker in _SECRET_ENVIRONMENT_MARKERS)


def is_allowed_core_environment_name(name: str) -> bool:
    """Return whether an environment name is part of the Core policy."""

    return name in CORE_ALLOWED_ENVIRONMENT_KEYS


def classify_core_environment(environment_keys: Iterable[str]) -> tuple[int, int]:
    """Return ``(secret_like_count, unexpected_count)`` without exposing names."""

    secret_like_count = 0
    unexpected_count = 0
    for key in environment_keys:
        if is_secret_like_environment_name(key):
            secret_like_count += 1
        if not is_allowed_core_environment_name(key):
            unexpected_count += 1
    return secret_like_count, unexpected_count


__all__ = [
    "CORE_ALLOWED_ENVIRONMENT_KEYS",
    "CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS",
    "CORE_ALLOWED_STATIC_ENVIRONMENT_KEYS",
    "build_core_isolation_requirements",
    "classify_core_environment",
    "is_allowed_core_environment_name",
    "is_secret_like_environment_name",
]
