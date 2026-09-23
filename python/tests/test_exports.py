from __future__ import annotations

import pytest

import ledgermind_protocol as protocol


def test_public_exports_are_boundary_models() -> None:
    expected = {
        "ContextView",
        "RawRoundContextExtension",
        "GenericExecutionTask",
        "RetrievalRequest",
        "RetrievalResponse",
        "RawRoundRequest",
        "ClaimCondition",
        "ClaimCoverage",
        "ClaimExtractionOutput",
        "ClaimSubject",
        "ExtractedClaim",
        "OperationalClaimOutput",
    }
    assert expected <= set(protocol.__all__)
    assert protocol.ContextView.model_fields["schema_version"].default == 2
    assert set(protocol.ContextViewItem.model_fields) == {
        "value_id",
        "primary_object_id",
        "object_name",
        "target_id",
        "target_name",
        "target_breadcrumb",
        "facet",
        "content",
        "scope_text",
        "content_language",
        "conditions",
        "source_event_ids",
        "relevance",
        "explanation",
    }


@pytest.mark.parametrize(
    "legacy_name",
    ["RetrieveContextRequest", "ContextViewItem.knowledge_id", "ConsolidationResult"],
)
def test_legacy_public_contracts_are_not_exported(legacy_name: str) -> None:
    if "." in legacy_name:
        model_name, field_name = legacy_name.split(".", 1)
        assert not hasattr(getattr(protocol, model_name, None), field_name)
    else:
        assert not hasattr(protocol, legacy_name)
