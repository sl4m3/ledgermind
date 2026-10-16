import pytest
from ledgermind_protocol.object_facet import MemoryInjection, RetrievalResponse, ValueSemanticSafety


def test_semantic_injection_requires_version_and_old_dump_is_unchanged():
    old = {"format":"facet_legend", "text":"", "legend":[], "item_count":0}
    assert MemoryInjection.model_validate(old).model_dump() == old
    candidate = {**old, "format":"semantic_units_v2", "semantic_contract_version":"memory_semantics_v2"}
    assert MemoryInjection.model_validate(candidate).model_dump() == candidate
    with pytest.raises(ValueError, match="versioned contract"):
        MemoryInjection.model_validate({**old,"format":"semantic_units_v2"})


def test_semantic_safety_is_explicit_and_unknown_evidence_never_becomes_active():
    safety = ValueSemanticSafety.model_validate({"lifecycle_status":"contested","dependencies":[]})
    assert safety.requires_revalidation()
    with pytest.raises(ValueError):
        ValueSemanticSafety.model_validate({"lifecycle_status":"verified_because_tool","dependencies":[]})
    assert RetrievalResponse.model_validate({"schema_version":4,"retrieval_request_id":"new", "items":[],
        "memory_injection":{"format":"semantic_units_v2","semantic_contract_version":"memory_semantics_v2","text":"","legend":[],"item_count":0}}).schema_version == 4
    with pytest.raises(ValueError,match="versioned memory injection"):
        RetrievalResponse.model_validate({"schema_version":4,"retrieval_request_id":"new", "items":[]})


def test_scoped_delivery_has_an_explicit_new_version_and_cannot_downgrade():
    scope = {"contract_version":"registered_dependency_scopes_v1", "scope_kind":"global",
             "scope_id":"*", "checked_revision":2, "current_revision":3,
             "coverage":"registered_rules_only", "state":"snapshot_changed"}
    safety = ValueSemanticSafety.model_validate({"lifecycle_status":"active", "dependencies":[],
                                                "scope_checks":[scope]})
    assert safety.requires_revalidation()
    response = {"schema_version":5,"retrieval_request_id":"new", "items":[],
        "memory_injection":{"format":"semantic_units_v3","semantic_contract_version":"memory_semantics_v2",
                            "text":"","legend":[],"item_count":0}}
    assert RetrievalResponse.model_validate(response).schema_version == 5
    with pytest.raises(ValueError):
        RetrievalResponse.model_validate({**response,"schema_version":4})
