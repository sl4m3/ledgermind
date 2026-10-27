"""Download approved Hugging Face model files with per-file hashes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..download import download_artifact
from ..errors import ConfigurationError
from ..paths import InstallerPaths


def _relative_model_path(value: object) -> Path:
    name = str(value or "").strip().replace("\\", "/")
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ConfigurationError("embedding model file path is invalid")
    return path


def _file_records(entry: dict[str, Any]) -> list[dict[str, Any]]:
    records = entry.get("files", [])
    if isinstance(records, dict):
        return [
            {"name": name, "url": url, "sha256": entry.get("sha256", {}).get(name)}
            for name, url in records.items()
        ]
    if not isinstance(records, list):
        raise ConfigurationError("embedding catalog files must be a list")
    result: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, str):
            result.append({"name": Path(record).name, "url": record})
        elif isinstance(record, dict):
            result.append(dict(record))
        else:
            raise ConfigurationError(
                "embedding catalog contains an invalid file record"
            )
    hashes = entry.get("sha256", {})
    for record in result:
        record.setdefault("sha256", hashes.get(record.get("name")))
    return result


def download_model(
    entry: dict[str, Any],
    paths: InstallerPaths,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    model_id = str(entry.get("id", "")).strip()
    if not model_id:
        raise ConfigurationError("embedding catalog entry has no id")
    target_dir = paths.models_dir / model_id
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    records = _file_records(entry)
    total_size = sum(int(record.get("size") or 0) for record in records)
    completed_size = 0
    for record in records:
        relative = _relative_model_path(record.get("name"))
        url = str(record.get("url", "")).strip()
        if not url:
            raise ConfigurationError("embedding model file URL is invalid")
        if record.get("size") is None or not record.get("sha256"):
            raise ConfigurationError(
                "signed embedding catalog requires size and SHA-256 for every file"
            )
        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        download_artifact(
            url,
            destination,
            expected_size=int(record["size"]),
            expected_sha256=str(record["sha256"]),
            progress=(
                lambda transferred, _total, base=completed_size: progress(
                    base + transferred, total_size
                )
                if progress is not None
                else None
            ),
        )
        completed_size += int(record["size"])
    return target_dir


__all__ = ["download_model"]
