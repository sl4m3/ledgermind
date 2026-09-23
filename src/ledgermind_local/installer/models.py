"""Typed installer configuration and result-facing models."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .provider_profiles import (
    GenerationProviderProfileId,
    infer_generation_provider_profile,
)

_OPENAI_OPERATION_SUFFIXES = ("/chat/completions", "/embeddings")


def _text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _http_url(value: str, field_name: str = "endpoint") -> str:
    normalized = _text(value, field_name).rstrip("/")
    # People commonly paste the operation URL shown in provider examples.
    # Profiles store the API base because the runtime appends the operation.
    for suffix in _OPENAI_OPERATION_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL")
    return normalized


def _language_tag(value: str) -> str:
    """Validate and canonicalize one deployment-owned BCP-47-like tag."""

    raw = _text(value, "semantic_language").replace("_", "-")
    subtags = raw.split("-")
    primary = subtags[0]
    if not (2 <= len(primary) <= 8) or not primary.isascii() or not primary.isalpha():
        raise ValueError(
            "semantic_language must be a valid language tag such as en, pt, or zh-Hans"
        )
    if any(
        not subtag or len(subtag) > 8 or not subtag.isascii() or not subtag.isalnum()
        for subtag in subtags[1:]
    ):
        raise ValueError(
            "semantic_language must be a valid language tag such as en, pt, or zh-Hans"
        )
    canonical = [primary.lower()]
    for subtag in subtags[1:]:
        if len(subtag) == 2 and subtag.isalpha():
            canonical.append(subtag.upper())
        elif len(subtag) == 4 and subtag.isalpha():
            canonical.append(subtag[0].upper() + subtag[1:].lower())
        else:
            canonical.append(subtag.lower())
    return "-".join(canonical)


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    provider_profile: GenerationProviderProfileId = "openai_compatible"
    # Optional provider route used by aggregators such as OpenRouter.  It is
    # part of the generation identity and is therefore applied to probes and
    # persisted inference profiles alike.
    route: str | None = None
    # Explicit, ordered OpenRouter fallbacks.  Keeping this list separate from
    # the primary route lets us restrict routing to reviewed providers instead
    # of allowing OpenRouter to select an arbitrary (and possibly expensive)
    # endpoint.
    fallback_routes: tuple[str, ...] = ()
    token: str | None = None
    token_env: str | None = None
    token_stdin: bool = False
    secret_ref: str | None = None
    model: str
    operational_model: str | None = None
    # Object Resolution is a separate production role.  It is optional only
    # at parse time so legacy installer payloads can be diagnosed explicitly;
    # profile materialization refuses to invent an operational fallback.
    object_resolution_model: str | None = None
    background_model: str | None = None
    timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    max_concurrency: int = Field(default=2, ge=1, le=64)
    structured_json_support: bool = True

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_provider_profile(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "provider_profile" in value:
            return value
        payload = dict(value)
        endpoint = payload.get("endpoint")
        if isinstance(endpoint, str):
            payload["provider_profile"] = infer_generation_provider_profile(endpoint)
        return payload

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        return _http_url(value)

    @field_validator(
        "model", "operational_model", "object_resolution_model", "background_model"
    )
    @classmethod
    def validate_models(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _text(value, getattr(info, "field_name", "model"))

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str | None) -> str | None:
        if value is None:
            return None
        route = _text(value, "route")
        if any(character.isspace() for character in route):
            raise ValueError("route must not contain whitespace")
        return route

    @field_validator("fallback_routes")
    @classmethod
    def validate_fallback_routes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_text(item, "fallback_routes") for item in value)
        if len(normalized) > 1:
            raise ValueError("at most one fallback route is supported")
        if any(any(character.isspace() for character in item) for item in normalized):
            raise ValueError("fallback routes must not contain whitespace")
        if len(normalized) != len(set(normalized)):
            raise ValueError("fallback routes must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_route_endpoint(self) -> GenerationConfig:
        if (
            self.route or self.fallback_routes
        ) and self.provider_profile != "openrouter":
            raise ValueError("generation routes are supported only for OpenRouter")
        if self.fallback_routes and not self.route:
            raise ValueError("generation fallback routes require a primary route")
        if self.route and self.route in self.fallback_routes:
            raise ValueError(
                "primary generation route must not be repeated as a fallback"
            )
        if (
            self.provider_profile == "openrouter"
            and "openrouter.ai" not in self.endpoint.lower()
        ):
            raise ValueError(
                "OpenRouter provider profile requires an OpenRouter endpoint"
            )
        if self.provider_profile == "openrouter" and not self.route:
            raise ValueError(
                "OpenRouter requires one explicit provider route; automatic routing is disabled"
            )
        return self

    @model_validator(mode="after")
    def validate_single_semantic_model(self) -> GenerationConfig:
        for field_name in (
            "operational_model",
            "object_resolution_model",
            "background_model",
        ):
            legacy_value = getattr(self, field_name)
            if legacy_value is not None and legacy_value != self.model:
                raise ValueError(
                    f"generation.{field_name} must match generation.model; "
                    "LedgerMind uses one model for the complete knowledge pipeline"
                )
        return self

    @model_validator(mode="after")
    def validate_secret_source(self) -> GenerationConfig:
        if not (self.token or self.token_env or self.token_stdin or self.secret_ref):
            raise ValueError(
                "generation requires token, token_env, token_stdin, or secret_ref"
            )
        if self.token and self.token_env:
            raise ValueError("generation token and token_env are mutually exclusive")
        return self


class EmbeddingApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    token: str | None = None
    token_env: str | None = None
    token_stdin: bool = False
    secret_ref: str | None = None
    model: str
    dimensions: int = Field(gt=0)
    batch_size: int = Field(default=32, ge=1, le=4096)
    concurrency: int = Field(default=1, ge=1, le=64)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        return _http_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return _text(value, "model")

    @model_validator(mode="after")
    def validate_secret_source(self) -> EmbeddingApiConfig:
        if not (self.token or self.token_env or self.token_stdin or self.secret_ref):
            raise ValueError(
                "embedding API requires token, token_env, token_stdin, or secret_ref"
            )
        if self.token and self.token_env:
            raise ValueError("embedding token and token_env are mutually exclusive")
        return self


class LocalEmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str
    device: Literal["auto", "cpu", "cuda", "rocm"] = "auto"
    model_storage_path: str | None = None
    model_path: str | None = None
    runtime_id: str | None = None
    runtime_path: str | None = None
    dimensions: int = Field(default=2048, gt=0)
    batch_size: int = Field(default=32, ge=1, le=4096)
    concurrency: int = Field(default=1, ge=1, le=64)
    threads: int = Field(default=0, ge=0, le=512)
    gpu_allocation: str = "balanced"
    auto_start: bool = True

    @field_validator("catalog_id", "gpu_allocation")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        return _text(value, getattr(info, "field_name", "value"))

    @field_validator("runtime_id", "runtime_path")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _text(value, getattr(info, "field_name", "value"))


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["api", "local"]
    api: EmbeddingApiConfig | None = None
    local: LocalEmbeddingConfig | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> EmbeddingConfig:
        if self.mode == "api" and self.api is None:
            raise ValueError("embedding.api is required in API mode")
        if self.mode == "local" and self.local is None:
            raise ValueError("embedding.local is required in local mode")
        if self.mode == "api" and self.local is not None:
            raise ValueError("embedding.local is not allowed in API mode")
        if self.mode == "local" and self.api is not None:
            raise ValueError("embedding.api is not allowed in local mode")
        return self


class RerankerApiConfig(BaseModel):
    """One Cohere-compatible HTTP reranking endpoint."""

    model_config = ConfigDict(extra="forbid")
    endpoint: str
    token: str | None = None
    token_env: str | None = None
    secret_ref: str | None = None
    model: str
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        # Unlike generation and embeddings this is an operation URL: vendors
        # expose either /rerank or /ranking and neither may be inferred safely.
        normalized = _text(value, "endpoint").rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint must be an absolute http(s) URL")
        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return _text(value, "model")


class RerankerLocalConfig(BaseModel):
    """Separately downloaded, signed Qwen reranker runtime."""

    model_config = ConfigDict(extra="forbid")
    model_path: str
    runtime_path: str
    device: Literal["cpu", "cuda", "rocm"] = "cpu"

    @field_validator("model_path", "runtime_path")
    @classmethod
    def validate_paths(cls, value: str, info: object) -> str:
        return _text(value, getattr(info, "field_name", "path"))


class RerankerConfig(BaseModel):
    """Retrieval reranker: disabled, remote API, or local CPU/GPU."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["disabled", "api", "local"] = "disabled"
    api: RerankerApiConfig | None = None
    local: RerankerLocalConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_local_only_config(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "enabled" not in value:
            return value
        legacy = dict(value)
        enabled = bool(legacy.pop("enabled", False))
        if not enabled:
            return {"mode": "disabled"}
        return {
            "mode": "local",
            "local": {
                "model_path": legacy.pop("model_path", None),
                "runtime_path": legacy.pop("runtime_path", None),
                "device": legacy.pop("device", "cpu"),
            },
        }

    @model_validator(mode="after")
    def validate_mode(self) -> RerankerConfig:
        if self.mode == "api" and self.api is None:
            raise ValueError("reranker.api is required in API mode")
        if self.mode == "local" and self.local is None:
            raise ValueError("reranker.local is required in local mode")
        if self.mode != "api" and self.api is not None:
            raise ValueError("reranker.api is allowed only in API mode")
        if self.mode != "local" and self.local is not None:
            raise ValueError("reranker.local is allowed only in local mode")
        return self

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def model_path(self) -> str | None:
        return self.local.model_path if self.local is not None else None

    @property
    def runtime_path(self) -> str | None:
        return self.local.runtime_path if self.local is not None else None

    @property
    def device(self) -> Literal["cpu", "cuda", "rocm"]:
        return self.local.device if self.local is not None else "cpu"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    residency_mode: Literal["session", "idle", "always_on"] = "session"
    idle_timeout_seconds: float = Field(default=900.0, ge=0, le=86_400)
    session_safety_ttl_seconds: float = Field(default=3_600.0, gt=0, le=86_400)
    lease_ttl_seconds: float = Field(default=30.0, gt=0, le=3_600)
    heartbeat_seconds: float = Field(default=10.0, gt=0, le=1_200)

    @model_validator(mode="before")
    @classmethod
    def migrate_idle_shutdown(cls, value: Any) -> Any:
        """Preserve the exact lifecycle of pre-residency installer configs."""

        if not isinstance(value, dict) or "idle_shutdown_seconds" not in value:
            return value
        payload = dict(value)
        legacy = payload.pop("idle_shutdown_seconds")
        payload.setdefault("residency_mode", "idle")
        payload.setdefault("idle_timeout_seconds", legacy)
        return payload

    @model_validator(mode="after")
    def validate_heartbeat(self) -> RuntimeConfig:
        if self.heartbeat_seconds >= self.lease_ttl_seconds:
            raise ValueError("heartbeat_seconds must be less than lease_ttl_seconds")
        if self.session_safety_ttl_seconds < self.lease_ttl_seconds:
            raise ValueError(
                "session_safety_ttl_seconds must not be less than lease_ttl_seconds"
            )
        return self

    @property
    def idle_shutdown_seconds(self) -> float:
        """Compatibility view for runtime callers during the format transition."""

        return self.idle_timeout_seconds


class AdvancedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_max_input: int | None = Field(default=None, gt=0)
    generation_max_output: int | None = Field(default=None, gt=0)
    embedding_max_text_length: int | None = Field(default=None, gt=0)
    retry_attempts: int = Field(default=5, ge=0, le=10)
    allow_custom_model: bool = False
    custom_model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    custom_runtime_compatibility: str | None = None


class IntegrationConfig(BaseModel):
    """One explicitly selected agent integration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["hermes", "codex", "claude-code", "cursor", "opencode", "openclaw"]
    enabled: bool = True


class InstallerConfig(BaseModel):
    """The single schema shared by the wizard and agent-driven installs."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    integrations: tuple[IntegrationConfig, ...] = ()
    # Installation must make the semantic language an explicit deployment
    # choice; it is never inferred from user text or the host locale.
    semantic_language: str
    # Agents may either share one logical knowledge space or keep independent
    # spaces while still using the same Local/Core runtime.
    memory_mode: Literal["shared", "per_agent"] = "per_agent"
    memory_data_path: str | None = None
    generation: GenerationConfig
    embedding: EmbeddingConfig
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)

    @field_validator("semantic_language")
    @classmethod
    def validate_semantic_language(cls, value: str) -> str:
        return _language_tag(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_config(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("schema_version") == 1 or "target" in payload:
            target = payload.pop("target", "hermes")
            payload["schema_version"] = 2
            payload.setdefault("integrations", [{"id": target, "enabled": True}])
        return payload

    @model_validator(mode="after")
    def validate_integrations(self) -> InstallerConfig:
        identifiers = [item.id for item in self.integrations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("integrations must contain unique ids")
        return self

    def memory_space_id_for(self, target_id: str) -> str:
        """Return the logical memory space injected into an agent adapter."""

        if self.memory_mode == "shared":
            return "shared-default"
        return f"{target_id}-default"

    @field_validator("memory_data_path")
    @classmethod
    def validate_memory_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _text(value, "memory_data_path")

    @model_validator(mode="after")
    def validate_custom_local_model(self) -> InstallerConfig:
        local = self.embedding.local
        if local is None or local.model_path is None:
            return self
        if not self.advanced.allow_custom_model:
            raise ValueError(
                "local model_path is available only in explicit advanced mode"
            )
        if not self.advanced.custom_model_sha256:
            raise ValueError("advanced custom model requires custom_model_sha256")
        if not self.advanced.custom_runtime_compatibility:
            raise ValueError(
                "advanced custom model requires runtime compatibility metadata"
            )
        return self


class ProfileBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    slot: Literal["operational", "background", "embedding"]
    model: str
    endpoint: str


__all__ = [
    "AdvancedConfig",
    "EmbeddingApiConfig",
    "EmbeddingConfig",
    "GenerationConfig",
    "InstallerConfig",
    "IntegrationConfig",
    "LocalEmbeddingConfig",
    "ProfileBinding",
    "RerankerApiConfig",
    "RerankerConfig",
    "RerankerLocalConfig",
    "RuntimeConfig",
]
