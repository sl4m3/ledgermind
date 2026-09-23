"""Verification of the installed Hermes payload and hooks."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ...errors import AdapterError

REQUIRED_HOOKS = {
    "pre_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "post_llm_call",
    "on_session_end",
}


def verify_hermes_plugin(
    plugin_root: str | Path,
    *,
    hermes_binary: str | None = None,
    hermes_home: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(plugin_root)
    manifest_path = root / "plugin.yaml"
    if not manifest_path.is_file():
        raise AdapterError(f"Hermes plugin manifest is missing: {manifest_path}")
    text = manifest_path.read_text(encoding="utf-8")
    hooks: set[str] = set()
    in_hooks = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in {"provides_hooks:", "hooks:"}:
            in_hooks = True
            continue
        if in_hooks and stripped.startswith("-"):
            hooks.add(stripped[1:].strip())
            continue
        if in_hooks and stripped and not stripped.startswith("-"):
            in_hooks = False
    missing = sorted(REQUIRED_HOOKS - hooks)
    if missing:
        raise AdapterError(f"Hermes plugin is missing hooks: {', '.join(missing)}")
    record_path = root / "installation-record.json"
    if not record_path.is_file():
        raise AdapterError("Hermes installation record is missing")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdapterError("Hermes installation record is invalid") from exc
    if not isinstance(record, dict) or record.get("target") != "hermes":
        raise AdapterError("Hermes installation record has an invalid target")
    config_path = root / "config.json"
    try:
        plugin_config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdapterError("Hermes plugin config is invalid") from exc
    expected_enabled = bool(plugin_config.get("enabled", True))
    if hermes_binary is None:
        raise AdapterError("Hermes CLI is required to verify plugin activation")
    environment = dict(os.environ)
    if hermes_home is not None:
        environment["HERMES_HOME"] = str(Path(hermes_home).expanduser())
    completed = subprocess.run(
        [hermes_binary, "plugins", "list", "--plain", "--no-bundled"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    if completed.returncode != 0:
        raise AdapterError("Hermes plugin activation status could not be read")
    matching = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().endswith("ledgermind-hermes")
    ]
    actual_enabled = bool(matching and matching[0].startswith("enabled"))
    if actual_enabled != expected_enabled:
        state = "enabled" if expected_enabled else "disabled"
        raise AdapterError(f"Hermes plugin is not {state}")
    return {
        "status": "passed",
        "plugin_root": str(root),
        "hooks": sorted(hooks),
        "enabled": actual_enabled,
    }


__all__ = ["REQUIRED_HOOKS", "verify_hermes_plugin"]
