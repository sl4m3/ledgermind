from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from ledgermind_local.inference.profiles import (
    EmbeddingProfileIdentity,
    InferenceProfile,
    embedding_profile_fingerprint,
)
from ledgermind_local.inference.secrets import SecretNotFoundError, SecretStore


def test_inference_profile_forbids_provider_secret_and_unknown_fields() -> None:
    profile = InferenceProfile(
        profile_id="operational-default",
        provider_kind="openai_compatible",
        base_url="https://provider.example/v1",
        model="test-model",
        secret_ref="provider-main",
        timeout_seconds=12,
        max_retries=2,
        max_input_tokens=4_000,
        max_output_tokens=800,
        enabled=True,
    )

    assert profile.base_url == "https://provider.example/v1"
    assert "api_key" not in profile.model_dump()
    with pytest.raises(ValueError):
        InferenceProfile.model_validate({**profile.model_dump(), "api_key": "secret"})


def test_inference_profile_rejects_invalid_provider_and_limits() -> None:
    with pytest.raises(ValueError, match="provider_kind"):
        InferenceProfile(
            profile_id="p",
            provider_kind="anthropic",
            base_url="https://provider.example/v1",
            model="model",
            secret_ref="ref",
        )

    with pytest.raises(ValueError, match="secret-like"):
        InferenceProfile(
            profile_id="p",
            base_url="https://provider.example/v1",
            model="model",
            secret_ref="ref",
            extra_body={"api_key": "must-not-be-stored"},
        )

    with pytest.raises(ValueError, match="max_output_tokens"):
        InferenceProfile(
            profile_id="p",
            provider_kind="openai_compatible",
            base_url="https://provider.example/v1",
            model="model",
            secret_ref="ref",
            max_output_tokens=0,
        )


def test_inference_profile_exposes_runinfra_prompt_cache_capability() -> None:
    runinfra = InferenceProfile(
        profile_id="generation-runinfra",
        base_url="https://api.runinfra.ai/v1",
        model="test-model",
        secret_ref="generation-test",
    )
    openrouter = InferenceProfile(
        profile_id="generation-openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="test-model",
        secret_ref="generation-test",
    )

    assert runinfra.supports_prompt_cache_key is True
    assert openrouter.supports_prompt_cache_key is False


def test_embedding_profile_fingerprint_is_stable_token_free_and_config_sensitive() -> None:
    first = embedding_profile_fingerprint(
        "nvidia/nemotron-3-embed-1b",
        "model-build-1",
        1024,
        {
            "provider": "local",
            "runtime": {
                "endpoint": "https://user:first-secret@provider.example/v1?token=first",
                "gpu_layers": 0,
                "token": "first-secret",
            },
        },
    )
    reordered = embedding_profile_fingerprint(
        "nvidia/nemotron-3-embed-1b",
        "model-build-1",
        1024,
        {
            "runtime": {
                "token": "second-secret",
                "endpoint": "https://user:second-secret@provider.example/v1?token=second",
                "gpu_layers": 0,
            },
            "provider": "local",
        },
    )

    assert first == reordered
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64
    assert first != embedding_profile_fingerprint(
        "nvidia/nemotron-3-embed-1b", "model-build-1", 1536, {"provider": "local"}
    )
    assert first != embedding_profile_fingerprint(
        "nvidia/nemotron-3-embed-1b", "model-build-1", 1024, {"provider": "api"}
    )

    identity = EmbeddingProfileIdentity(
        model_id="nvidia/nemotron-3-embed-1b",
        model_version="model-build-1",
        dimensions=1024,
        config={"provider": "local"},
    )
    assert identity.profile_fingerprint.startswith("sha256:")


def test_secret_store_is_private_atomic_and_does_not_expose_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / "local" / "secrets.json"
    store = SecretStore(path)
    store.put("provider-main", "TOP_SECRET")

    assert store.get("provider-main") == "TOP_SECRET"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "TOP_SECRET" not in repr(store)
    assert "TOP_SECRET" in path.read_text(encoding="utf-8")
    assert (
        json.loads(path.read_text(encoding="utf-8"))["secrets"]["provider-main"]
        == "TOP_SECRET"
    )

    store.delete("provider-main")
    with pytest.raises(SecretNotFoundError, match="provider-main"):
        store.get("provider-main")


def test_secret_store_errors_do_not_include_secret_value(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    path.write_text('{"secrets": ["invalid"]}', encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        SecretStore(path).get("provider-main")

    assert "TOP_SECRET" not in str(error.value)
