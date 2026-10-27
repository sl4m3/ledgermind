"""Signed release manifest models and loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigurationError


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    signature: str | None = None
    platform: str
    minimum_glibc: str | None = None
    component_compatibility: dict[str, Any] = Field(default_factory=dict)


class PlatformRelease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installer: ArtifactRecord
    bundle: ArtifactRecord


class InstallManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    release_version: str = Field(min_length=1)
    published_at: str
    public_key_fingerprint: str = Field(min_length=1)
    platforms: dict[str, PlatformRelease]
    components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    embedding_catalog: list[dict[str, Any]] = Field(default_factory=list)

    def platform(self, platform: str) -> PlatformRelease:
        try:
            return self.platforms[platform]
        except KeyError as exc:
            raise ConfigurationError(
                f"release does not support platform {platform}"
            ) from exc

    def catalog_entry(self, catalog_id: str) -> dict[str, Any]:
        for entry in self.embedding_catalog:
            if entry.get("id") == catalog_id:
                return dict(entry)
        raise ConfigurationError(
            f"embedding model is not in the signed catalog: {catalog_id}"
        )


def load_manifest(path: str | Path) -> InstallManifest:
    target = Path(path).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return InstallManifest.model_validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ConfigurationError(f"invalid install manifest: {target}") from exc


def dump_manifest(manifest: InstallManifest, path: str | Path) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ArtifactRecord",
    "InstallManifest",
    "PlatformRelease",
    "dump_manifest",
    "load_manifest",
]
