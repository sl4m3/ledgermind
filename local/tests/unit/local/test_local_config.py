"""Tests for local service configuration."""

from __future__ import annotations

import pytest
from ledgermind_local.config import LocalConfig
from pydantic import ValidationError


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


def test_generation_concurrency_accepts_fifty_workers() -> None:
    config = LocalConfig.model_validate(
        {
            "config_version": 2,
            "semantic_language": "ru",
            "generation_concurrency": 50,
        }
    )
    assert config.generation_concurrency == 50

    with pytest.raises(ValidationError):
        LocalConfig.model_validate(
            {
                "config_version": 2,
                "semantic_language": "ru",
                "generation_concurrency": 0,
            }
        )


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


def test_reranker_candidate_policy_defaults_to_semantic_and_accepts_formula() -> None:
    from ledgermind_local.config import RerankerConfig

    assert RerankerConfig().candidate_policy == "semantic"
    assert RerankerConfig(candidate_policy="formula").candidate_policy == "formula"
    with pytest.raises(ValidationError):
        RerankerConfig(candidate_policy="lexical")  # type: ignore[arg-type]


def test_retrieval_defaults_enable_dual_view_and_adaptive_merge() -> None:
    config = LocalConfig(config_version=1, semantic_language="ru")

    assert config.retrieval.dual_view_rerank is True
    assert config.retrieval.adaptive_merge is True
    assert config.retrieval.session_context_query_chars == 96
    assert config.retrieval.multi_aspect_quota is True
    assert config.retrieval.multi_aspect_primary_slots == 32
    assert config.retrieval.multi_aspect_aspect_slots == 8


def test_retrieval_config_validation() -> None:
    from ledgermind_local.config import RetrievalConfig

    with pytest.raises(ValidationError):
        RetrievalConfig(session_context_query_chars=-1)
    with pytest.raises(ValidationError):
        RetrievalConfig(session_context_query_chars=1001)
    assert (
        RetrievalConfig(session_context_query_chars=0).session_context_query_chars == 0
    )


def test_retrieval_config_is_optional_for_old_configurations() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 2, "semantic_language": "ru"}
    )

    assert config.retrieval.dual_view_rerank is True


def test_retrieval_config_round_trips_through_json() -> None:
    from ledgermind_local.config import RetrievalConfig

    config = LocalConfig(
        config_version=2,
        semantic_language="ru",
        retrieval=RetrievalConfig(
            dual_view_rerank=False,
            adaptive_merge=False,
            session_context_query_chars=0,
        ),
    )

    restored = LocalConfig.model_validate_json(config.to_json())

    assert restored.retrieval.dual_view_rerank is False
    assert restored.retrieval.adaptive_merge is False
    assert restored.retrieval.session_context_query_chars == 0


def test_worker_poll_limit_migrates_to_lease_batch_with_a_warning() -> None:
    with pytest.warns(DeprecationWarning, match="poll_limit"):
        config = LocalConfig.model_validate(
            {
                "config_version": 2,
                "semantic_language": "ru",
                "workers": {"core_model_tasks": {"poll_limit": 7}},
            }
        )

    assert config.workers.core_model_tasks.lease_batch == 7
    assert "poll_limit" not in config.workers.core_model_tasks.model_dump()


def test_decision_inflight_defaults_to_unbounded() -> None:
    config = LocalConfig.model_validate(
        {"config_version": 2, "semantic_language": "ru"}
    )
    assert config.decision_inflight is None

    bounded = LocalConfig.model_validate(
        {
            "config_version": 2,
            "semantic_language": "ru",
            "decision_inflight": 12,
        }
    )
    assert bounded.decision_inflight == 12

    with pytest.raises(ValidationError):
        LocalConfig.model_validate(
            {
                "config_version": 2,
                "semantic_language": "ru",
                "decision_inflight": 0,
            }
        )
