"""Public object-facet ContextView returned by Local."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import ProtocolModel
from .object_facet import (
    MAX_CONTEXT_IDS,
    MAX_SOURCE_EVENT_IDS,
    MemoryInjection,
    RetrievalItem,
    _validate_ids,
)


class ContextViewItem(RetrievalItem):
    """Public Local item, whose Core-owned event provenance is not exposed.

    ``RetrievalResponse`` remains strict and requires source event ids.  Local's
    public ContextView deliberately strips those internal ids before handing
    context to integrations, so this boundary accepts an omitted/empty list.
    """

    source_event_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_SOURCE_EVENT_IDS,
    )

    @model_validator(mode="after")
    def validate_item(self) -> ContextViewItem:
        if self.source_event_ids:
            _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        if self.explanation.item_facet != self.facet:
            raise ValueError("explanation item_facet must match the item facet")
        return self


class ContextView(ProtocolModel):
    schema_version: Literal[2, 3] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=500)
    items: list[ContextViewItem] = Field(max_length=100)
    # Compatibility name: service-selected IDs, not proof of host visibility.
    delivered_value_ids: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_IDS)
    memory_injection: MemoryInjection | None = None
    selection_diagnostics: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_delivery_refs(self) -> ContextView:
        if len(set(self.delivered_value_ids)) != len(self.delivered_value_ids):
            raise ValueError("delivered_value_ids must be unique")
        value_ids = {item.value_id for item in self.items}
        if not set(self.delivered_value_ids).issubset(value_ids):
            raise ValueError("delivered_value_ids must refer to returned items")
        if self.memory_injection is not None and self.memory_injection.item_count != len(
            self.items
        ):
            raise ValueError("memory_injection.item_count must match items")
        return self


__all__ = ["ContextView", "ContextViewItem"]
