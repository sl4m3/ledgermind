"""Independent, measurable guarantees for the supervised Core boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IsolationCapabilities:
    """Capabilities actually established for one Core child process."""

    network_isolated: bool = False
    rounds_database_hidden: bool = False
    filesystem_allowlisted: bool = False
    environment_sanitized: bool = False
    file_descriptors_closed: bool = False
    child_process_creation_blocked: bool = False
    binary_signature_verified: bool = False
    sandbox_backend: str = "none"
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        """Return a stable, JSON-safe representation of the guarantees."""

        return {
            "network_isolated": self.network_isolated,
            "rounds_database_hidden": self.rounds_database_hidden,
            "filesystem_allowlisted": self.filesystem_allowlisted,
            "environment_sanitized": self.environment_sanitized,
            "file_descriptors_closed": self.file_descriptors_closed,
            "child_process_creation_blocked": self.child_process_creation_blocked,
            "binary_signature_verified": self.binary_signature_verified,
            "sandbox_backend": self.sandbox_backend,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class IsolationRequirements:
    """Guarantees that a Core launch profile requires."""

    require_network_isolation: bool = False
    require_rounds_database_hidden: bool = False
    require_filesystem_allowlist: bool = False
    require_environment_sanitized: bool = False
    require_signature: bool = False

    def missing(self, capabilities: IsolationCapabilities) -> tuple[str, ...]:
        """Return capability names required by this profile but not established."""

        checks = (
            ("network_isolated", self.require_network_isolation, capabilities.network_isolated),
            (
                "rounds_database_hidden",
                self.require_rounds_database_hidden,
                capabilities.rounds_database_hidden,
            ),
            (
                "filesystem_allowlisted",
                self.require_filesystem_allowlist,
                capabilities.filesystem_allowlisted,
            ),
            (
                "environment_sanitized",
                self.require_environment_sanitized,
                capabilities.environment_sanitized,
            ),
            (
                "binary_signature_verified",
                self.require_signature,
                capabilities.binary_signature_verified,
            ),
        )
        return tuple(name for name, required, present in checks if required and not present)

    def as_dict(self) -> dict[str, bool]:
        """Return the required guarantees without exposing configuration details."""

        return {
            "network_isolated": self.require_network_isolation,
            "rounds_database_hidden": self.require_rounds_database_hidden,
            "filesystem_allowlisted": self.require_filesystem_allowlist,
            "environment_sanitized": self.require_environment_sanitized,
            "binary_signature_verified": self.require_signature,
        }


@dataclass(frozen=True, slots=True)
class IsolationPlan:
    """Command plus the guarantees measured for its launch environment."""

    command: tuple[str, ...]
    capabilities: IsolationCapabilities

    @property
    def level(self) -> str:
        """Compatibility view for callers that still consume sandbox levels."""

        if self.capabilities.sandbox_backend == "unavailable":
            return "unavailable"
        if all(
            (
                self.capabilities.network_isolated,
                self.capabilities.rounds_database_hidden,
                self.capabilities.filesystem_allowlisted,
                self.capabilities.environment_sanitized,
                self.capabilities.file_descriptors_closed,
            )
        ):
            return "full"
        return "partial"

    @property
    def detail(self) -> str:
        """Compatibility view for callers that still consume sandbox details."""

        return self.capabilities.detail


__all__ = [
    "IsolationCapabilities",
    "IsolationPlan",
    "IsolationRequirements",
]
