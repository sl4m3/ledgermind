from __future__ import annotations

import json
from types import SimpleNamespace

from ledgermind_local.installer import wizard
from ledgermind_local.installer.models import GenerationConfig, ResolutionDecisionConfig
from ledgermind_local.installer.profiles.resolution_decision import (
    build_resolution_profile,
)
from ledgermind_local.model_defaults import load_model_defaults


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        resolution_decision=ResolutionDecisionConfig(
            backend="jev", token="decision-token"
        ),
        generation=GenerationConfig(
            endpoint="https://openrouter.ai/api/v1",
            model="generation-model",
            secret_ref="generation-secret",
            route="primary",
            fallback_routes=(),
        ),
    )


def test_packaged_defaults_are_valid_and_exposed_by_wizard() -> None:
    defaults = load_model_defaults()

    assert defaults.generation_openrouter == "deepseek/deepseek-v4-flash-0731"
    assert defaults.generation_nvidia_nim == "nvidia/nemotron-3-super-120b-a12b"
    assert defaults.embedding_api == "nvidia/nemotron-3.5-embed-1b:free"
    assert defaults.embedding_dimensions == 2048
    assert defaults.embedding_local_catalog_id == "nemotron-3-embed-1b-bf16"
    assert defaults.embedding_local_alias == "nvidia/nemotron-3-embed-1b-local-bf16"
    assert defaults.reranker_local == "Qwen/Qwen3-Reranker-0.6B"
    assert defaults.resolution_decision == "typesafe/jev-1.14"

    assert wizard.REFERENCE_GENERATION_MODEL == defaults.generation_openrouter
    assert wizard.REFERENCE_NVIDIA_GENERATION_MODEL == defaults.generation_nvidia_nim
    assert wizard.REFERENCE_EMBEDDING_MODEL == defaults.embedding_api
    assert wizard.REFERENCE_EMBEDDING_DIMENSIONS == defaults.embedding_dimensions
    assert (
        wizard.REFERENCE_LOCAL_EMBEDDING_CATALOG_ID
        == defaults.embedding_local_catalog_id
    )
    assert wizard.REFERENCE_LOCAL_EMBEDDING_ALIAS == defaults.embedding_local_alias
    assert wizard.REFERENCE_RERANKER_MODEL == defaults.reranker_local
    assert wizard.REFERENCE_RESOLUTION_DECISION_MODEL == defaults.resolution_decision


def test_override_file_merges_only_requested_values(tmp_path, monkeypatch) -> None:
    override = tmp_path / "model-defaults.json"
    override.write_text(
        json.dumps({"generation": {"openrouter": "private/generation-model"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGERMIND_MODEL_DEFAULTS_FILE", str(override))
    load_model_defaults.cache_clear()
    try:
        defaults = load_model_defaults()
        assert defaults.generation_openrouter == "private/generation-model"
        assert defaults.generation_nvidia_nim == "nvidia/nemotron-3-super-120b-a12b"
        assert defaults.resolution_decision == "typesafe/jev-1.14"
    finally:
        load_model_defaults.cache_clear()


def test_resolution_profile_uses_the_configured_model(tmp_path, monkeypatch) -> None:
    override = tmp_path / "model-defaults.json"
    override.write_text(
        json.dumps({"resolution_decision": {"model": "private/jev-model"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGERMIND_MODEL_DEFAULTS_FILE", str(override))
    load_model_defaults.cache_clear()
    try:
        profile = build_resolution_profile(_config())
    finally:
        load_model_defaults.cache_clear()

    assert profile is not None
    assert profile["model"] == "private/jev-model"
