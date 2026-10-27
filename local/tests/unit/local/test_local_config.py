"""Tests for local service configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ledgermind_local.config import LocalConfig


def test_config_version_required() -> None:
    with pytest.raises(ValidationError):
        LocalConfig.model_validate({"bind_host": "127.0.0.1"})


def test_semantic_language_is_required_from_configuration() -> None:
    with pytest.raises(ValidationError, match="semantic_language"):
        LocalConfig.model_validate({"config_version": 1})


def test_custom_semantic_language_tag_is_canonicalized() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 2, "semantic_language": "zh_hans"}
    )

    assert config.semantic_language == "zh-Hans"


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LocalConfig.model_validate({"config_version": 1, "secret_api_key": "x"})


def test_remote_bind_requires_explicit_allow_remote_bind() -> None:
    with pytest.raises(ValidationError):
        LocalConfig.model_validate(
            {"config_version": 1, "bind_host": "0.0.0.0", "allow_remote_bind": False}
        )


def test_remote_bind_allowed_when_flag_enabled() -> None:
    config = LocalConfig.model_validate(
        {
            "config_version": 1,
            "semantic_language": "ru",
            "bind_host": "0.0.0.0",
            "allow_remote_bind": True,
        }
    )
    assert config.bind_host == "0.0.0.0"
    assert config.allow_remote_bind is True


def test_config_has_expected_6_2_shape() -> None:
    config = LocalConfig.model_validate(
        {
            "config_version": 1,
            "semantic_language": "ru",
            "bind_host": "127.0.0.1",
            "bind_port": 8765,
        }
    )
    payload = config.to_json()
    assert '"config_version":1' in payload
    assert '"rounds_database_path":"rounds.db"' in payload
    assert '"log_level":"INFO"' in payload
    assert '"embedding":{"enabled":false' in payload
    assert "core_model_tasks" in payload
    assert "core_projections" not in payload


def test_process_core_backend_is_the_only_default() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 1, "semantic_language": "ru"}
    )

    assert config.core_backend == "process"


def test_python_core_backend_is_rejected_after_cutover() -> None:
    with pytest.raises(ValidationError):
        LocalConfig.model_validate({"config_version": 1, "core_backend": "python"})


def test_config_to_json_is_deterministic() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 1, "semantic_language": "ru", "bind_port": 8765}
    )
    first = config.to_json()
    second = config.to_json()
    assert first == second
    assert '"config_version":1' in first


def test_legacy_runtime_settings_migrate_to_current_shape() -> None:
    config = LocalConfig.from_dict(
        {
            "config_version": 1,
            "semantic_language": "ru",
            "hypothesis_profile_id": "operational-default",
            "merge_profile_id": "background-default",
            "processing_max_attempts": 7,
            "workers": {
                "processing": {"enabled": True},
                "core_projections": {"enabled": True},
            },
            "vector": {"enabled": True, "model_path": "model.gguf"},
            "markdown_projection": {"enabled": True},
        }
    )

    assert config.config_version == 2
    assert config.profile_slots.operational == "operational-default"
    assert config.profile_slots.background == "background-default"
    assert config.worker_max_attempts == 7
    assert config.embedding.enabled is True
    payload = config.model_dump()
    assert "hypothesis_profile_id" not in payload
    assert "merge_profile_id" not in payload
    assert "processing" not in payload["workers"]
    assert "core_projections" not in payload["workers"]
    assert "vector" not in payload
    assert "markdown_projection" not in payload


def test_log_level_is_normalized_to_uppercase() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 1, "semantic_language": "ru", "log_level": "info"}
    )
    assert config.log_level == "INFO"
