"""Deferred Google transport boundary.

The Core-facing contract is deliberately shared with the OpenAI-compatible
transport.  Google-specific request/response mapping can be added here later
without teaching Core or the generic Local executor about a vendor API.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..cancellation import CancellationToken
from .base import (
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    normalize_error,
    normalize_usage,
)


class GoogleGenerationTransport:
    """Explicitly unavailable boundary rather than an accidental fallback."""

    provider_kind = "google_genai"

    def complete_json(
        self,
        request: ModelRequest,
        token: CancellationToken | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse:
        """Expose the legacy Local provider contract at the boundary."""

        return self.execute_structured(
            request,
            profile=None,
            cancellation_token=cancellation_token or token,
        )

    def execute_structured(
        self,
        task: ModelRequest,
        profile: object,
        capabilities: object | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse:
        del task, profile, capabilities, cancellation_token
        raise ProviderConfigurationError(
            "Google Generative Language transport is not configured in this Local build"
        )

    def probe_capabilities(self, profile: object) -> Mapping[str, object]:
        del profile
        return {
            "transport": self.provider_kind,
            "probe_required": True,
            "implemented": False,
        }

    @staticmethod
    def normalize_usage(response: ModelResponse | Mapping[str, object]) -> dict[str, object]:
        return normalize_usage(response)

    @staticmethod
    def normalize_error(error: BaseException) -> dict[str, object]:
        return normalize_error(error)


__all__ = ["GoogleGenerationTransport"]
