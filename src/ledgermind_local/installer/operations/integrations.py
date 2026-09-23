"""Independent lifecycle for agent integrations."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from ..config_writer import bind_existing_profiles_for_agent, load_installer_config, persist_installer_config
from ..errors import AdapterError, ConfigurationError
from ..models import InstallerConfig, IntegrationConfig
from ..paths import InstallerPaths
from ..targets.base import AdapterContext
from ..targets.registry import get_target_adapter, target_ids

logger = logging.getLogger(__name__)


def _installed_config(paths: InstallerPaths) -> InstallerConfig:
    if not paths.config_file.is_file():
        raise ConfigurationError(
            "LedgerMind must be installed before connecting agents"
        )
    return load_installer_config(paths.config_file)


def _replace_selection(
    config: InstallerConfig, target_id: str, *, enabled: bool | None
) -> InstallerConfig:
    selected: dict[str, IntegrationConfig] = {
        item.id: item for item in config.integrations
    }
    if enabled is None:
        selected.pop(target_id, None)
    else:
        selected[target_id] = IntegrationConfig.model_validate(
            {"id": target_id, "enabled": enabled}
        )
    return config.model_copy(update={"integrations": tuple(selected.values())})


def discover_integrations() -> dict[str, Any]:
    return {
        "status": "passed",
        "integrations": {
            target_id: get_target_adapter(target_id).discover().as_dict()
            for target_id in target_ids()
        },
    }


def connect_integration(
    *,
    paths: InstallerPaths,
    target_id: str,
    enabled: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = _installed_config(paths)
    adapter = get_target_adapter(target_id)
    discovery = adapter.discover()
    if not discovery.detected:
        raise AdapterError(discovery.detail or f"{target_id} was not discovered")
    context = AdapterContext(
        config=config,
        paths=paths,
        bundle_root=paths.current_link,
        discovery=discovery,
        dry_run=dry_run,
        metadata={"enabled": enabled},
    )
    preflight = adapter.preflight(context)
    if dry_run:
        return {
            "status": "dry_run",
            "integration": target_id,
            "enabled": enabled,
            "preflight": preflight,
        }
    updated = _replace_selection(config, target_id, enabled=enabled)
    try:
        installed = adapter.install(context)
        verified = adapter.verify(context)
        bound_profiles = bind_existing_profiles_for_agent(updated, paths, target_id)
        persist_installer_config(updated, paths)
    except Exception:
        try:
            adapter.uninstall(context, purge=False)
        except Exception as cleanup_error:  # noqa: BLE001
            logger.warning(
                "integration rollback failed for %s: %s",
                target_id,
                type(cleanup_error).__name__,
            )
        try:
            persist_installer_config(config, paths)
        except Exception as cleanup_error:  # noqa: BLE001
            logger.warning(
                "integration config rollback failed for %s: %s",
                target_id,
                type(cleanup_error).__name__,
            )
        raise
    return {
        "status": "passed",
        "integration": target_id,
        "connected": True,
        "enabled": enabled,
        "preflight": preflight,
        "install": installed,
        "verify": verified,
        "bound_profiles": bound_profiles,
        "summary": {
            "label": adapter.label,
            "agent_location": str(discovery.config_dir or discovery.home or ""),
            "connected": True,
            "enabled": enabled,
            "verification": verified.get("status", "unknown"),
            "activation_required": verified.get("activation_required"),
            "memory_mode": config.memory_mode,
            "memory_space_id": config.memory_space_id_for(target_id),
            "inference_profiles_preserved": True,
        },
    }


def _integration_config_path(target_id: str, context: AdapterContext) -> Path:
    environment = get_target_adapter(target_id).runtime_environment(context)
    key = f"LEDGERMIND_{target_id.upper().replace('-', '_')}_CONFIG"
    value = environment.get(key)
    if not value:
        raise AdapterError(f"{target_id} does not expose a mutable integration config")
    return Path(value)


def set_integration_enabled(
    *, paths: InstallerPaths, target_id: str, enabled: bool, dry_run: bool = False
) -> dict[str, Any]:
    config = _installed_config(paths)
    selected = {item.id: item for item in config.integrations}
    if target_id not in selected:
        raise AdapterError(f"{target_id} is not connected")
    adapter = get_target_adapter(target_id)
    discovery = adapter.discover()
    context = AdapterContext(config=config, paths=paths, discovery=discovery)
    target = _integration_config_path(target_id, context)
    if not target.is_file():
        raise AdapterError(f"{target_id} integration config is missing")
    if dry_run:
        return {
            "status": "dry_run",
            "integration": target_id,
            "enabled": enabled,
            "config": str(target),
        }
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AdapterError(f"{target_id} integration config is invalid")
    payload["enabled"] = enabled
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    target.write_bytes(encoded)
    os.chmod(target, 0o600)
    record_path = target.parent / "installation-record.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        files = record.get("files") if isinstance(record, dict) else None
        config_record = files.get("config.json") if isinstance(files, dict) else None
        if isinstance(config_record, dict):
            config_record["after"] = {
                "content": base64.b64encode(encoded).decode("ascii")
            }
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.chmod(record_path, 0o600)
    updated = _replace_selection(config, target_id, enabled=enabled)
    persist_installer_config(updated, paths)
    return {
        "status": "passed",
        "integration": target_id,
        "connected": True,
        "enabled": enabled,
        "config": str(target),
        "summary": {
            "label": adapter.label,
            "agent_location": str(discovery.config_dir or discovery.home or ""),
            "connected": True,
            "enabled": enabled,
            "verification": "not_repeated",
            "memory_mode": config.memory_mode,
            "memory_space_id": config.memory_space_id_for(target_id),
            "inference_profiles_preserved": True,
        },
    }


def disconnect_integration(
    *, paths: InstallerPaths, target_id: str, dry_run: bool = False
) -> dict[str, Any]:
    config = _installed_config(paths)
    adapter = get_target_adapter(target_id)
    discovery = adapter.discover()
    if dry_run:
        return {"status": "dry_run", "integration": target_id}
    result: dict[str, Any] = {"status": "not_detected"}
    if discovery.detected:
        result = adapter.uninstall(
            AdapterContext(config=config, paths=paths, discovery=discovery), purge=False
        )
    persist_installer_config(_replace_selection(config, target_id, enabled=None), paths)
    return {
        "status": "passed",
        "integration": target_id,
        "connected": False,
        "uninstall": result,
        "summary": {
            "label": adapter.label,
            "agent_location": str(discovery.config_dir or discovery.home or ""),
            "connected": False,
            "enabled": False,
            "verification": "disconnected",
            "inference_profiles_preserved": True,
        },
    }


def integration_status(*, paths: InstallerPaths) -> dict[str, Any]:
    config = _installed_config(paths)
    selected = {item.id: item for item in config.integrations}
    results: dict[str, Any] = {}
    for target_id in target_ids():
        adapter = get_target_adapter(target_id)
        discovery = adapter.discover()
        item: dict[str, Any] = {
            "installed_agent": discovery.detected,
            "connected": target_id in selected,
            "enabled": selected[target_id].enabled if target_id in selected else False,
            "active": False,
            "discovery": discovery.as_dict(),
        }
        if target_id in selected and discovery.detected:
            try:
                verification = adapter.verify(
                    AdapterContext(config=config, paths=paths, discovery=discovery)
                )
                item["verify"] = verification
                item["active"] = bool(selected[target_id].enabled) and not bool(
                    verification.get("activation_required")
                )
            except Exception as exc:  # noqa: BLE001
                item["verify"] = {"status": "failed", "error": str(exc)}
        results[target_id] = item
    return {"status": "passed", "integrations": results}


__all__ = [
    "connect_integration",
    "disconnect_integration",
    "discover_integrations",
    "integration_status",
    "set_integration_enabled",
]
