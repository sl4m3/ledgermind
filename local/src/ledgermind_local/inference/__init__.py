"""Local inference profiles, secrets, providers, and technical slots."""

import sys
import ledgermind_inference.core_task_executor
import ledgermind_inference.structured_json_provider
import ledgermind_inference.profiles
import ledgermind_inference.provider_probe
import ledgermind_inference.provider_telemetry
import ledgermind_inference.token_budget
import ledgermind_inference.cancellation
import ledgermind_inference.openai_vectorizer
import ledgermind_inference.vectorizer
import ledgermind_inference.sentence_transformer_vectorizer
import ledgermind_inference.strict
import ledgermind_inference.secrets
import ledgermind_inference.retrieval_reranker
import ledgermind_inference.providers
import ledgermind_inference.providers.base
import ledgermind_inference.providers.openai_compatible
import ledgermind_inference.providers.google_boundary

sys.modules["ledgermind_local.inference.core_task_executor"] = ledgermind_inference.core_task_executor
sys.modules["ledgermind_local.inference.structured_json_provider"] = ledgermind_inference.structured_json_provider
sys.modules["ledgermind_local.inference.profiles"] = ledgermind_inference.profiles
sys.modules["ledgermind_local.inference.provider_probe"] = ledgermind_inference.provider_probe
sys.modules["ledgermind_local.inference.provider_telemetry"] = ledgermind_inference.provider_telemetry
sys.modules["ledgermind_local.inference.token_budget"] = ledgermind_inference.token_budget
sys.modules["ledgermind_local.inference.cancellation"] = ledgermind_inference.cancellation
sys.modules["ledgermind_local.inference.openai_vectorizer"] = ledgermind_inference.openai_vectorizer
sys.modules["ledgermind_local.inference.vectorizer"] = ledgermind_inference.vectorizer
sys.modules["ledgermind_local.inference.sentence_transformer_vectorizer"] = ledgermind_inference.sentence_transformer_vectorizer
sys.modules["ledgermind_local.inference.strict"] = ledgermind_inference.strict
sys.modules["ledgermind_local.inference.secrets"] = ledgermind_inference.secrets
sys.modules["ledgermind_local.inference.retrieval_reranker"] = ledgermind_inference.retrieval_reranker
sys.modules["ledgermind_local.inference.providers"] = ledgermind_inference.providers
sys.modules["ledgermind_local.inference.providers.base"] = ledgermind_inference.providers.base
sys.modules["ledgermind_local.inference.providers.openai_compatible"] = ledgermind_inference.providers.openai_compatible
sys.modules["ledgermind_local.inference.providers.google_boundary"] = ledgermind_inference.providers.google_boundary

from ..embedding_purpose import EmbeddingPurpose
from .profile_slots import (
    DatabaseBackedProfileResolver,
    MissingProfileError,
    ProfileSlot,
    StoreBackedProfileResolver,
)
from .profile_store import DatabaseBackedCapabilityStore, InferenceProfileStore
from .profiles import (
    EMBEDDING_PROFILE_DIGEST_ALGORITHM,
    EMBEDDING_PROFILE_DIGEST_SCHEMA_VERSION,
    GENERATION_PROFILE_DIGEST_ALGORITHM,
    GENERATION_PROFILE_DIGEST_SCHEMA_VERSION,
    EmbeddingProfileIdentity,
    EmbeddingProfileReadiness,
    InferenceProfile,
    ProbeStatus,
    ProviderCapabilities,
    ProviderKind,
    StructuredOutputMode,
    StructuredOutputPreference,
    TokenParameter,
    embedding_profile_fingerprint,
    generation_profile_fingerprint,
)
from .provider_probe import PROBE_MODE_ORDER, ProviderProbe, ProviderProbeResult
from .secrets import SecretNotFoundError, SecretStore
from .token_budget import (
    InputBudgetExceededError,
    OutputBudgetExceededError,
    TokenBudgetEstimate,
    TokenBudgetEstimator,
)

__all__ = [
    "EMBEDDING_PROFILE_DIGEST_ALGORITHM",
    "EMBEDDING_PROFILE_DIGEST_SCHEMA_VERSION",
    "GENERATION_PROFILE_DIGEST_ALGORITHM",
    "GENERATION_PROFILE_DIGEST_SCHEMA_VERSION",
    "PROBE_MODE_ORDER",
    "DatabaseBackedCapabilityStore",
    "DatabaseBackedProfileResolver",
    "EmbeddingProfileIdentity",
    "EmbeddingProfileReadiness",
    "EmbeddingPurpose",
    "InferenceProfile",
    "InferenceProfileStore",
    "InputBudgetExceededError",
    "OutputBudgetExceededError",
    "MissingProfileError",
    "ProbeStatus",
    "ProfileSlot",
    "ProviderCapabilities",
    "ProviderKind",
    "ProviderProbe",
    "ProviderProbeResult",
    "SecretNotFoundError",
    "SecretStore",
    "StoreBackedProfileResolver",
    "StructuredOutputMode",
    "StructuredOutputPreference",
    "TokenBudgetEstimate",
    "TokenBudgetEstimator",
    "TokenParameter",
    "embedding_profile_fingerprint",
    "generation_profile_fingerprint",
]
