"""Operational and background structured-output capability probes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .profile_slots import ProfileResolver, ProfileSlot
from .profiles import (
    InferenceProfile,
    ProviderCapabilities,
    StructuredOutputMode,
    generation_profile_fingerprint,
)
from .strict import STRICT_JSON_SCHEMA_MODE, strict_requirement_for_contract
from .providers.base import ChatMessage, InferenceProvider, ModelRequest
from .providers.openai_compatible import decode_json_content
from .secrets import SecretNotFoundError, SecretStore

ProbeProviderFactory = Callable[[InferenceProfile, str], InferenceProvider]
PROBE_MODE_ORDER: tuple[StructuredOutputMode, ...] = (
    STRICT_JSON_SCHEMA_MODE,
)
PROBE_TOOL_NAME = "submit_structured_result"
# Reasoning-capable models may spend more than the JSON body itself before
# emitting content.  A 64-token probe can therefore report a false transport
# failure even when the same profile can complete the production contract.
PROBE_MAX_OUTPUT_TOKENS = 768
_SAFE_PROBE_ERROR_CODES = frozenset(
    {
        "authentication_error",
        "configuration_error",
        "invalid_provider_response",
        "length_truncation",
        "provider_error",
        "provider_transport_error",
        "secret_missing",
        "timeout",
        "transient_provider_error",
    }
)


class ProbeCapabilityStore(Protocol):
    def upsert_capabilities(
        self, capabilities: ProviderCapabilities
    ) -> ProviderCapabilities: ...


class ProviderProbeResult(BaseModel):
    """Secret-free report returned by a real provider probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    slot: str = Field(min_length=1)
    probe_kind: str = Field(min_length=1)
    status: str = Field(min_length=1)
    selected_mode: StructuredOutputMode = "auto"
    attempted_modes: tuple[StructuredOutputMode, ...] = ()
    capabilities: ProviderCapabilities
    contract_digest: str = Field(min_length=1)
    error_code: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def mode(self) -> StructuredOutputMode:
        return self.selected_mode


class ProviderProbe:
    """Run a real small generation-slot contract through an endpoint."""

    def __init__(
        self,
        *,
        profile_resolver: ProfileResolver,
        secret_store: SecretStore,
        capability_store: ProbeCapabilityStore | None = None,
        provider_factory: ProbeProviderFactory | None = None,
        capability_ttl_seconds: int = 86_400,
    ) -> None:
        self._profile_resolver = profile_resolver
        self._secret_store = secret_store
        self._capability_store = capability_store
        if capability_ttl_seconds < 1:
            raise ValueError("capability_ttl_seconds must be positive")
        self.capability_ttl_seconds = capability_ttl_seconds
        if provider_factory is None:
            from .structured_json_provider import default_provider_factory

            self._provider_factory: ProbeProviderFactory = default_provider_factory
        else:
            self._provider_factory = provider_factory

    def probe(
        self,
        memory_space_id: str,
        slot: ProfileSlot | str,
        *,
        mode_override: StructuredOutputMode | None = None,
        mode: StructuredOutputMode | None = None,
        force: bool = False,
        reprobe: bool = False,
        capability_ttl_seconds: int | None = None,
    ) -> ProviderProbeResult:
        if mode_override is not None and mode is not None and mode_override != mode:
            raise ValueError("conflicting probe mode overrides")
        override = mode_override or mode
        profile_slot = slot if isinstance(slot, ProfileSlot) else ProfileSlot(slot)
        if profile_slot is ProfileSlot.EMBEDDING:
            raise ValueError("structured provider probe requires a generation slot")
        profile = self._profile_resolver.resolve_profile(memory_space_id, profile_slot)
        probe_kind = profile_slot.value
        contract = _probe_contract(probe_kind)
        contract_digest = str(contract["schema_digest"])
        modes = _probe_modes(profile, override)
        profile_fingerprint = generation_profile_fingerprint(
            profile,
            structured_output_override=override,
        )
        cached = self._cached_capabilities(profile.profile_id)
        if (
            cached is not None
            and not force
            and not reprobe
            and cached.is_fresh(profile_fingerprint=profile_fingerprint)
            and cached.probe_contract_digest == contract_digest
        ):
            selected = _selected_mode(cached)
            return ProviderProbeResult(
                profile_id=profile.profile_id,
                slot=profile_slot.value,
                probe_kind=probe_kind,
                status="passed",
                selected_mode=selected,
                attempted_modes=(selected,) if selected != "auto" else (),
                capabilities=cached,
                contract_digest=contract_digest,
                metadata={"mode_order": list(modes), "cache_hit": True},
            )

        try:
            secret = self._secret_store.get(profile.secret_ref)
        except SecretNotFoundError:
            return self._failed_result(
                profile,
                profile_slot,
                contract_digest,
                modes,
                "secret_missing",
                previous=cached,
            )

        successful: set[StructuredOutputMode] = set()
        attempted: list[StructuredOutputMode] = []
        last_error_code: str | None = None
        selected: StructuredOutputMode = "auto"
        try:
            provider = self._provider_factory(profile, secret)
        except Exception as exc:  # noqa: BLE001 - persist a safe probe failure
            return self._failed_result(
                profile,
                profile_slot,
                contract_digest,
                modes,
                _safe_probe_error_code(exc),
                previous=cached,
            )
        try:
            for candidate in modes:
                attempted.append(candidate)
                request = _probe_request(profile, contract, candidate)
                try:
                    response = provider.complete_json(request)
                    decoded = decode_json_content(response.content)
                    if not isinstance(decoded, dict):
                        raise TypeError("probe response is not an object")
                except Exception as exc:  # noqa: BLE001 - one mode must not abort auto
                    last_error_code = _safe_probe_error_code(exc)
                    continue
                successful.add(candidate)
                selected = candidate
                break
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()

        status: Literal["passed", "failed"] = (
            "passed" if selected != "auto" else "failed"
        )
        now = datetime.now(timezone.utc)
        ttl = self.capability_ttl_seconds if capability_ttl_seconds is None else capability_ttl_seconds
        if ttl < 1:
            raise ValueError("capability_ttl_seconds must be positive")
        timestamp = now.isoformat(timespec="seconds")
        capabilities = ProviderCapabilities(
            profile_id=profile.profile_id,
            profile_fingerprint=profile_fingerprint,
            transport=profile.provider_kind,
            model=profile.model,
            structured_output_mode=selected,
            json_schema_supported=(
                STRICT_JSON_SCHEMA_MODE in successful or "json_schema" in successful
            ),
            tool_call_supported="tool_call" in successful,
            json_object_supported="json_object" in successful,
            prompt_only_supported="prompt_only" in successful,
            structured_json_schema=(
                STRICT_JSON_SCHEMA_MODE in successful or "json_schema" in successful
            ),
            structured_json_object="json_object" in successful,
            tool_calling="tool_call" in successful,
            plain_json_prompt="prompt_only" in successful,
            native_schema_strictness=(
                STRICT_JSON_SCHEMA_MODE in successful or "json_schema" in successful
            ),
            detected_capabilities={
                "structured_json_schema": (
                    STRICT_JSON_SCHEMA_MODE in successful or "json_schema" in successful
                ),
                "structured_json_object": "json_object" in successful,
                "tool_calling": "tool_call" in successful,
                "plain_json_prompt": "prompt_only" in successful,
                "native_schema_strictness": (
                    STRICT_JSON_SCHEMA_MODE in successful or "json_schema" in successful
                ),
            },
            probe_contract_digest=contract_digest,
            probe_status=status,
            last_probed_at=timestamp,
            last_error_code=None if status == "passed" else last_error_code,
            probed_at=timestamp,
            expires_at=(now + timedelta(seconds=ttl)).isoformat(timespec="seconds"),
            probe_result=status,
            last_error=None if status == "passed" else last_error_code,
        )
        if status == "failed" and cached is not None and cached.is_fresh(
            profile_fingerprint=profile_fingerprint
        ):
            self._record_probe_error(profile.profile_id, last_error_code or "probe_failed")
            capabilities = cached
        else:
            self._persist(capabilities)
        return ProviderProbeResult(
            profile_id=profile.profile_id,
            slot=profile_slot.value,
            probe_kind=probe_kind,
            status=status,
            selected_mode=selected,
            attempted_modes=tuple(attempted),
            capabilities=capabilities,
            contract_digest=contract_digest,
            error_code=capabilities.last_error_code,
            metadata={"mode_order": list(modes)},
        )

    run = probe

    def probe_operational(
        self,
        memory_space_id: str,
        *,
        mode_override: StructuredOutputMode | None = None,
    ) -> ProviderProbeResult:
        return self.probe(
            memory_space_id,
            ProfileSlot.OPERATIONAL,
            mode_override=mode_override,
        )

    def probe_background(
        self,
        memory_space_id: str,
        *,
        mode_override: StructuredOutputMode | None = None,
    ) -> ProviderProbeResult:
        return self.probe(
            memory_space_id,
            ProfileSlot.BACKGROUND,
            mode_override=mode_override,
        )

    def probe_object_resolution(
        self,
        memory_space_id: str,
        *,
        mode_override: StructuredOutputMode | None = None,
    ) -> ProviderProbeResult:
        return self.probe(
            memory_space_id,
            ProfileSlot.OBJECT_RESOLUTION,
            mode_override=mode_override,
        )

    def _cached_capabilities(self, profile_id: str) -> ProviderCapabilities | None:
        if self._capability_store is None:
            return None
        getter = getattr(self._capability_store, "get_capabilities", None)
        if not callable(getter):
            return None
        result = getter(profile_id)
        return result if isinstance(result, ProviderCapabilities) else None

    def _record_probe_error(self, profile_id: str, error_code: str) -> None:
        if self._capability_store is None:
            return
        recorder = getattr(self._capability_store, "record_probe_error", None)
        if callable(recorder):
            recorder(profile_id, error_code=error_code)

    def _persist(self, capabilities: ProviderCapabilities) -> None:
        if self._capability_store is not None:
            self._capability_store.upsert_capabilities(capabilities)

    def _failed_result(
        self,
        profile: InferenceProfile,
        slot: ProfileSlot,
        contract_digest: str,
        modes: tuple[StructuredOutputMode, ...],
        error_code: str,
        previous: ProviderCapabilities | None = None,
    ) -> ProviderProbeResult:
        if previous is not None and previous.probe_status == "passed":
            self._record_probe_error(profile.profile_id, error_code)
            return ProviderProbeResult(
                profile_id=profile.profile_id,
                slot=slot.value,
                probe_kind=slot.value,
                status="failed",
                attempted_modes=(),
                capabilities=previous,
                contract_digest=contract_digest,
                error_code=error_code,
                metadata={"mode_order": list(modes), "cache_retained": True},
            )
        capabilities = ProviderCapabilities(
            profile_id=profile.profile_id,
            profile_fingerprint=generation_profile_fingerprint(profile),
            transport=profile.provider_kind,
            model=profile.model,
            structured_output_mode="auto",
            plain_json_prompt=False,
            probe_contract_digest=contract_digest,
            probe_status="failed",
            last_probed_at=_now(),
            last_error_code=error_code,
            probed_at=_now(),
            probe_result="failed",
            last_error=error_code,
        )
        self._persist(capabilities)
        return ProviderProbeResult(
            profile_id=profile.profile_id,
            slot=slot.value,
            probe_kind=slot.value,
            status="failed",
            attempted_modes=(),
            capabilities=capabilities,
            contract_digest=contract_digest,
            error_code=error_code,
            metadata={"mode_order": list(modes)},
        )


def _probe_modes(
    profile: InferenceProfile,
    override: StructuredOutputMode | None,
) -> tuple[StructuredOutputMode, ...]:
    if override is not None and override != "auto":
        # An explicit legacy override remains available for bounded
        # compatibility diagnostics, but the default/install probe below is
        # always the real strict transport.
        return (override,)
    return PROBE_MODE_ORDER


def _probe_contract(probe_kind: str) -> dict[str, object]:
    if probe_kind not in {"operational", "object_resolution", "background"}:
        raise ValueError(f"unsupported structured probe kind: {probe_kind}")
    # This is intentionally a small, provider-neutral strict probe. It uses
    # required fields, an enum, a closed object, and a non-empty array so a
    # successful response proves the actual strict transport rather than only
    # parseable JSON mode.
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "state": {"type": "string", "enum": ["ok"]},
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "integer"},
            },
        },
        "required": ["schema_version", "state", "items"],
    }
    template: dict[str, object] = {
        "schema_version": 1,
        "state": "ok",
        "items": [1],
    }
    contract_name = f"{probe_kind}_strict_structured_output"
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "contract_name": contract_name,
        "schema_version": 1,
        "json_schema": schema,
        "schema_digest": digest,
        "compact_template": template,
        "examples": [],
        "max_output_tokens": 256,
        "allow_empty_result": True,
    }


def _probe_request(
    profile: InferenceProfile,
    contract: Mapping[str, object],
    mode: StructuredOutputMode,
) -> ModelRequest:
    strict_requirement = (
        strict_requirement_for_contract(contract)
        if mode == STRICT_JSON_SCHEMA_MODE
        else None
    )
    return ModelRequest(
        model=profile.model,
        messages=(
            ChatMessage(
                role="system",
                content="This is a technical provider capability probe. Return the requested JSON object only.",
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Return one JSON object matching the {contract['contract_name']} contract. "
                    f"Use this compact example exactly as the shape guide: {json.dumps(contract['compact_template'], ensure_ascii=False, sort_keys=True)}"
                ),
            ),
        ),
        max_output_tokens=min(profile.max_output_tokens, PROBE_MAX_OUTPUT_TOKENS),
        output_contract=dict(contract),
        structured_output_requirement=strict_requirement,
        mode=mode,
        tool_name=PROBE_TOOL_NAME,
        token_parameter=profile.token_parameter,
        supports_system_role=profile.supports_system_role,
        supports_seed=profile.supports_seed,
    )


def _safe_probe_error_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in _SAFE_PROBE_ERROR_CODES:
        return code
    if isinstance(exc, ValueError):
        return "invalid_provider_response"
    return "provider_error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _selected_mode(capabilities: ProviderCapabilities) -> StructuredOutputMode:
    if capabilities.structured_output_mode == STRICT_JSON_SCHEMA_MODE:
        return STRICT_JSON_SCHEMA_MODE
    for candidate in PROBE_MODE_ORDER:
        if capabilities.supports(candidate):
            return candidate
    return capabilities.structured_output_mode


__all__ = [
    "PROBE_MODE_ORDER",
    "PROBE_MAX_OUTPUT_TOKENS",
    "PROBE_TOOL_NAME",
    "ProviderProbe",
    "ProviderProbeResult",
]
