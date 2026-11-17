"""Reference model defaults for Local, loaded from packaged JSON.

The JSON file is the source of truth for provider model names. Code must not
duplicate these literals: an installer or a release may override individual
values without patching Python. ``LEDGERMIND_MODEL_DEFAULTS_FILE`` may point at
a JSON file whose values are merged over the packaged defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

_DEFAULTS_RESOURCE = "model-defaults.json"
_OVERRIDE_ENV = "LEDGERMIND_MODEL_DEFAULTS_FILE"
_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ModelDefaults:
    """Model identities shared by the installer and its probes."""

    generation_openrouter: str
    generation_nvidia_nim: str
    embedding_api: str
    embedding_dimensions: int
    embedding_local_catalog_id: str
    embedding_local_alias: str
    reranker_local: str
    resolution_decision: str


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"model defaults must be a JSON object: {path}")
    return payload


def _read_packaged() -> dict[str, Any]:
    resource = files("ledgermind_local").joinpath(_DEFAULTS_RESOURCE)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{_DEFAULTS_RESOURCE} must contain a JSON object")
    return payload


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged


def _section(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise TypeError(f"model defaults section {name!r} must be an object")
    return value


def _text(section: dict[str, Any], name: str, path: str) -> str:
    value = section.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"model defaults {path} must be a non-empty string")
    return value.strip()


def _dimensions(section: dict[str, Any]) -> int:
    value = section.get("dimensions")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            "model defaults embedding.dimensions must be a positive integer"
        )
    return value


@lru_cache(maxsize=1)
def load_model_defaults() -> ModelDefaults:
    """Return validated model defaults, merging an optional override file."""

    payload = _read_packaged()
    override_path = os.environ.get(_OVERRIDE_ENV, "").strip()
    if override_path:
        payload = _merge(payload, _read_json(Path(override_path).expanduser()))
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"model defaults schema_version must be {_SCHEMA_VERSION}")
    generation = _section(payload, "generation")
    embedding = _section(payload, "embedding")
    reranker = _section(payload, "reranker")
    decision = _section(payload, "resolution_decision")
    return ModelDefaults(
        generation_openrouter=_text(generation, "openrouter", "generation.openrouter"),
        generation_nvidia_nim=_text(generation, "nvidia_nim", "generation.nvidia_nim"),
        embedding_api=_text(embedding, "api", "embedding.api"),
        embedding_dimensions=_dimensions(embedding),
        embedding_local_catalog_id=_text(
            embedding, "local_catalog_id", "embedding.local_catalog_id"
        ),
        embedding_local_alias=_text(embedding, "local_alias", "embedding.local_alias"),
        reranker_local=_text(reranker, "local", "reranker.local"),
        resolution_decision=_text(decision, "model", "resolution_decision.model"),
    )


__all__ = ["ModelDefaults", "load_model_defaults"]
