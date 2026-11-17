"""One independent OR/KR backend; text rendering always remains operational."""

from ledgermind_inference.profiles import DEFAULT_GENERATION_MAX_INPUT_TOKENS

from ...model_defaults import load_model_defaults
from .generation import build_generation_profiles

DECISION_SECRET_REF = "resolution-decision-api"


def build_resolution_profile(config):
    decision = config.resolution_decision
    if decision is None:
        return None
    if decision.backend != "jev":
        raise ValueError("only Jev is supported for resolution_decision")
    return {
        "profile_id": "resolution-decision",
        "slot": "resolution_decision",
        "max_output_tokens": 6144,
        "decision_backend": "jev",
        "timeout_seconds": config.generation.timeout_seconds,
        "endpoint": "https://openrouter.ai/api/alpha/decisions",
        "provider_kind": "openai_compatible",
        "model": load_model_defaults().resolution_decision,
        "secret_ref": DECISION_SECRET_REF,
        # Jev's supported default request window is 64k tokens
        # (32k per question). Do not inherit the generic 12k profile
        # default: the structured object-resolution request is larger.
        "max_input_tokens": DEFAULT_GENERATION_MAX_INPUT_TOKENS,
        "extra_body": {},
    }


def build_runtime_profiles(config):
    profiles = list(build_generation_profiles(config.generation))
    decision = build_resolution_profile(config)
    if decision is not None:
        profiles.append(decision)
    return profiles
