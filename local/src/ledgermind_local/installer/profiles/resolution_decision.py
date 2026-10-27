"""One independent OR/KR backend; text rendering always remains operational."""

from .generation import build_generation_profiles

DECISION_SECRET_REF = "resolution-decision-api"


def build_resolution_profile(config):
    decision = config.resolution_decision
    if decision is None:
        return None
    common = {
        "profile_id": "resolution-decision",
        "slot": "resolution_decision",
        "max_output_tokens": 6144,
        "decision_backend": decision.backend,
        "timeout_seconds": config.generation.timeout_seconds,
    }
    if decision.backend == "generative":
        profile = dict(build_generation_profiles(config.generation)[0])
        # Never allow route/model fallback for a closed semantic decision.
        extra = dict(profile.get("extra_body", {}))
        if config.generation.route:
            extra["provider"] = {
                "order": [config.generation.route],
                "only": [config.generation.route],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        elif "openrouter.ai" in config.generation.endpoint:
            extra["provider"] = {"allow_fallbacks": False, "require_parameters": True}
        return {**profile, **common, "extra_body": extra}
    if decision.backend == "jev":
        return {
            **common,
            "endpoint": "https://openrouter.ai/api/alpha/decisions",
            "provider_kind": "openai_compatible",
            "model": "typesafe/jev-1.13",
            "secret_ref": DECISION_SECRET_REF,
            "extra_body": {},
        }
    return {
        **common,
        "endpoint": "http://127.0.0.1",
        "provider_kind": "openai_compatible",
        "model": "jaredpalmer/kev-4b",
        "secret_ref": "local-decision-unused",
        "extra_body": {
            "runtime_path": decision.runtime_path,
            "residency_mode": config.runtime.residency_mode,
            "idle_timeout_seconds": config.runtime.idle_timeout_seconds,
        },
    }


def build_runtime_profiles(config):
    profiles = list(build_generation_profiles(config.generation))
    decision = build_resolution_profile(config)
    if decision is not None:
        profiles.append(decision)
    return profiles
