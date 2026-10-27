"""Single source of truth for the Local/Core wire compatibility window."""

from __future__ import annotations

from typing import Final

from ledgermind_protocol.core_ipc import (
    CORE_IPC_PROTOCOL_VERSION,
    CORE_KNOWLEDGE_SCHEMA_VERSION,
)

# Local currently supports one exact public contract.  Keeping the bounds in
# one module makes a future compatibility window an explicit, reviewable
# change instead of a collection of magic comparisons.
SUPPORTED_PROTOCOL_MIN: Final[int] = CORE_IPC_PROTOCOL_VERSION
SUPPORTED_PROTOCOL_MAX: Final[int] = CORE_IPC_PROTOCOL_VERSION
SUPPORTED_KNOWLEDGE_SCHEMA_MIN: Final[int] = CORE_KNOWLEDGE_SCHEMA_VERSION
SUPPORTED_KNOWLEDGE_SCHEMA_MAX: Final[int] = CORE_KNOWLEDGE_SCHEMA_VERSION


def protocol_supported(value: object) -> bool:
    """Return whether a handshake protocol version is supported."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and SUPPORTED_PROTOCOL_MIN <= value <= SUPPORTED_PROTOCOL_MAX
    )


def knowledge_schema_supported(value: object) -> bool:
    """Return whether a Core knowledge schema version is supported."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and SUPPORTED_KNOWLEDGE_SCHEMA_MIN <= value <= SUPPORTED_KNOWLEDGE_SCHEMA_MAX
    )


def compatibility_reason(
    protocol_version: object,
    knowledge_schema_version: object,
) -> str | None:
    """Return the stable readiness reason for an incompatible handshake."""

    if not protocol_supported(protocol_version):
        return "core_protocol_incompatible"
    if not knowledge_schema_supported(knowledge_schema_version):
        return "core_knowledge_schema_incompatible"
    return None


__all__ = [
    "SUPPORTED_KNOWLEDGE_SCHEMA_MAX",
    "SUPPORTED_KNOWLEDGE_SCHEMA_MIN",
    "SUPPORTED_PROTOCOL_MAX",
    "SUPPORTED_PROTOCOL_MIN",
    "compatibility_reason",
    "knowledge_schema_supported",
    "protocol_supported",
]
