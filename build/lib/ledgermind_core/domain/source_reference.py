"""Immutable reference to an external source round."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SHA256_PREFIX = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_system: str
    source_instance_id: str
    source_profile_id: str
    source_session_id: str
    source_round_id: str
    first_message_id: str | None
    final_message_id: str | None
    message_ids: tuple[str, ...]
    source_digest: str
    source_schema_version: int
    resolver_version: int

    def __post_init__(self) -> None:
        required = {
            "source_system": self.source_system,
            "source_instance_id": self.source_instance_id,
            "source_profile_id": self.source_profile_id,
            "source_session_id": self.source_session_id,
            "source_round_id": self.source_round_id,
            "source_digest": self.source_digest,
        }
        for name, value in required.items():
            if not value or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        if self.source_schema_version < 1:
            raise ValueError("source_schema_version must be >= 1")
        if self.resolver_version < 1:
            raise ValueError("resolver_version must be >= 1")

        if not _SHA256_PREFIX.fullmatch(self.source_digest):
            raise ValueError("source_digest must match sha256:<64 hex>")

    @property
    def source_round_key_data(self) -> tuple[str, str, str, str, str]:
        return (
            self.source_system,
            self.source_instance_id,
            self.source_profile_id,
            self.source_session_id,
            self.source_round_id,
        )
