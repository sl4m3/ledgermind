"""Filesystem operations for Hermes payload installation."""

from __future__ import annotations

import base64
import json
import os
import shutil
from pathlib import Path
from typing import Any

from ...errors import AdapterError
from ...permissions import ensure_private_dir


def _payload_root(context_bundle: Path | None) -> Path | None:
    if context_bundle is None:
        return None
    candidates = (
        context_bundle / "integrations" / "hermes" / "plugin",
        context_bundle / "integrations" / "hermes",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def _record_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    if not path.is_file():
        raise AdapterError(f"Hermes target path is not a regular file: {path}")
    return {
        "exists": True,
        "mode": path.stat().st_mode & 0o777,
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def install_plugin(
    *,
    hermes_home: Path,
    bundle_root: Path | None,
    plugin_config: dict[str, Any],
) -> dict[str, Any]:
    plugin_root = hermes_home / "plugins" / "ledgermind-hermes"
    ensure_private_dir(plugin_root)
    payload = _payload_root(bundle_root)
    if payload is None:
        raise AdapterError(
            "signed Hermes plugin payload is missing from platform bundle"
        )
    files = [
        path
        for path in payload.rglob("*")
        if path.is_file() and path.name != "installation-record.json"
    ]
    if not files:
        raise AdapterError("signed Hermes plugin payload is empty")
    record: dict[str, Any] = {
        "schema_version": 1,
        "target": "hermes",
        "plugin_root": str(plugin_root),
        "files": {},
    }
    for source in files:
        relative = source.relative_to(payload)
        destination = plugin_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        record["files"][str(relative)] = {
            "before": _record_file(destination),
            "after": {"content": base64.b64encode(source.read_bytes()).decode("ascii")},
        }
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o600)
    config_path = plugin_root / "config.json"
    config_bytes = (
        json.dumps(plugin_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    record["files"]["config.json"] = {
        "before": _record_file(config_path),
        "after": {"content": base64.b64encode(config_bytes).decode("ascii")},
    }
    config_path.write_bytes(config_bytes)
    os.chmod(config_path, 0o600)
    record_path = plugin_root / "installation-record.json"
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(record_path, 0o600)
    return {
        "plugin_root": str(plugin_root),
        "installation_record": str(record_path),
        "files": len(record["files"]),
    }


def restore_plugin(*, plugin_root: Path, purge: bool = False) -> dict[str, Any]:
    record_path = plugin_root / "installation-record.json"
    if not record_path.is_file():
        return {"status": "not_installed", "plugin_root": str(plugin_root)}
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdapterError("Hermes installation record cannot be read") from exc
    restored = 0
    skipped = 0
    for relative, details in dict(record.get("files", {})).items():
        path = plugin_root / relative
        after = details.get("after", {})
        expected_after = (
            base64.b64decode(after.get("content", "")) if after.get("content") else None
        )
        if (
            expected_after is not None
            and path.exists()
            and path.read_bytes() != expected_after
        ):
            skipped += 1
            continue
        before = details.get("before", {})
        if before.get("exists"):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(base64.b64decode(before.get("content", "")))
            os.chmod(path, int(before.get("mode", 0o600)))
        else:
            path.unlink(missing_ok=True)
        restored += 1
    record_path.unlink(missing_ok=True)
    if purge and plugin_root.exists():
        shutil.rmtree(plugin_root)
    return {"status": "passed", "restored": restored, "skipped_user_changes": skipped}


__all__ = ["install_plugin", "restore_plugin"]
