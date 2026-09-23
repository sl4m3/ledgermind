"""Inference profile models owned by the Local service."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProviderKind = Literal["openai_compatible", "google_genai", "nvidia_nim"]
StructuredOutputMode = Literal[
    "auto",
    "strict_json_schema",
    "json_schema",
    "tool_call",
    "json_object",
    "prompt_only",
]
StructuredOutputPreference = StructuredOutputMode
TokenParameter = Literal["max_tokens", "max_completion_tokens"]
ProbeStatus = Literal["unknown", "passed", "failed"]

EMBEDDING_PROFILE_DIGEST_ALGORITHM = "sha256"
EMBEDDING_PROFILE_DIGEST_SCHEMA_VERSION = 1
# Round Semantic bounds the complete provider-visible request to 64k
# characters. Keep the generation input allowance at the same numeric ceiling
# so Local does not reject a request that Core has already admitted, including
# conservative estimation for non-ASCII semantic languages.
DEFAULT_GENERATION_MAX_INPUT_TOKENS = 64_000
_SENSITIVE_CONFIG_PARTS = (
    "api_key",
    "access_key",
    "auth",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def _is_sensitive_config_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_CONFIG_PARTS)


def _safe_config_value(value: object, *, key: str | None = None) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            config_key = str(raw_key).strip()
            if not config_key or _is_sensitive_config_key(config_key):
                continue
            result[config_key] = _safe_config_value(raw_value, key=config_key)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_config_value(item) for item in value]
    if isinstance(value, str):
        if key is not None and key.casefold().endswith(("url", "endpoint")):
            parsed = urlparse(value.strip())
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                # Query and fragment fields may contain provider credentials.
                hostname = parsed.hostname or ""
                if ":" in hostname and not hostname.startswith("["):
                    hostname = f"[{hostname}]"
                try:
                    port = parsed.port
                except ValueError:
                    port = None
                safe_netloc = hostname + (f":{port}" if port is not None else "")
                return parsed._replace(
                    netloc=safe_netloc, query="", fragment=""
                ).geturl().rstrip("/")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("embedding profile config must contain finite numbers")
        return value
    raise TypeError(
        f"embedding profile config contains unsupported value type {type(value).__name__}"
    )


def _safe_embedding_config(config: Mapping[str, object] | None) -> dict[str, object]:
    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise TypeError("embedding profile config must be a mapping")
    safe = _safe_config_value(config)
    if not isinstance(safe, dict):  # pragma: no cover - guarded by the helper
        raise TypeError("embedding profile config must be an object")
    return safe


def embedding_profile_fingerprint(
    model_id: str,
    model_version: str,
    dimensions: int | None,
    config: Mapping[str, object] | None = None,
) -> str:
    """Return a stable, token-free identity for one embedding profile.

    The canonical material deliberately contains only model identity,
    dimensions and provider configuration. Secret-bearing config keys are
    omitted before hashing, so a token can never affect this digest.
    """

    normalized_model_id = _required_text(model_id, "model_id")
    normalized_model_version = _required_text(model_version, "model_version")
    if dimensions is not None and (
        isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0
    ):
        raise ValueError("embedding dimensions must be positive when provided")
    material = {
        "config": _safe_embedding_config(config),
        "dimensions": dimensions,
        "model_id": normalized_model_id,
        "model_version": normalized_model_version,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"{EMBEDDING_PROFILE_DIGEST_ALGORITHM}:{hashlib.sha256(encoded).hexdigest()}"


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_provider_extra_body(value: object) -> dict[str, object]:
    """Validate secret-free provider wire extensions stored with a profile."""

    if not isinstance(value, Mapping):
        raise TypeError("extra_body must be a mapping")

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError("extra_body keys must be non-empty strings")
                if _is_sensitive_config_key(key):
                    raise ValueError("extra_body must not contain secret-like keys")
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        elif node is not None and not isinstance(node, (str, bool, int, float)):
            raise ValueError("extra_body must contain JSON-compatible values")

    walk(value)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("extra_body must contain JSON-compatible values") from exc
    if len(encoded.encode("utf-8")) > 100_000:
        raise ValueError("extra_body is too large")
    return dict(value)


GENERATION_PROFILE_DIGEST_ALGORITHM = "sha256"
GENERATION_PROFILE_DIGEST_SCHEMA_VERSION = 1


def generation_profile_fingerprint(
    profile: InferenceProfile,
    *,
    structured_output_override: str | None = None,
) -> str:
    """Return the secret-free identity used by the provider capability cache.

    The digest deliberately describes transport/model configuration rather
    than a credential.  A changed endpoint, model, token parameter or
    structured-output preference therefore cannot accidentally reuse an old
    capability observation.
    """

    from urllib.parse import urlparse

    parsed = urlparse(profile.base_url.strip().rstrip("/"))
    endpoint = parsed._replace(query="", fragment="").geturl().rstrip("/")
    material = {
        "schema_version": GENERATION_PROFILE_DIGEST_SCHEMA_VERSION,
        "provider_kind": profile.provider_kind,
        "transport": profile.provider_kind,
        "endpoint": endpoint,
        "model": profile.model.strip(),
        "timeout_seconds": profile.timeout_seconds,
        "max_retries": profile.max_retries,
        "max_input_tokens": profile.max_input_tokens,
        "max_output_tokens": profile.max_output_tokens,
        "extra_body": profile.extra_body,
        "structured_output_preference": (
            structured_output_override or profile.structured_output_preference
        ),
        "token_parameter": profile.token_parameter,
        "supports_system_role": profile.supports_system_role,
        "supports_seed": profile.supports_seed,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"{GENERATION_PROFILE_DIGEST_ALGORITHM}:{hashlib.sha256(encoded).hexdigest()}"


class EmbeddingProfileIdentity(BaseModel):
    """Secret-free embedding identity that Local can send before scheduling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=500)
    model_version: str = Field(min_length=1, max_length=500)
    dimensions: int | None = Field(default=None, gt=0, le=100_000)
    config: dict[str, object] = Field(default_factory=dict)
    profile_fingerprint: str = Field(default="", min_length=1, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _materialize_fingerprint(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        config = _safe_embedding_config(data.get("config"))
        data["config"] = config
        if not data.get("profile_fingerprint"):
            data["profile_fingerprint"] = embedding_profile_fingerprint(
                str(data.get("model_id", "")),
                str(data.get("model_version", "")),
                data.get("dimensions"),
                config,
            )
        return data

    @model_validator(mode="after")
    def _validate_fingerprint(self) -> EmbeddingProfileIdentity:
        expected = embedding_profile_fingerprint(
            self.model_id,
            self.model_version,
            self.dimensions,
            self.config,
        )
        if self.profile_fingerprint != expected:
            raise ValueError("embedding profile fingerprint does not match identity metadata")
        return self

    @property
    def fingerprint(self) -> str:
        return self.profile_fingerprint

    def to_core_metadata(self) -> dict[str, object]:
        """Return only opaque, non-secret metadata for the Core task boundary."""

        metadata: dict[str, object] = {
            "embedding_model_id": self.model_id,
            # Core treats the stable profile fingerprint as its model-version key.
            "embedding_model_version": self.profile_fingerprint,
            "embedding_profile_fingerprint": self.profile_fingerprint,
            "embedding_profile_model_version": self.model_version,
            "embedding_profile_digest_algorithm": EMBEDDING_PROFILE_DIGEST_ALGORITHM,
            "embedding_profile_digest_algorithm_schema_version": (
                EMBEDDING_PROFILE_DIGEST_SCHEMA_VERSION
            ),
        }
        if self.dimensions is not None:
            metadata["embedding_dimensions"] = self.dimensions
        return metadata


class EmbeddingProfileReadiness(BaseModel):
    """Content-free readiness report for a resolvable embedding profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=200)
    ready: bool
    identity: EmbeddingProfileIdentity | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=200)

    @property
    def profile_fingerprint(self) -> str | None:
        return self.identity.profile_fingerprint if self.identity is not None else None

    def to_core_metadata(self) -> dict[str, object]:
        if not self.ready or self.identity is None:
            raise RuntimeError("embedding profile is not ready")
        return self.identity.to_core_metadata()


class InferenceProfile(BaseModel):
    """Strict, secret-free configuration for one model provider profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=200)
    provider_kind: ProviderKind = "openai_compatible"
    base_url: str = Field(min_length=1, max_length=2_000)
    model: str = Field(min_length=1, max_length=500)
    secret_ref: str = Field(min_length=1, max_length=200)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_input_tokens: int = Field(default=12_000, ge=1, le=200_000)
    max_output_tokens: int = Field(default=2_000, ge=1, le=50_000)
    # Provider-specific, non-secret wire controls stay in Local and never
    # enter the Core task contract.
    extra_body: dict[str, object] = Field(default_factory=dict)
    structured_output_preference: StructuredOutputPreference = "auto"
    token_parameter: TokenParameter = "max_tokens"
    supports_system_role: bool = True
    supports_seed: bool = False
    enabled: bool = True

    @property
    def supports_prompt_cache_key(self) -> bool:
        """Return whether the configured transport accepts a cache hint.

        Local persists this model and the shared inference package consumes
        it. Keep the capability available at that boundary instead of relying
        on the concrete Pydantic class that happens to construct the profile.
        """

        host = (urlparse(self.base_url).hostname or "").casefold().rstrip(".")
        return host == "runinfra.ai" or host.endswith(".runinfra.ai")

    @field_validator("profile_id", "model", "secret_ref")
    @classmethod
    def _validate_text_fields(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _required_text(value, field_name)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        normalized = _required_text(value, "base_url").rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        return normalized

    @field_validator("extra_body")
    @classmethod
    def _validate_extra_body(cls, value: dict[str, object]) -> dict[str, object]:
        return _validate_provider_extra_body(value)


class ProviderCapabilities(BaseModel):
    """Persisted, transport-only observations for one inference profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=200)
    profile_fingerprint: str = Field(default="", max_length=200)
    transport: str = Field(default="openai_compatible", max_length=200)
    model: str = Field(default="", max_length=500)
    structured_output_mode: StructuredOutputMode = "auto"
    json_schema_supported: bool = False
    tool_call_supported: bool = False
    json_object_supported: bool = False
    prompt_only_supported: bool = False
    # Provider-neutral names used by the normalized capability contract.
    structured_json_schema: bool = False
    structured_json_object: bool = False
    tool_calling: bool = False
    plain_json_prompt: bool = False
    native_schema_strictness: bool = False
    max_input_tokens_known: int | None = Field(default=None, ge=1)
    max_output_tokens_known: int | None = Field(default=None, ge=1)
    supports_batch_embeddings: bool = False
    embedding_max_batch: int | None = Field(default=None, ge=1)
    detected_capabilities: dict[str, object] = Field(default_factory=dict)
    probe_contract_digest: str | None = Field(default=None, max_length=200)
    probe_status: ProbeStatus = "unknown"
    last_probed_at: str | None = Field(default=None, max_length=64)
    last_error_code: str | None = Field(default=None, max_length=200)
    probed_at: str | None = Field(default=None, max_length=64)
    expires_at: str | None = Field(default=None, max_length=64)
    probe_result: ProbeStatus = "unknown"
    last_error: str | None = Field(default=None, max_length=200)

    @property
    def mode(self) -> StructuredOutputMode:
        return self.structured_output_mode

    def supports(self, mode: str) -> bool:
        """Return whether a probe recorded support for ``mode``."""

        if mode == "strict_json_schema":
            return self.structured_json_schema and self.native_schema_strictness
        if mode == "json_schema":
            return self.json_schema_supported or self.structured_json_schema
        if mode == "tool_call":
            return self.tool_call_supported or self.tool_calling
        if mode == "json_object":
            return self.json_object_supported or self.structured_json_object
        if mode == "prompt_only":
            return self.prompt_only_supported or self.plain_json_prompt
        return False

    def after_successful_fallback(
        self,
        *,
        failed_mode: StructuredOutputMode,
        successful_mode: StructuredOutputMode,
        error_code: str,
    ) -> ProviderCapabilities:
        """Record a bounded runtime downgrade without forcing a new probe.

        A provider response incompatibility is stronger evidence than the
        original capability probe for the failed transport mode.  If Local
        completes the same request through its one bounded fallback, retain
        the cache as fresh, select the working mode on the next request, and
        keep the failure as secret-free diagnostic metadata.
        """

        if failed_mode == "auto" or successful_mode == "auto":
            raise ValueError("fallback modes must be concrete")
        if failed_mode == successful_mode:
            raise ValueError("fallback modes must be different")
        mode_fields: dict[str, tuple[str, ...]] = {
            "json_schema": ("json_schema_supported", "structured_json_schema"),
            "tool_call": ("tool_call_supported", "tool_calling"),
            "json_object": ("json_object_supported", "structured_json_object"),
            "prompt_only": ("prompt_only_supported", "plain_json_prompt"),
        }
        values = self.model_dump(mode="python")
        for field in mode_fields[failed_mode]:
            values[field] = False
        for field in mode_fields[successful_mode]:
            values[field] = True
        if failed_mode == "json_schema":
            values["native_schema_strictness"] = False
        elif successful_mode == "json_schema":
            values["native_schema_strictness"] = True
        detected = dict(self.detected_capabilities)
        detected.update(
            {
                "structured_json_schema": values["structured_json_schema"],
                "structured_json_object": values["structured_json_object"],
                "tool_calling": values["tool_calling"],
                "plain_json_prompt": values["plain_json_prompt"],
                "native_schema_strictness": values["native_schema_strictness"],
            }
        )
        values["detected_capabilities"] = detected
        values["structured_output_mode"] = successful_mode
        reason = (
            f"capability_execution_failed:{failed_mode}:"
            f"{error_code}"
        )
        values["last_error_code"] = reason
        values["last_error"] = reason
        return type(self).model_validate(values)

    @property
    def detected_capabilities_json(self) -> dict[str, object]:
        """Compatibility spelling for the persisted normalized payload."""

        return dict(self.detected_capabilities)

    def is_fresh(self, *, profile_fingerprint: str, now: str | None = None) -> bool:
        """Return whether this verified observation still matches the profile.

        A successful strict-output probe is an identity-bound capability fact,
        not a lease.  The persisted ``expires_at`` field remains readable for
        backward compatibility and optional background revalidation, but time
        alone must never disable production inference.  Profile changes are
        detected by the fingerprint and explicit probe failures retain their
        failed status.
        """

        del now

        if not profile_fingerprint or (
            self.profile_fingerprint
            and self.profile_fingerprint != profile_fingerprint
        ):
            return False
        return self.probe_result == "passed" or self.probe_status == "passed"


__all__ = [
    "DEFAULT_GENERATION_MAX_INPUT_TOKENS",
    "EMBEDDING_PROFILE_DIGEST_ALGORITHM",
    "EMBEDDING_PROFILE_DIGEST_SCHEMA_VERSION",
    "GENERATION_PROFILE_DIGEST_ALGORITHM",
    "GENERATION_PROFILE_DIGEST_SCHEMA_VERSION",
    "EmbeddingProfileIdentity",
    "EmbeddingProfileReadiness",
    "InferenceProfile",
    "ProbeStatus",
    "ProviderCapabilities",
    "ProviderKind",
    "StructuredOutputMode",
    "StructuredOutputPreference",
    "TokenParameter",
    "embedding_profile_fingerprint",
    "generation_profile_fingerprint",
]
