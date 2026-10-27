from types import SimpleNamespace

import pytest

from ledgermind_local.installer.models import GenerationConfig, ResolutionDecisionConfig
from ledgermind_local.installer.profiles.probes import probe_resolution_decision
from ledgermind_local.installer.profiles.resolution_decision import build_resolution_profile, build_runtime_profiles


def config(backend=None):
    return SimpleNamespace(resolution_decision=None if backend is None else ResolutionDecisionConfig(
        backend=backend, runtime_path="/tmp/installed-kev" if backend == "kev" else None),
        generation=GenerationConfig(endpoint="https://openrouter.ai/api/v1", model="generation-model", secret_ref="generation-key",
            route="primary", fallback_routes=("fallback",)),
        runtime=SimpleNamespace(residency_mode="idle", idle_timeout_seconds=60))


def test_old_config_is_legacy_and_generation_settings_are_unchanged():
    old = config()
    assert build_resolution_profile(old) is None
    assert len(build_runtime_profiles(old)) == 3
    new = config("jev")
    assert build_runtime_profiles(new)[:3] == build_runtime_profiles(old)
    profile = build_resolution_profile(new)
    assert profile["model"] == "typesafe/jev-1.13"
    assert profile["endpoint"] == "https://openrouter.ai/api/alpha/decisions"
    assert profile["secret_ref"] == "resolution-decision-api"


def test_generative_decision_has_no_fallback_and_does_not_change_round_semantic():
    new = config("generative")
    profile = build_resolution_profile(new)
    assert profile["extra_body"]["provider"]["allow_fallbacks"] is False
    assert profile["extra_body"]["provider"]["only"] == ["primary"]
    assert build_runtime_profiles(new)[0]["extra_body"]["provider"]["allow_fallbacks"] is True


def test_kev_warned_quality_is_not_used_as_preflight_success(monkeypatch):
    seen = []
    def predict(profile, packet):
        seen.append((profile, packet))
        return {"data": {"choices": {"probe": "ready"}}, "body": {"model": profile.model},
                "latency_ms": 1, "request_id": None}
    monkeypatch.setattr("ledgermind_inference.kev_runtime.kev_decide", predict)
    result = probe_resolution_decision(config("kev"))
    assert result["status"] == "passed"
    assert result.get("accuracy") is None
    assert seen[0][0].extra_body["residency_mode"] == "idle"
    assert seen[0][1]["questions"]["probe"]["criteria"].keys() == {"ready", "absent"}


def test_backend_does_not_accept_another_backends_credentials():
    with pytest.raises(ValueError):
        ResolutionDecisionConfig(backend="generative", token="private")
    with pytest.raises(ValueError):
        ResolutionDecisionConfig(backend="kev")
