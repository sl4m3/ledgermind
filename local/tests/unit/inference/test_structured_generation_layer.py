from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from ledgermind_local.inference.core_task_executor import (
    CoreTaskExecutor,
    GenericExecutionTask,
    ModelRequestSpec,
)
from ledgermind_local.inference.embedding_provider import EmbeddingProvider
from ledgermind_local.inference.profile_slots import (
    ProfileSlot,
    StoreBackedProfileResolver,
)
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import (
    InferenceProfile,
    ProviderCapabilities,
    generation_profile_fingerprint,
)
from ledgermind_local.inference.provider_probe import (
    PROBE_MAX_OUTPUT_TOKENS,
    ProviderProbe,
    _probe_request,
)
from ledgermind_local.inference.providers.base import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderTransportError,
)
from ledgermind_local.inference.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_payload_json_object,
    build_payload_json_schema,
    build_payload_prompt_only,
    build_payload_tool_call,
    decode_json_content,
)
from ledgermind_local.inference.secrets import SecretStore
from ledgermind_local.inference.strict import (
    STRICT_JSON_SCHEMA_MODE,
    canonical_digest,
    strict_requirement_for_contract,
    validate_strict_schema_profile,
)
from ledgermind_local.inference.structured_json_provider import (
    StructuredJsonCapabilityError,
    StructuredJsonProvider,
    StructuredJsonResponseError,
    StructuredJsonSchemaError,
    _advisory_schema_issues,
)
from ledgermind_local.inference.token_budget import InputBudgetExceededError
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.scheduler.core_execution_task_worker import (
    classify_execution_error,
)

CONTRACT = {
    "contract_name": "technical_result",
    "schema_version": 1,
    "json_schema": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    },
    "schema_digest": "sha256:" + "a" * 64,
}

STRICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}
STRICT_CONTRACT = {
    "contract_name": "strict_technical_result",
    "schema_version": 1,
    "json_schema": STRICT_SCHEMA,
    "schema_digest": canonical_digest(STRICT_SCHEMA),
}


class _FakeProvider:
    provider_kind = "openai_compatible"

    def __init__(self, *, failures: set[str] | None = None, content: str = '{"ok":true}') -> None:
        self.failures = failures or set()
        self.content = content
        self.requests: list[ModelRequest] = []

    def complete_json(self, request: ModelRequest, **_kwargs: object) -> ModelResponse:
        self.requests.append(request)
        if request.mode in self.failures:
            raise ProviderResponseError("mode rejected")
        return ModelResponse(
            content=self.content,
            raw_text=self.content,
            model=request.model,
            attempts=1,
            request_bytes=len(request.encoded_payload()),
            response_bytes=len(self.content.encode("utf-8")),
            status_code=200,
            mode=request.mode,
            output_contract=request.output_contract,
            tool_name=request.tool_name,
            metadata={"usage": {"prompt_tokens": 3}},
        )

    def close(self) -> None:
        return None


def _profile(*, max_input_tokens: int = 12_000, preference: str = "auto") -> InferenceProfile:
    return InferenceProfile(
        profile_id="profile",
        base_url="https://provider.example/v1",
        model="model",
        secret_ref="provider-secret",
        max_input_tokens=max_input_tokens,
        structured_output_preference=preference,
    )


def _store(profile: InferenceProfile | None = None) -> tuple[sqlite3.Connection, InferenceProfileStore]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
        "VALUES ('space', 'tests', '2026-08-09T00:00:00Z', '2026-08-09T00:00:00Z')"
    )
    store = InferenceProfileStore(connection)
    store.upsert(profile or _profile())
    store.bind_slot("space", slot="operational", profile_id="profile")
    connection.commit()
    return connection, store


def _secret_store(tmp_path) -> SecretStore:
    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put("provider-secret", "TOP_SECRET")
    return secrets


def test_all_four_modes_have_separate_payload_shapes_and_capabilities() -> None:
    base = {
        "model": "model",
        "messages": (
            ChatMessage(role="system", content="technical role"),
            ChatMessage(role="user", content="return JSON"),
        ),
        "max_output_tokens": 42,
        "output_contract": CONTRACT,
        "tool_name": "submit_result",
        "token_parameter": "max_completion_tokens",
        "supports_system_role": False,
        "supports_seed": True,
        "seed": 7,
    }

    schema = build_payload_json_schema(ModelRequest(**base, mode="json_schema"))
    assert schema["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "technical_result",
            "strict": True,
            "schema": CONTRACT["json_schema"],
        },
    }
    assert "max_completion_tokens" in schema
    assert "max_tokens" not in schema
    assert schema["messages"][0]["role"] == "user"  # type: ignore[index]
    assert schema["seed"] == 7

    tool = build_payload_tool_call(ModelRequest(**base, mode="tool_call"))
    assert "response_format" not in tool
    assert tool["tools"][0]["function"]["name"] == "submit_result"  # type: ignore[index]

    object_payload = build_payload_json_object(ModelRequest(**base, mode="json_object"))
    assert object_payload["response_format"] == {"type": "json_object"}
    legacy = ModelRequest(
        model="model",
        messages=(ChatMessage(role="user", content="return"),),
        max_output_tokens=10,
        response_format={"type": "json_object"},
    )
    assert legacy.to_openai_payload()["response_format"] == {"type": "json_object"}

    prompt = build_payload_prompt_only(ModelRequest(**base, mode="prompt_only"))
    assert "response_format" not in prompt
    assert "Do not use Markdown" in prompt["messages"][-1]["content"]  # type: ignore[index]


def test_openai_provider_extracts_tool_arguments_and_fenced_json() -> None:
    responses = [
        {
            "model": "model",
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "submit_result",
                                    "arguments": '{"ok":true}',
                                }
                            }
                        ]
                    }
                }
            ],
        },
        {
            "model": "model",
            "choices": [
                {"message": {"content": "```json\n{\"ok\":true}\n```"}}
            ],
        },
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="secret",
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    tool_response = provider.complete_json(
        ModelRequest(
            model="model",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=10,
            mode="tool_call",
            output_contract=CONTRACT,
            tool_name="submit_result",
        )
    )
    fenced_response = provider.complete_json(
        ModelRequest(
            model="model",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=10,
            mode="json_object",
        )
    )
    assert json.loads(tool_response.content) == {"ok": True}
    assert decode_json_content(fenced_response.content) == {"ok": True}
    provider.close()


def test_json_schema_is_rejected_before_http_when_contract_is_missing() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="secret",
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderConfigurationError):
        provider.complete_json(
            ModelRequest(
                model="model",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=10,
                mode="json_schema",
            )
        )
    assert called is False
    provider.close()


def test_strict_profile_accepts_bounded_local_reference_patterns() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "object_ref": {"type": "string", "pattern": r"^uo[1-8]$"},
        },
        "required": ["object_ref"],
    }

    assert validate_strict_schema_profile(schema) == schema

    invalid = {
        **schema,
        "properties": {
            "object_ref": {"type": "integer", "pattern": r"^uo[1-8]$"}
        },
    }
    with pytest.raises(ValueError, match="pattern"):
        validate_strict_schema_profile(invalid)


def test_strict_profile_accepts_core_local_definitions() -> None:
    schema = {
        "$defs": {
            "claim": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            }
        },
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"$ref": "#/$defs/claim"},
                        {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False,
                        },
                    ]
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }

    assert validate_strict_schema_profile(schema) == schema


def test_strict_profile_rejects_external_or_unknown_refs() -> None:
    schema = {
        "$defs": {},
        "type": "object",
        "properties": {"value": {"$ref": "https://example.invalid/schema"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError, match="must be local"):
        validate_strict_schema_profile(schema)

    schema["properties"]["value"] = {"$ref": "#/$defs/missing"}
    with pytest.raises(ValueError, match="is unknown"):
        validate_strict_schema_profile(schema)


def test_openai_provider_merges_non_secret_extra_body_without_overriding_contract() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "model",
                "choices": [{"message": {"content": '{"ok":true}'}}],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="secret",
        max_retries=0,
        extra_body={"reasoning": {"effort": "none", "exclude": True}},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.complete_json(
        ModelRequest(
            model="model",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=10,
            mode="json_object",
        )
    )
    provider.close()

    assert seen["reasoning"] == {"effort": "none", "exclude": True}
    assert seen["response_format"] == {"type": "json_object"}


def test_probe_auto_order_manual_override_and_capability_persistence(tmp_path) -> None:
    connection, store = _store()
    try:
        secret_store = _secret_store(tmp_path)
        auto_provider = _FakeProvider(failures={"json_schema"})
        auto_result = ProviderProbe(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=secret_store,
            capability_store=store,
            provider_factory=lambda _profile, _secret: auto_provider,
        ).probe("space", ProfileSlot.OPERATIONAL)
        assert auto_result.attempted_modes == (STRICT_JSON_SCHEMA_MODE,)
        assert auto_result.selected_mode == STRICT_JSON_SCHEMA_MODE
        assert store.get_capabilities("profile") == auto_result.capabilities
        assert auto_result.capabilities.native_schema_strictness is True
        assert auto_result.capabilities.supports(STRICT_JSON_SCHEMA_MODE) is True

        store.upsert(_profile(preference="prompt_only"))
        manual_provider = _FakeProvider()
        manual_result = ProviderProbe(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=secret_store,
            capability_store=store,
            provider_factory=lambda _profile, _secret: manual_provider,
        ).probe("space", "operational")
        assert manual_result.attempted_modes == (STRICT_JSON_SCHEMA_MODE,)
        assert manual_result.selected_mode == STRICT_JSON_SCHEMA_MODE
    finally:
        connection.close()


def test_reasoning_provider_probe_reserves_bounded_output_headroom() -> None:
    contract = {
        "contract_name": "probe",
        "compact_template": {"ok": True},
    }
    request = _probe_request(_profile(), contract, "json_object")

    assert request.max_output_tokens == PROBE_MAX_OUTPUT_TOKENS
    assert request.max_output_tokens > 64


def test_structured_provider_selects_capability_and_roundtrips_digest_and_fence(
    tmp_path,
) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest=CONTRACT["schema_digest"],
                probe_status="passed",
            )
        )
        fake = _FakeProvider(content="```json\n{\"ok\":true}\n```")
        result = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=CONTRACT,
        )
        assert fake.requests[0].mode == "tool_call"
        assert result.data == {"ok": True}
        assert result.structured_output_mode == "tool_call"
        assert result.contract_digest == CONTRACT["schema_digest"]
        assert result.raw_model_text.startswith("```")
        assert result.metadata["usage"] == {"prompt_tokens": 3}
        assert result.parsed_json == {"ok": True}
        assert result.usage == {"prompt_tokens": 3}
        assert result.transport_error is None
        assert result.native_schema_valid is True
    finally:
        connection.close()


def test_strict_semantic_request_is_probe_gated_and_never_falls_back(tmp_path) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )
        fake = _FakeProvider(failures={STRICT_JSON_SCHEMA_MODE})
        provider = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        )
        with pytest.raises(ProviderResponseError):
            provider.generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
                output_contract=STRICT_CONTRACT,
                structured_output_requirement=strict_requirement_for_contract(
                    STRICT_CONTRACT
                ),
                mode=STRICT_JSON_SCHEMA_MODE,
            )
        assert [request.mode for request in fake.requests] == [STRICT_JSON_SCHEMA_MODE]
        assert fake.requests[0].structured_output_requirement is not None
        assert fake.requests[0].structured_output_requirement["strict"] is True
    finally:
        connection.close()


def test_strict_semantic_request_requires_a_verified_capability(tmp_path) -> None:
    connection, store = _store()
    try:
        created = False

        def factory(_profile: InferenceProfile, _secret: str) -> _FakeProvider:
            nonlocal created
            created = True
            return _FakeProvider()

        with pytest.raises(
            StructuredJsonCapabilityError,
            match="capability has not been verified",
        ) as failure:
            StructuredJsonProvider(
                profile_resolver=StoreBackedProfileResolver(store),
                secret_store=_secret_store(tmp_path),
                capability_store=store,
                provider_factory=factory,
            ).generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
                output_contract=STRICT_CONTRACT,
                structured_output_requirement=strict_requirement_for_contract(
                    STRICT_CONTRACT
                ),
                mode=STRICT_JSON_SCHEMA_MODE,
            )
        assert failure.value.code == "provider_capability_unverified"
        assert created is False
    finally:
        connection.close()


def test_expired_verified_capability_does_not_disable_unchanged_profile(
    tmp_path,
) -> None:
    connection, store = _store()
    try:
        profile_fingerprint = generation_profile_fingerprint(
            _profile(), structured_output_override=STRICT_JSON_SCHEMA_MODE
        )
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                profile_fingerprint=profile_fingerprint,
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
                expires_at="2020-01-01T00:00:00+00:00",
            )
        )
        fake = _FakeProvider(content='{"ok":true}')
        result = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=STRICT_CONTRACT,
            structured_output_requirement=strict_requirement_for_contract(
                STRICT_CONTRACT
            ),
            mode=STRICT_JSON_SCHEMA_MODE,
        )

        assert result.data == {"ok": True}
        assert len(fake.requests) == 1
        cached = store.get_capabilities(
            "profile",
            profile_fingerprint=profile_fingerprint,
            fresh_only=True,
        )
        assert cached is not None
        assert cached.is_fresh(
            profile_fingerprint="changed-profile",
            now="2099-01-01T00:00:00+00:00",
        ) is False
    finally:
        connection.close()


def test_strict_schema_mismatch_fails_before_core_delivery(tmp_path) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )
        fake = _FakeProvider(content='{"ok":"wrong"}')

        with pytest.raises(StructuredJsonSchemaError) as failure:
            StructuredJsonProvider(
                profile_resolver=StoreBackedProfileResolver(store),
                secret_store=_secret_store(tmp_path),
                capability_store=store,
                provider_factory=lambda _profile, _secret: fake,
            ).generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
                output_contract=STRICT_CONTRACT,
                structured_output_requirement=strict_requirement_for_contract(
                    STRICT_CONTRACT
                ),
                mode=STRICT_JSON_SCHEMA_MODE,
            )

        assert failure.value.code == "schema_shape_failure"
        assert len(fake.requests) == 1
    finally:
        connection.close()


def test_local_schema_validation_checks_nested_bounds_refs_and_one_of() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "$defs": {
            "payload": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "refs": {
                        "type": "array",
                        "minItems": 0,
                        "maxItems": 0,
                        "items": {"type": "string", "enum": ["e1"]},
                    }
                },
                "required": ["refs"],
            }
        },
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "state": {"$ref": "#/$defs/payload"}
                            },
                            "required": ["state"],
                        },
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "procedure": {"$ref": "#/$defs/payload"}
                            },
                            "required": ["procedure"],
                        },
                    ]
                },
            }
        },
        "required": ["claims"],
    }

    issues = _advisory_schema_issues(
        {"claims": [{"state": {"refs": ["e1"]}}]},
        schema,
    )

    assert issues
    assert issues[0]["code"] == "oneOf"
    assert _advisory_schema_issues(
        {"claims": [{"state": {"refs": []}}]}, schema
    ) == []


def test_local_schema_validation_rejects_unknown_nested_fields() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "item": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"name": {"type": "string", "maxLength": 4}},
                "required": ["name"],
            }
        },
        "required": ["item"],
    }

    issues = _advisory_schema_issues(
        {"item": {"name": "valid", "extra": True}}, schema
    )

    assert {issue["code"] for issue in issues} == {
        "additionalProperties",
        "maxLength",
    }


def test_forced_strict_retry_pins_next_configured_provider_route(tmp_path) -> None:
    routed_profile = _profile(preference=STRICT_JSON_SCHEMA_MODE).model_copy(
        update={
            "extra_body": {
                "provider": {
                    "order": ["baidu/fp8", "deepinfra/fp8"],
                    "only": ["baidu/fp8", "deepinfra/fp8"],
                    "allow_fallbacks": True,
                    "require_parameters": True,
                }
            }
        }
    )
    connection, store = _store(routed_profile)
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )
        constructed_profiles: list[InferenceProfile] = []

        def factory(profile: InferenceProfile, _secret: str) -> _FakeProvider:
            constructed_profiles.append(profile)
            return _FakeProvider()

        result = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=factory,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=STRICT_CONTRACT,
            structured_output_requirement=strict_requirement_for_contract(
                STRICT_CONTRACT
            ),
            mode=STRICT_JSON_SCHEMA_MODE,
            force_provider_fallback=True,
        )

        provider_options = constructed_profiles[0].extra_body["provider"]
        assert provider_options == {
            "order": ["deepinfra/fp8"],
            "only": ["deepinfra/fp8"],
            "allow_fallbacks": False,
            "require_parameters": True,
        }
        assert result.metadata["forced_provider_fallback"] is True
        assert result.metadata["forced_provider_route"] == "deepinfra/fp8"
    finally:
        connection.close()


def test_malformed_completion_keeps_verified_capability_for_bounded_retry(tmp_path) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )
        fake = _FakeProvider(content="not-json")
        provider = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        )

        with pytest.raises(StructuredJsonResponseError):
            provider.generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
                output_contract=STRICT_CONTRACT,
                structured_output_requirement=strict_requirement_for_contract(
                    STRICT_CONTRACT
                ),
                mode=STRICT_JSON_SCHEMA_MODE,
            )
        cached = store.get_capabilities("profile")
        assert cached is not None
        assert cached.probe_status == "passed"
        assert cached.is_fresh(profile_fingerprint="fixture-profile") is True
    finally:
        connection.close()


def test_provider_shape_failure_keeps_capability_and_allows_fresh_retry(
    tmp_path,
) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode=STRICT_JSON_SCHEMA_MODE,
                structured_json_schema=True,
                native_schema_strictness=True,
                probe_contract_digest=STRICT_CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )

        class FailOnceProvider(_FakeProvider):
            def __init__(self) -> None:
                super().__init__()
                self.attempts = 0

            def complete_json(
                self, request: ModelRequest, **kwargs: object
            ) -> ModelResponse:
                self.attempts += 1
                if self.attempts == 1:
                    self.requests.append(request)
                    raise ProviderResponseError("incomplete provider envelope")
                return super().complete_json(request, **kwargs)

        fake = FailOnceProvider()
        provider = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        )
        request = {
            "memory_space_id": "space",
            "messages": (ChatMessage(role="user", content="return"),),
            "max_output_tokens": 20,
            "profile_slot": ProfileSlot.OPERATIONAL,
            "output_contract": STRICT_CONTRACT,
            "structured_output_requirement": strict_requirement_for_contract(
                STRICT_CONTRACT
            ),
            "mode": STRICT_JSON_SCHEMA_MODE,
        }

        with pytest.raises(ProviderResponseError):
            provider.generate_json(**request)

        cached = store.get_capabilities("profile")
        assert cached is not None
        assert cached.probe_status == "passed"
        assert cached.is_fresh(profile_fingerprint="fixture-profile") is True

        result = provider.generate_json(**request)

        assert result.data == {"ok": True}
        assert fake.attempts == 2
    finally:
        connection.close()


def test_structured_provider_falls_back_once_after_automatic_mode_rejection(
    tmp_path,
) -> None:
    connection, store = _store()
    try:
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest=CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
            )
        )
        fake = _FakeProvider(failures={"tool_call"})
        result = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: fake,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=CONTRACT,
        )

        assert [request.mode for request in fake.requests] == [
            "tool_call",
            "json_object",
        ]
        assert result.structured_output_mode == "json_object"
        assert result.metadata["structured_output_fallback"] is True
        assert result.metadata["structured_output_fallback_from"] == "tool_call"
        assert result.metadata["structured_output_fallback_to"] == "json_object"
        assert result.metadata["structured_output_fallback_error_code"] == (
            "invalid_provider_response"
        )
        cached = store.get_capabilities("profile")
        assert cached is not None
        assert cached.structured_output_mode == "json_object"
        assert cached.json_schema_supported is False
        assert cached.tool_call_supported is False
        assert cached.json_object_supported is True
        assert cached.probe_status == "passed"
        assert cached.probe_result == "passed"
        assert cached.is_fresh(profile_fingerprint="fixture-profile") is True
    finally:
        connection.close()


def test_successful_fallback_is_reused_after_store_restart(tmp_path) -> None:
    database = tmp_path / "rounds.db"
    connection = sqlite3.connect(database, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        migrations.apply_migrations(connection)
        connection.execute(
            "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
            "VALUES ('space', 'tests', '2026-08-09T00:00:00Z', '2026-08-09T00:00:00Z')"
        )
        store = InferenceProfileStore(connection)
        store.upsert(_profile())
        store.bind_slot("space", slot="operational", profile_id="profile")
        store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest=CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
                expires_at="2099-01-01T00:00:00+00:00",
            )
        )
        first_provider = _FakeProvider(failures={"tool_call"})
        StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            capability_store=store,
            provider_factory=lambda _profile, _secret: first_provider,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=CONTRACT,
        )
        connection.commit()
    finally:
        connection.close()

    restarted = sqlite3.connect(database, check_same_thread=False)
    restarted.row_factory = sqlite3.Row
    try:
        migrations.apply_migrations(restarted)
        restarted_store = InferenceProfileStore(restarted)
        cached = restarted_store.get_capabilities("profile")
        assert cached is not None
        assert cached.structured_output_mode == "json_object"
        assert cached.tool_call_supported is False
        assert cached.json_object_supported is True
        assert cached.probe_status == "passed"
        assert cached.is_fresh(profile_fingerprint="fixture-profile") is True

        second_provider = _FakeProvider(failures={"tool_call"})
        StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(restarted_store),
            secret_store=_secret_store(tmp_path),
            capability_store=restarted_store,
            provider_factory=lambda _profile, _secret: second_provider,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=CONTRACT,
        )
        assert [request.mode for request in second_provider.requests] == [
            "json_object"
        ]
    finally:
        restarted.close()


def test_parseable_schema_mismatch_is_advisory_and_reaches_core(tmp_path) -> None:
    connection, store = _store()
    try:
        fake = _FakeProvider(content='{"ok":"wrong"}')
        result = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            provider_factory=lambda _profile, _secret: fake,
        ).generate_json(
            memory_space_id="space",
            messages=(ChatMessage(role="user", content="return"),),
            max_output_tokens=20,
            profile_slot=ProfileSlot.OPERATIONAL,
            output_contract=CONTRACT,
        )

        assert result.parsed_json == {"ok": "wrong"}
        assert result.native_schema_valid is False
        assert result.native_schema_issues
        assert result.transport_error is None
    finally:
        connection.close()


def test_provider_outage_retains_fresh_capability_cache(tmp_path) -> None:
    connection, store = _store()
    try:
        cached = store.upsert_capabilities(
            ProviderCapabilities(
                profile_id="profile",
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest=CONTRACT["schema_digest"],
                probe_status="passed",
                probe_result="passed",
                expires_at="2099-01-01T00:00:00+00:00",
            )
        )

        class OutageProvider(_FakeProvider):
            def complete_json(self, request: ModelRequest, **_kwargs: object) -> ModelResponse:
                del request
                raise ProviderTransportError("provider unavailable")

        with pytest.raises(ProviderTransportError):
            StructuredJsonProvider(
                profile_resolver=StoreBackedProfileResolver(store),
                secret_store=_secret_store(tmp_path),
                capability_store=store,
                provider_factory=lambda _profile, _secret: OutageProvider(),
            ).generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
                output_contract=CONTRACT,
            )
        retained = store.get_capabilities("profile")
        assert retained is not None
        assert retained.probe_status == cached.probe_status == "passed"
        assert retained.expires_at == cached.expires_at
    finally:
        connection.close()


def test_input_budget_rejection_happens_before_provider_factory(tmp_path) -> None:
    connection, store = _store(_profile(max_input_tokens=1))
    try:
        created = False

        def factory(_profile: InferenceProfile, _secret: str) -> _FakeProvider:
            nonlocal created
            created = True
            raise AssertionError("provider must not be constructed")

        provider = StructuredJsonProvider(
            profile_resolver=StoreBackedProfileResolver(store),
            secret_store=_secret_store(tmp_path),
            provider_factory=factory,
        )
        with pytest.raises(InputBudgetExceededError) as error:
            provider.generate_json(
                memory_space_id="space",
                messages=(ChatMessage(role="user", content="too much input"),),
                max_output_tokens=20,
                profile_slot=ProfileSlot.OPERATIONAL,
            )
        assert error.value.code == "input_budget_exceeded"
        assert created is False
    finally:
        connection.close()


def test_worker_classifies_budget_failure_as_safe_permanent_error() -> None:
    classification = classify_execution_error(InputBudgetExceededError(10, 1))

    assert classification.error_code == "input_budget_exceeded"
    assert classification.retryable is False
    assert classification.retry_after_seconds == 0


def test_executor_keeps_operation_opaque_and_returns_result_metadata(tmp_path) -> None:
    connection, store = _store()
    try:
        fake = _FakeProvider()
        executor = CoreTaskExecutor(
            json_provider=StructuredJsonProvider(
                profile_resolver=StoreBackedProfileResolver(store),
                secret_store=_secret_store(tmp_path),
                provider_factory=lambda _profile, _secret: fake,
            ),
            embedding_provider=EmbeddingProvider(vectorizer_factory=lambda: None),  # type: ignore[arg-type]
            profile_resolver=StoreBackedProfileResolver(store),
            generate_json_timeout_seconds=2,
            embed_texts_timeout_seconds=2,
        )
        task = GenericExecutionTask(
            task_id="task",
            task_kind="generate_json",
            operation="core_owned_facet_resolution_value_operation",
            operation_input={"facet": "opaque-to-local"},
            profile_slot=ProfileSlot.OPERATIONAL,
            model_request=ModelRequestSpec(
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=20,
                output_contract=CONTRACT,
            ),
            lease={"memory_space_id": "space"},
        )
        result = executor.execute(task)
        assert result.status == "completed"
        assert result.operation == task.operation
        assert result.operation_input == task.operation_input
        assert result.structured_output_mode == "json_object"
        assert result.contract_digest == CONTRACT["schema_digest"]
        assert result.raw_model_text == '{"ok":true}'
        assert fake.requests[0].metadata == {}
        assert "facet" not in json.dumps(fake.requests[0].model_dump())
    finally:
        connection.close()
