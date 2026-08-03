"""Language-neutral RawRound v2 contract models.

The contract contains only data observable by a client adapter. Semantic fields
such as hypotheses, confidence and knowledge phases are intentionally absent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import SHA256_CHECKSUM_PATTERN, ContractModel


class RawContentPart(ContractModel):
    type: Literal["text", "json", "reference"]
    text: str | None = Field(default=None, max_length=200_000)
    data: object | None = None
    uri: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_payload(self) -> RawContentPart:
        if self.type == "text" and self.text is None:
            raise ValueError("text content part requires text")
        if self.type == "json" and self.data is None:
            raise ValueError("json content part requires data")
        if self.type == "reference" and self.uri is None:
            raise ValueError("reference content part requires uri")
        return self


class RawRoundEvent(ContractModel):
    event_id: str = Field(min_length=1, max_length=300)
    sequence: int = Field(ge=0, le=1_000_000)
    kind: Literal["message", "tool_call", "tool_result"]
    role: Literal["user", "assistant", "system"] | None = None
    content: list[RawContentPart] = Field(default_factory=list, max_length=256)
    final: bool = False
    tool_call_id: str | None = Field(default=None, max_length=300)
    tool_name: str | None = Field(default=None, max_length=300)
    arguments: object | None = None
    status: Literal["success", "error", "cancelled", "unknown"] | None = None


class RawRoundSource(ContractModel):
    system: str = Field(min_length=1, max_length=100)
    instance_id: str = Field(min_length=1, max_length=300)
    profile_id: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=1, max_length=500)
    round_id: str = Field(min_length=1, max_length=500)
    first_event_id: str | None = Field(default=None, min_length=1, max_length=300)
    final_event_id: str | None = Field(default=None, min_length=1, max_length=300)
    event_ids: list[str] = Field(min_length=1, max_length=10_000)
    source_schema_version: int = Field(ge=1)
    adapter_version: str = Field(min_length=1, max_length=200)
    extensions: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_event_ids(self) -> RawRoundSource:
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("source.event_ids must be unique")
        return self


class RawRoundBody(ContractModel):
    started_at: datetime
    completed_at: datetime
    events: list[RawRoundEvent] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_order(self) -> RawRoundBody:
        sequences = [event.sequence for event in self.events]
        event_ids = [event.event_id for event in self.events]
        if len(set(sequences)) != len(sequences):
            raise ValueError("round event sequences must be unique")
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("round event IDs must be unique")
        if self.completed_at < self.started_at:
            raise ValueError("round.completed_at must not precede started_at")
        return self


class RawRoundRequest(ContractModel):
    """Complete immutable raw-round capture request."""

    api_version: Literal["2"] = "2"
    idempotency_key: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    memory_space_id: str = Field(min_length=1, max_length=200)
    source: RawRoundSource
    round: RawRoundBody
    payload_digest: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    extensions: dict[str, object] | None = None


__all__ = [
    "RawContentPart",
    "RawRoundBody",
    "RawRoundEvent",
    "RawRoundRequest",
    "RawRoundSource",
]
