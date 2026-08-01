"""Shared building blocks for contract models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base class for API contracts with strict field policy."""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_dict(cls) -> dict[str, Any]:
        return cls.model_json_schema()


SHA256_CHECKSUM_PATTERN = r"^sha256:[0-9a-f]{64}$"

__all__ = ["ContractModel", "SHA256_CHECKSUM_PATTERN"]
