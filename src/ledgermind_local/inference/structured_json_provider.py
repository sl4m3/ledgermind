"""Structured generation over Local-owned profiles and capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .cancellation import CancellationToken
from .profile_slots import ProfileResolver, ProfileSlot
from .profiles import (
    InferenceProfile,
    ProviderCapabilities,
    StructuredOutputMode,
    generation_profile_fingerprint,
)
from .provider_telemetry import operation_context
from .providers.base import (
    ChatMessage,
    InferenceProvider,
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    normalize_error,
    normalize_usage,
)
from .providers.google_boundary import GoogleGenerationTransport
from .providers.openai_compatible import (
    DEFAULT_TOOL_NAME,
    OpenAICompatibleProvider,
    decode_json_content,
)
from .secrets import SecretNotFoundError, SecretStore
from .strict import (
    STRICT_JSON_SCHEMA_MODE,
    validate_strict_requirement,
)
from .token_budget import (
    InputBudgetExceededError,
    OutputBudgetExceededError,
    TokenBudgetEstimator,
)

ProviderFactory = Callable[[InferenceProfile, str], InferenceProvider]
_MODE_ORDER: tuple[StructuredOutputMode, ...] = (
    STRICT_JSON_SCHEMA_MODE,
    "json_schema",
    "tool_call",
    "json_object",
    "prompt_only",
)


def _forced_fallback_profile(
    profile: InferenceProfile,
) -> tuple[InferenceProfile, str | None]:
    """Pin one retry to the next configured provider route, when available.

    Aggregators normally advance their route chain only for transport errors.
    A schema-invalid HTTP 200 is therefore retried with the primary provider
    unless Local narrows the already configured chain for the bounded retry.
    This helper changes transport routing only; model, schema, prompts, and all
    semantic inputs remain identical.
    """

    extra_body = dict(profile.extra_body)
    provider_options = extra_body.get("provider")
    if not isinstance(provider_options, Mapping):
        return profile, None
    order_value = provider_options.get("order")
    if not isinstance(order_value, (list, tuple)):
        return profile, None
    routes = tuple(
        route.strip()
        for route in order_value
        if isinstance(route, str) and route.strip()
    )
    if len(routes) < 2:
        return profile, None

    fallback_routes = list(routes[1:])
    narrowed_options = dict(provider_options)
    narrowed_options["order"] = fallback_routes
    narrowed_options["only"] = fallback_routes
    narrowed_options["allow_fallbacks"] = len(fallback_routes) > 1
    extra_body["provider"] = narrowed_options
    return (
        profile.model_copy(update={"extra_body": extra_body}),
        fallback_routes[0],
    )


class CapabilityStore(Protocol):
    def get_capabilities(self, profile_id: str) -> ProviderCapabilities | None: ...


def default_provider_factory(
    profile: InferenceProfile, secret: str
) -> InferenceProvider:
    """Construct the default generative provider for a resolved profile."""

    if profile.provider_kind == "google_genai":
        del secret
        return GoogleGenerationTransport()
    if profile.provider_kind in {"openai_compatible", "nvidia_nim"}:
        return OpenAICompatibleProvider(
            base_url=profile.base_url,
            api_key=secret,
            timeout_seconds=profile.timeout_seconds,
            max_retries=profile.max_retries,
            token_parameter=profile.token_parameter,
            supports_system_role=profile.supports_system_role,
            supports_seed=profile.supports_seed,
            extra_body=profile.extra_body,
            strict_transport=(
                "nvidia_guided_json" if profile.provider_kind == "nvidia_nim" else None
            ),
            profile_fingerprint=generation_profile_fingerprint(profile),
        )
    raise ProviderConfigurationError("unsupported inference provider kind")


class StructuredJsonResult(BaseModel):
    """Parsed JSON object plus selected transport mode and safe metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    data: dict[str, object]
    raw_text: str = ""
    profile_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    attempts: int = Field(ge=1)
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
    status_code: int = Field(ge=100, le=599)
    structured_output_mode: StructuredOutputMode = Field(
        default="json_object",
        validation_alias=AliasChoices("structured_output_mode", "mode"),
    )
    contract_digest: str | None = Field(default=None, max_length=200)
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, object] = Field(default_factory=dict)
    token_usage: dict[str, object] | None = None
    normalized_usage: dict[str, object] = Field(default_factory=dict)

    @property
    def mode(self) -> StructuredOutputMode:
        return self.structured_output_mode

    @property
    def selected_mode(self) -> StructuredOutputMode:
        return self.structured_output_mode

    @property
    def provider_metadata(self) -> dict[str, object]:
        return self.metadata

    @property
    def raw_model_text(self) -> str:
        return self.raw_text

    @property
    def parsed_json(self) -> dict[str, object]:
        """Canonical name for the parseable payload sent to Core."""

        return self.data

    @property
    def usage(self) -> dict[str, object] | None:
        """Provider usage under the normalized response vocabulary."""

        return self.token_usage

    @property
    def provider_request_id(self) -> str | None:
        value = self.metadata.get(
            "provider_request_id", self.metadata.get("request_id")
        )
        return value if isinstance(value, str) and value else None

    @property
    def finish_reason(self) -> str | None:
        value = self.metadata.get("finish_reason")
        return value if isinstance(value, str) and value else None

    @property
    def transport_error(self) -> object | None:
        """Successful normalized responses carry an explicit null error."""

        return self.metadata.get("transport_error")

    @property
    def native_schema_issues(self) -> list[dict[str, object]]:
        value = self.metadata.get("local_validation_issues")
        return value if isinstance(value, list) else []

    @property
    def native_schema_valid(self) -> bool:
        return not self.native_schema_issues


class StructuredJsonError(RuntimeError):
    """Base structured generation failure with a safe code."""

    code = "structured_json_error"


class StructuredJsonRequestError(StructuredJsonError):
    code = "invalid_request"


class StructuredJsonCapabilityError(StructuredJsonError):
    """The configured strict transport has not passed its current probe."""

    code = "provider_capability_unverified"


class StructuredJsonSecretError(StructuredJsonError):
    code = "secret_missing"


class StructuredJsonResponseError(StructuredJsonError):
    code = "invalid_json_response"


class StructuredJsonSchemaError(StructuredJsonError):
    """A parseable strict response that violates the requested JSON Schema."""

    code = "schema_shape_failure"


class StructuredJsonProvider:
    """Select a technical provider mode and return a Core-facing JSON object.

    This class checks only transport shape (object, JSON, size, and capability
    metadata).  It never assigns or interprets operation, facet, resolution, or
    value semantics.
    """

    def __init__(
        self,
        *,
        profile_resolver: ProfileResolver,
        secret_store: SecretStore,
        provider_factory: ProviderFactory | None = None,
        capability_store: CapabilityStore | None = None,
        capabilities_store: CapabilityStore | None = None,
        max_output_bytes: int = 2_000_000,
        token_budget_estimator: TokenBudgetEstimator | None = None,
    ) -> None:
        if max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")
        if capability_store is not None and capabilities_store is not None:
            raise ValueError("provide only one capability store")
        self._profile_resolver = profile_resolver
        self._secret_store = secret_store
        self._provider_factory = provider_factory or default_provider_factory
        self._capability_store = capability_store or capabilities_store
        self.max_output_bytes = max_output_bytes
        self._token_budget_estimator = token_budget_estimator or TokenBudgetEstimator()

    def generate_json(
        self,
        *,
        memory_space_id: str,
        messages: Sequence[ChatMessage],
        max_output_tokens: int,
        profile_slot: ProfileSlot,
        response_format: Mapping[str, object] | None = None,
        output_contract: Mapping[str, object] | None = None,
        structured_output_requirement: Mapping[str, object] | None = None,
        mode: StructuredOutputMode | None = None,
        structured_output_mode: StructuredOutputMode | None = None,
        tool_name: str | None = None,
        metadata: Mapping[str, object] | None = None,
        telemetry_operation: str | None = None,
        telemetry_context: Mapping[str, object] | None = None,
        seed: int | None = None,
        force_provider_fallback: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> StructuredJsonResult:
        profile = self._profile_resolver.resolve_profile(memory_space_id, profile_slot)
        if max_output_tokens > profile.max_output_tokens:
            error = OutputBudgetExceededError(
                max_output_tokens,
                profile.max_output_tokens,
            )
            error.profile_id = profile.profile_id
            raise error
        contract, requested_mode = self._normalize_contract_and_mode(
            response_format=response_format,
            output_contract=output_contract,
            mode=mode,
            structured_output_mode=structured_output_mode,
        )
        if (
            structured_output_requirement is not None
            or requested_mode == STRICT_JSON_SCHEMA_MODE
        ):
            if requested_mode not in {None, "auto", STRICT_JSON_SCHEMA_MODE}:
                raise StructuredJsonRequestError(
                    "strict structured output cannot be combined with a legacy mode"
                )
            try:
                structured_output_requirement = validate_strict_requirement(
                    structured_output_requirement,
                    contract,
                )
            except (TypeError, ValueError) as exc:
                raise StructuredJsonRequestError(
                    "strict structured output requirement is invalid"
                ) from exc
            requested_mode = STRICT_JSON_SCHEMA_MODE
        selected_mode = self._select_mode(
            profile,
            requested_mode=requested_mode,
            response_format=response_format,
        )
        request = self._build_request(
            profile=profile,
            messages=messages,
            max_output_tokens=max_output_tokens,
            output_contract=contract,
            structured_output_requirement=structured_output_requirement,
            mode=selected_mode,
            tool_name=tool_name,
            metadata=metadata,
            seed=seed,
        )
        # This is deliberately before secret lookup/provider construction and
        # therefore before any possible HTTP call.
        try:
            self._token_budget_estimator.ensure_within(
                request, profile.max_input_tokens
            )
        except InputBudgetExceededError as exc:
            exc.profile_id = profile.profile_id
            raise
        try:
            secret = self._secret_store.get(profile.secret_ref)
        except SecretNotFoundError as exc:
            raise StructuredJsonSecretError(
                "configured provider secret is not present"
            ) from exc

        capabilities = self._load_capabilities(
            profile, structured_output_override=requested_mode
        )
        strict_request = (
            requested_mode == STRICT_JSON_SCHEMA_MODE
            or structured_output_requirement is not None
        )
        if strict_request and (
            capabilities is None
            or not capabilities.is_fresh(
                profile_fingerprint=generation_profile_fingerprint(
                    profile, structured_output_override=requested_mode
                )
            )
            or not capabilities.supports(STRICT_JSON_SCHEMA_MODE)
        ):
            raise StructuredJsonCapabilityError(
                "strict provider/model capability has not been verified by a successful probe"
            )
        transport_profile, forced_route = (
            _forced_fallback_profile(profile)
            if force_provider_fallback
            else (profile, None)
        )
        provider = self._provider_factory(transport_profile, secret)
        fallback_metadata: dict[str, object] = {}

        internal_metadata = dict(telemetry_context or {})
        task_id = internal_metadata.get("_ledgermind_task_id") or internal_metadata.get(
            "task_id"
        )
        root_task_id = internal_metadata.get(
            "_ledgermind_root_task_id"
        ) or internal_metadata.get("root_task_id")
        attempt_index = internal_metadata.get(
            "_ledgermind_attempt_index"
        ) or internal_metadata.get("attempt_index")
        request_reason = internal_metadata.get(
            "_ledgermind_request_reason"
        ) or internal_metadata.get("request_reason", "primary")
        attempt_kind = internal_metadata.get(
            "_ledgermind_attempt_kind"
        ) or internal_metadata.get("attempt_kind")

        def execute_and_parse(
            current_request: ModelRequest,
            current_mode: StructuredOutputMode,
            *,
            reason: str,
            fallback_from: StructuredOutputMode | None = None,
            fallback_to: StructuredOutputMode | None = None,
        ) -> StructuredJsonResult:
            with operation_context(
                telemetry_operation,
                task_id=task_id,
                root_task_id=root_task_id,
                attempt_index=attempt_index,
                request_reason=reason,
                structured_output_mode=current_mode,
                fallback_from=fallback_from,
                fallback_to=fallback_to,
                attempt_kind=attempt_kind,
            ):
                execute = getattr(provider, "execute_structured", None)
                if callable(execute):
                    response = execute(
                        current_request,
                        profile,
                        capabilities,
                        cancellation_token=cancellation_token,
                    )
                else:
                    response = provider.complete_json(
                        current_request, cancellation_token=cancellation_token
                    )
            return self._to_result(
                profile,
                response,
                output_contract=contract,
                selected_mode=current_mode,
                tool_name=tool_name,
            )

        try:
            try:
                result = execute_and_parse(
                    request,
                    selected_mode,
                    reason=str(request_reason),
                )
            except Exception as exc:
                if not isinstance(
                    exc, (ProviderResponseError, StructuredJsonResponseError)
                ):
                    raise
                fallback_mode = self._automatic_fallback_mode(
                    profile,
                    requested_mode=requested_mode,
                    response_format=response_format,
                    selected_mode=selected_mode,
                )
                if fallback_mode is None:
                    self._invalidate_capability_after_failure(
                        profile,
                        selected_mode=selected_mode,
                        error=exc,
                    )
                    raise
                fallback_request = self._build_request(
                    profile=profile,
                    messages=messages,
                    max_output_tokens=max_output_tokens,
                    output_contract=contract,
                    structured_output_requirement=structured_output_requirement,
                    mode=fallback_mode,
                    tool_name=tool_name,
                    metadata=metadata,
                    seed=seed,
                )
                # Prompt-only fallback appends a short instruction to the
                # final message, so enforce the same input budget before the
                # bounded second provider call.
                try:
                    self._token_budget_estimator.ensure_within(
                        fallback_request, profile.max_input_tokens
                    )
                except InputBudgetExceededError as budget_error:
                    budget_error.profile_id = profile.profile_id
                    self._invalidate_capability_after_failure(
                        profile,
                        selected_mode=selected_mode,
                        error=exc,
                    )
                    raise
                fallback_metadata = {
                    "structured_output_fallback": True,
                    "structured_output_fallback_from": selected_mode,
                    "structured_output_fallback_to": fallback_mode,
                    "structured_output_fallback_error_code": normalize_error(exc)[
                        "code"
                    ],
                }
                try:
                    result = execute_and_parse(
                        fallback_request,
                        fallback_mode,
                        reason="structured_mode_fallback",
                        fallback_from=selected_mode,
                        fallback_to=fallback_mode,
                    )
                except Exception as fallback_error:
                    self._invalidate_capability_after_failure(
                        profile,
                        selected_mode=selected_mode,
                        error=exc,
                    )
                    self._invalidate_capability_after_failure(
                        profile,
                        selected_mode=fallback_mode,
                        error=fallback_error,
                    )
                    raise
                self._record_capability_fallback(
                    profile,
                    failed_mode=selected_mode,
                    successful_mode=fallback_mode,
                    error_code=normalize_error(exc)["code"],
                )
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()
        if fallback_metadata:
            result = result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        **fallback_metadata,
                    }
                }
            )
        if forced_route is not None:
            result = result.model_copy(
                update={
                    "metadata": {
                        **result.metadata,
                        "forced_provider_fallback": True,
                        "forced_provider_route": forced_route,
                    }
                }
            )
        if strict_request and not result.native_schema_valid:
            raise StructuredJsonSchemaError(
                "provider response violates the requested strict JSON Schema"
            )
        return result

    def _record_capability_fallback(
        self,
        profile: InferenceProfile,
        *,
        failed_mode: StructuredOutputMode,
        successful_mode: StructuredOutputMode,
        error_code: str,
    ) -> None:
        """Retain a fresh cache after a successful bounded fallback."""

        stores: list[object] = []
        if self._capability_store is not None:
            stores.append(self._capability_store)
        resolver_store = getattr(self._profile_resolver, "profile_store", None)
        if resolver_store is not None:
            stores.append(resolver_store)
        for store in stores:
            recorder = getattr(store, "record_capability_fallback", None)
            if callable(recorder):
                recorder(
                    profile.profile_id,
                    failed_mode=failed_mode,
                    successful_mode=successful_mode,
                    error_code=error_code,
                )
                return

    @staticmethod
    def _automatic_fallback_mode(
        profile: InferenceProfile,
        *,
        requested_mode: StructuredOutputMode | None,
        response_format: Mapping[str, object] | None,
        selected_mode: StructuredOutputMode,
    ) -> StructuredOutputMode | None:
        """Return one bounded transport fallback for an automatic choice.

        Capability probes are intentionally small.  A weak or reasoning-heavy
        model can pass a tiny tool-call probe and then emit ordinary JSON for
        the production contract.  When Local selected the mode automatically,
        one retry in a less specialized JSON transport keeps the Core task
        contract intact without turning semantic failures into open-ended
        retries.  Explicit operator choices remain fail-closed.
        """

        if response_format is not None:
            return None
        if requested_mode not in (None, "auto"):
            return None
        if profile.structured_output_preference != "auto":
            return None
        if selected_mode in {"json_schema", "tool_call"}:
            return "json_object"
        if selected_mode == "json_object":
            return "prompt_only"
        return None

    def _normalize_contract_and_mode(
        self,
        *,
        response_format: Mapping[str, object] | None,
        output_contract: Mapping[str, object] | None,
        mode: StructuredOutputMode | None,
        structured_output_mode: StructuredOutputMode | None,
    ) -> tuple[dict[str, object] | None, StructuredOutputMode | None]:
        if (
            mode is not None
            and structured_output_mode is not None
            and mode != structured_output_mode
        ):
            raise StructuredJsonRequestError("conflicting structured output modes")
        selected_request_mode = mode or structured_output_mode
        contract = dict(output_contract) if output_contract is not None else None
        if response_format is not None:
            format_type = response_format.get("type")
            if format_type == "json_object":
                # Explicit legacy response_format always wins over profile
                # auto/manual defaults, preserving the old API behavior.
                selected_request_mode = "json_object"
            elif format_type == "json_schema":
                selected_request_mode = "json_schema"
                schema_contract = response_format.get("json_schema")
                if isinstance(schema_contract, dict):
                    if isinstance(schema_contract.get("schema"), dict):
                        contract = {
                            "contract_name": schema_contract.get(
                                "name", "structured_result"
                            ),
                            "json_schema": dict(schema_contract["schema"]),
                        }
                    else:
                        contract = dict(schema_contract)
            else:
                raise StructuredJsonRequestError(
                    "response_format must be json_object or json_schema"
                )
        return contract, selected_request_mode

    def _load_capabilities(
        self,
        profile: InferenceProfile,
        *,
        structured_output_override: StructuredOutputMode | None = None,
    ) -> ProviderCapabilities | None:
        fingerprint = generation_profile_fingerprint(
            profile, structured_output_override=structured_output_override
        )
        stores: list[object] = []
        if self._capability_store is not None:
            stores.append(self._capability_store)
        resolver_store = getattr(self._profile_resolver, "profile_store", None)
        if resolver_store is not None:
            stores.append(resolver_store)
        for store in stores:
            profile_getter = getattr(store, "get_capabilities_for_profile", None)
            if callable(profile_getter):
                result = profile_getter(profile, fresh_only=True)
                if isinstance(result, ProviderCapabilities):
                    from .provider_telemetry import record_counter

                    record_counter(
                        "capability_cache_hits",
                        operation="capability_cache",
                        provider_profile_fingerprint=fingerprint,
                        model=profile.model,
                    )
                    return result
            getter = getattr(store, "get_capabilities", None)
            if callable(getter):
                result = getter(profile.profile_id)
                if isinstance(result, ProviderCapabilities):
                    if result.profile_fingerprint and not result.is_fresh(
                        profile_fingerprint=fingerprint
                    ):
                        continue
                    from .provider_telemetry import record_counter

                    record_counter(
                        "capability_cache_hits",
                        operation="capability_cache",
                        provider_profile_fingerprint=fingerprint,
                        model=profile.model,
                    )
                    return result
        database_path = getattr(self._profile_resolver, "database_path", None)
        if database_path is not None:
            from .profile_store import DatabaseBackedCapabilityStore

            store = DatabaseBackedCapabilityStore(str(database_path))
            getter = getattr(store, "get_capabilities_for_profile", None)
            if callable(getter):
                return getter(profile, fresh_only=True)
            return store.get_capabilities(profile.profile_id)
        return None

    def _invalidate_capability_after_failure(
        self,
        profile: InferenceProfile,
        *,
        selected_mode: StructuredOutputMode,
        error: BaseException,
    ) -> None:
        """Keep probe-owned capability stable across individual executions.

        A malformed or incomplete completion is evidence about that request,
        not about the endpoint's general structured-output capability.  The
        worker owns one bounded fresh retry; invalidating here would make that
        retry fail its local capability preflight before reaching the provider.
        Capability changes remain the responsibility of an explicit probe (or
        a successful automatic-mode fallback), where compatibility is tested
        deliberately rather than inferred from one completion.
        """

        del profile, selected_mode, error

    def _select_mode(
        self,
        profile: InferenceProfile,
        *,
        requested_mode: StructuredOutputMode | None,
        response_format: Mapping[str, object] | None,
    ) -> StructuredOutputMode:
        if response_format is not None and response_format.get("type") == "json_object":
            return "json_object"
        candidate = requested_mode or profile.structured_output_preference
        capabilities = self._load_capabilities(profile)
        if candidate != "auto":
            # A non-auto preference is an explicit operator choice.  It is
            # sent as requested; an endpoint rejection remains observable as
            # a provider error rather than being silently changed to another
            # mode.
            return candidate
        if capabilities is not None:
            for mode in _MODE_ORDER:
                if capabilities.supports(mode):
                    return mode
            if capabilities.probe_status == "passed":
                raise StructuredJsonRequestError(
                    "provider has no persisted structured output capability"
                )
        # A profile created before capability probing must retain the old
        # json_object behavior until a probe records a better mode.
        return "json_object"

    def _build_request(
        self,
        *,
        profile: InferenceProfile,
        messages: Sequence[ChatMessage],
        max_output_tokens: int,
        output_contract: dict[str, object] | None,
        structured_output_requirement: Mapping[str, object] | None,
        mode: StructuredOutputMode,
        tool_name: str | None,
        metadata: Mapping[str, object] | None,
        seed: int | None,
    ) -> ModelRequest:
        if not messages:
            raise StructuredJsonRequestError("messages must not be empty")
        if mode in {"strict_json_schema", "json_schema"} and (
            not isinstance(output_contract, dict)
            or not isinstance(output_contract.get("json_schema"), dict)
        ):
            raise StructuredJsonRequestError(
                "json_schema mode requires an output contract schema"
            )
        try:
            return ModelRequest(
                model=profile.model,
                messages=tuple(messages),
                max_output_tokens=max_output_tokens,
                output_contract=output_contract,
                structured_output_requirement=(
                    dict(structured_output_requirement)
                    if isinstance(structured_output_requirement, Mapping)
                    else None
                ),
                mode=mode,
                tool_name=tool_name,
                metadata=dict(metadata or {}),
                token_parameter=profile.token_parameter,
                supports_system_role=profile.supports_system_role,
                supports_seed=profile.supports_seed,
                seed=seed,
            )
        except ValueError as exc:
            raise StructuredJsonRequestError("model request is invalid") from exc

    def _to_result(
        self,
        profile: InferenceProfile,
        response: ModelResponse,
        *,
        output_contract: dict[str, object] | None,
        selected_mode: StructuredOutputMode,
        tool_name: str | None,
    ) -> StructuredJsonResult:
        if response.response_bytes > self.max_output_bytes:
            raise StructuredJsonResponseError("provider response exceeds size limit")
        try:
            parsed = decode_json_content(response.content)
        except Exception as exc:
            if isinstance(exc, StructuredJsonResponseError):
                raise
            raise StructuredJsonResponseError(
                "provider response is not valid JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise StructuredJsonResponseError("provider response must be a JSON object")
        metadata_value = dict(response.metadata)
        token_usage = metadata_value.get("usage")
        normalized_usage = normalize_usage(response)
        metadata_value["normalized_usage"] = normalized_usage
        metadata_value["parsed_json"] = parsed
        metadata_value["raw_text"] = response.raw_text or response.content
        provider_request_id = metadata_value.get("request_id")
        if isinstance(provider_request_id, str) and provider_request_id:
            metadata_value["provider_request_id"] = provider_request_id
        finish_reason = metadata_value.get("finish_reason")
        if not isinstance(finish_reason, str):
            metadata_value["finish_reason"] = None
        metadata_value["transport_error"] = None
        metadata_value["local_validation_issues"] = _advisory_schema_issues(
            parsed,
            output_contract.get("json_schema")
            if isinstance(output_contract, Mapping)
            else None,
        )
        return StructuredJsonResult(
            data=parsed,
            raw_text=response.raw_text or response.content,
            profile_id=profile.profile_id,
            provider=profile.provider_kind,
            model=response.model,
            attempts=response.attempts,
            request_bytes=response.request_bytes,
            response_bytes=response.response_bytes,
            status_code=response.status_code,
            structured_output_mode=selected_mode,
            contract_digest=_contract_digest(output_contract),
            tool_name=(
                tool_name
                or response.tool_name
                or (DEFAULT_TOOL_NAME if selected_mode == "tool_call" else None)
            ),
            metadata=metadata_value,
            token_usage=token_usage if isinstance(token_usage, dict) else None,
            normalized_usage=normalized_usage,
        )


def _contract_digest(contract: Mapping[str, object] | None) -> str | None:
    if contract is None:
        return None
    digest = contract.get("schema_digest")
    if digest is None:
        digest = contract.get("contract_digest")
    return digest if isinstance(digest, str) and digest else None


def _advisory_schema_issues(
    value: object,
    schema: object,
    *,
    path: str = "$",
    limit: int = 16,
    root_schema: object | None = None,
) -> list[dict[str, object]]:
    """Return bounded structural JSON Schema diagnostics.

    Core owns semantic validation and remains the final authority. Local must
    nevertheless verify the portable structural keywords it sent to a strict
    provider: some OpenAI-compatible routes return a parseable HTTP 200 while
    violating array bounds or a nested ``$ref``. The report stays advisory for
    non-strict modes and becomes fail-closed through ``native_schema_valid``
    for an explicitly strict request.
    """

    if not isinstance(schema, Mapping):
        return []
    if root_schema is None:
        root_schema = schema
    issues: list[dict[str, object]] = []

    def add(issue_path: str, code: str, message: str) -> None:
        if len(issues) < limit:
            issues.append({"path": issue_path, "code": code, "message": message})

    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        resolved: object = root_schema
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(resolved, Mapping) or part not in resolved:
                add(path, "$ref", "local schema reference cannot be resolved")
                return issues
            resolved = resolved[part]
        return _advisory_schema_issues(
            value,
            resolved,
            path=path,
            limit=limit,
            root_schema=root_schema,
        )

    alternatives = schema.get("oneOf")
    if isinstance(alternatives, list):
        matches = 0
        for alternative in alternatives:
            if not _advisory_schema_issues(
                value,
                alternative,
                path=path,
                limit=1,
                root_schema=root_schema,
            ):
                matches += 1
        if matches != 1:
            add(path, "oneOf", "value must match exactly one schema alternative")
        return issues

    schema_type = schema.get("type")
    if schema_type == "object" and not isinstance(value, Mapping):
        add(path, "type", "expected object")
        return issues
    if schema_type == "array" and not isinstance(value, list):
        add(path, "type", "expected array")
        return issues
    if schema_type == "string" and not isinstance(value, str):
        add(path, "type", "expected string")
        return issues
    if schema_type == "boolean" and not isinstance(value, bool):
        add(path, "type", "expected boolean")
        return issues
    if schema_type == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        add(path, "type", "expected integer")
        return issues
    if "const" in schema and value != schema.get("const"):
        add(path, "const", "value does not match const")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        add(path, "enum", "value is not in enum")
    if isinstance(value, Mapping):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    add(f"{path}.{key}", "required", "required field is missing")
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            if schema.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        add(
                            f"{path}.{key}",
                            "additionalProperties",
                            "unknown field is not allowed",
                        )
            for key, child_schema in properties.items():
                if isinstance(key, str) and key in value:
                    issues.extend(
                        _advisory_schema_issues(
                            value[key],
                            child_schema,
                            path=f"{path}.{key}",
                            limit=max(0, limit - len(issues)),
                            root_schema=root_schema,
                        )
                    )
                    if len(issues) >= limit:
                        break
    elif isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            add(path, "minItems", "array has fewer items than allowed")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            add(path, "maxItems", "array has more items than allowed")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                issues.extend(
                    _advisory_schema_issues(
                        item,
                        item_schema,
                        path=f"{path}[{index}]",
                        limit=max(0, limit - len(issues)),
                        root_schema=root_schema,
                    )
                )
                if len(issues) >= limit:
                    break
    elif isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            add(path, "minLength", "string is shorter than allowed")
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            add(path, "maxLength", "string is longer than allowed")
    return issues[:limit]


__all__ = [
    "CapabilityStore",
    "InputBudgetExceededError",
    "ProviderFactory",
    "StructuredJsonCapabilityError",
    "StructuredJsonError",
    "StructuredJsonProvider",
    "StructuredJsonRequestError",
    "StructuredJsonResponseError",
    "StructuredJsonResult",
    "StructuredJsonSchemaError",
    "StructuredJsonSecretError",
    "default_provider_factory",
]
