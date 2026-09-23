"""Validate/import configuration without silently installing a target."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config_writer import select_secret_backend, write_installer_config
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..permissions import assert_private
from ..profiles.probes import probe_embedding_api, probe_generation
from ..secret_refs import (
    EMBEDDING_SECRET_REF,
    GENERATION_SECRET_REF,
    LEGACY_EMBEDDING_SECRET_REF,
    LEGACY_GENERATION_SECRET_REF,
)
from ..secrets.base import SecretBackend


def _get_secret(backend: SecretBackend, *refs: str) -> str | None:
    for ref in refs:
        value = backend.get(ref)
        if value:
            return value
    return None


def import_config(
    *,
    paths: InstallerPaths,
    file: str | Path,
    validate_providers: bool = False,
    register_target: bool = False,
    delete_after_import: bool = False,
) -> dict[str, Any]:
    source = Path(file).expanduser()
    assert_private(source, directory=False)
    payload = json.loads(source.read_text(encoding="utf-8"))
    secrets = payload.pop("secrets", {}) if isinstance(payload, dict) else {}
    config = InstallerConfig.model_validate(payload)
    backend = select_secret_backend(paths)
    if isinstance(secrets, dict):
        for key, value in secrets.items():
            if isinstance(key, str) and isinstance(value, str):
                backend.put(key, value)
    probes: dict[str, Any] = {}
    if validate_providers:
        generation_token = config.generation.token or _get_secret(
            backend, GENERATION_SECRET_REF, LEGACY_GENERATION_SECRET_REF
        )
        if generation_token:
            probes["generation"] = probe_generation(
                config.generation, token=generation_token
            )
        if config.embedding.mode == "api" and config.embedding.api is not None:
            token = config.embedding.api.token or _get_secret(
                backend, EMBEDDING_SECRET_REF, LEGACY_EMBEDDING_SECRET_REF
            )
            if token:
                probes["embedding"] = probe_embedding_api(
                    config.embedding.api, token=token
                )
    metadata = write_installer_config(config, paths)
    if delete_after_import:
        source.unlink(missing_ok=True)
    return {
        "status": "passed",
        "config": metadata,
        "probes": probes,
        "target_registered": bool(register_target),
    }


__all__ = ["import_config"]
