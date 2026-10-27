"""Public, language-neutral LedgerMind protocol models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256_CHECKSUM_PATTERN = r"^sha256:[0-9a-f]{64}$"


class ProtocolModel(BaseModel):
    """Strict public protocol model: unknown fields are never accepted."""

    model_config = ConfigDict(extra="forbid")


class RawContentPart(ProtocolModel):
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


class RawRoundEvent(ProtocolModel):
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

    @model_validator(mode="after")
    def validate_kind_shape(self) -> RawRoundEvent:
        supplied = self.model_fields_set
        if self.kind == "message":
            if self.role is None:
                raise ValueError("message event requires role")
            forbidden = {"tool_call_id", "tool_name", "arguments", "status"} & supplied
            if forbidden:
                raise ValueError(
                    "message event forbids tool_call_id, tool_name, arguments and status"
                )
        elif self.kind == "tool_call":
            if not self.tool_call_id or not self.tool_name:
                raise ValueError("tool_call event requires tool_call_id and tool_name")
            if "role" in supplied or "status" in supplied:
                raise ValueError("tool_call event forbids role and status")
        else:
            if not self.tool_call_id:
                raise ValueError("tool_result event requires tool_call_id")
            if self.status is None:
                raise ValueError("tool_result event requires status")
            if "role" in supplied:
                raise ValueError("tool_result event forbids role")
        return self


class LedgerMindResolution(ProtocolModel):
    """Versioned, source-owned work identity for object resolution."""

    schema_version: Literal[1]
    project_id: str | None = Field(min_length=1, max_length=500)
    repository_id: str | None = Field(min_length=1, max_length=500)
    task_id: str | None = Field(min_length=1, max_length=500)
    conversation_id: str | None = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_identifiers(self) -> LedgerMindResolution:
        for value, name in (
            (self.project_id, "project_id"),
            (self.repository_id, "repository_id"),
            (self.task_id, "task_id"),
            (self.conversation_id, "conversation_id"),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be empty")
        return self


class RawRoundSource(ProtocolModel):
    system: str = Field(min_length=1, max_length=100)
    instance_id: str = Field(min_length=1, max_length=300)
    profile_id: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=1, max_length=500)
    round_id: str = Field(min_length=1, max_length=500)
    first_event_id: str = Field(min_length=1, max_length=300)
    final_event_id: str = Field(min_length=1, max_length=300)
    event_ids: list[str] = Field(min_length=1, max_length=10_000)
    source_schema_version: int = Field(ge=1)
    adapter_version: str = Field(min_length=1, max_length=200)
    extensions: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_event_ids(self) -> RawRoundSource:
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("source.event_ids must be unique")
        if self.extensions is not None and "ledgermind_resolution" in self.extensions:
            LedgerMindResolution.model_validate(self.extensions["ledgermind_resolution"])
        return self


class RawRoundBody(ProtocolModel):
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
        if sequences != list(range(len(sequences))):
            raise ValueError("round event sequences must be contiguous and ordered")
        if self.completed_at < self.started_at:
            raise ValueError("round.completed_at must not precede started_at")
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("round timestamps must include a timezone")
        return self


class RawRoundRequest(ProtocolModel):
    """Complete immutable structural RawRound capture."""

    schema_version: Literal[2] = 2
    idempotency_key: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    memory_space_id: str = Field(min_length=1, max_length=200)
    source: RawRoundSource
    round: RawRoundBody
    payload_digest: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    extensions: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_complete_round(self) -> RawRoundRequest:
        if self.extensions is not None and "ledgermind_resolution" in self.extensions:
            raise ValueError("ledgermind_resolution belongs in source.extensions")
        events = self.round.events
        event_ids = [event.event_id for event in events]
        if self.source.event_ids != event_ids:
            raise ValueError("source.event_ids must match round event order")
        if self.source.first_event_id != event_ids[0]:
            raise ValueError("source.first_event_id must match the first event")
        if self.source.final_event_id != event_ids[-1]:
            raise ValueError("source.final_event_id must match the final event")

        user_messages = [
            event for event in events if event.kind == "message" and event.role == "user"
        ]
        if not user_messages:
            raise ValueError("round must contain at least one user message")
        final_assistants = [
            event
            for event in events
            if event.kind == "message" and event.role == "assistant" and event.final
        ]
        if len(final_assistants) != 1:
            raise ValueError("round must contain exactly one final assistant message")

        call_ids = [event.tool_call_id for event in events if event.kind == "tool_call"]
        if len(set(call_ids)) != len(call_ids):
            raise ValueError("tool_call_id must be unique across tool calls")
        known_calls = {call_id for call_id in call_ids if call_id is not None}
        for event in events:
            if event.kind == "tool_result" and event.tool_call_id not in known_calls:
                raise ValueError("every tool_result must reference an existing tool_call")

        if self.idempotency_key != self.payload_digest:
            raise ValueError("idempotency_key must equal payload_digest for RawRound")
        from .canonical import calculate_payload_digest

        if calculate_payload_digest(self) != self.payload_digest:
            raise ValueError("payload_digest does not match canonical source and round")
        return self


__all__ = [
    "SHA256_CHECKSUM_PATTERN",
    "LedgerMindResolution",
    "ProtocolModel",
    "RawContentPart",
    "RawRoundBody",
    "RawRoundEvent",
    "RawRoundRequest",
    "RawRoundSource",
]
