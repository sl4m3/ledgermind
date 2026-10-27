"""Repair release links, permissions, and Hermes hooks."""

from __future__ import annotations

from typing import Any

from ..config_writer import load_installer_config
from ..paths import InstallerPaths
from ..targets.base import AdapterContext
from ..targets.registry import get_target_adapter
from .common import install_bin_link
from .doctor import doctor


def repair(*, paths: InstallerPaths, dry_run: bool = False) -> dict[str, Any]:
    if not paths.config_file.is_file():
        raise RuntimeError("LedgerMind configuration is missing")
    config = load_installer_config(paths.config_file)
    if not paths.current_link.exists():
        raise RuntimeError("current release symlink is missing")
    if dry_run:
        return {"status": "dry_run", "current": str(paths.current_link)}
    install_bin_link(paths)
    integrations: dict[str, Any] = {}
    for selected in config.integrations:
        adapter = get_target_adapter(selected.id)
        discovery = adapter.discover()
        if not discovery.detected:
            integrations[selected.id] = {
                "status": "failed",
                "error": discovery.detail or "agent was not discovered",
            }
            continue
        context = AdapterContext(
            config=config,
            paths=paths,
            discovery=discovery,
            bundle_root=paths.current_link,
            metadata={"enabled": selected.enabled},
        )
        integrations[selected.id] = adapter.repair(context)
    # Repair is a local filesystem/runtime operation. Provider availability is
    # orthogonal and probing it here would add billable calls and make repair
    # fail during an unrelated upstream outage.
    doctor_report = doctor(paths=paths, probe_providers=False)
    verified = sum(
        1
        for item in integrations.values()
        if isinstance(item, dict) and item.get("status") == "passed"
    )
    return {
        "status": (
            "passed"
            if doctor_report.get("status") == "passed" and verified == len(integrations)
            else "failed"
        ),
        "doctor": doctor_report,
        "integrations": integrations,
        "current": str(paths.current_link),
        "readiness": {
            "platform": doctor_report.get("platform", "linux"),
            "core": doctor_report.get("status", "unknown"),
            "generation": "preserved-not-probed",
            "embeddings": "preserved-not-probed",
            "smoke_test": doctor_report.get("smoke_test", {}).get("status", "unknown"),
            "agents": f"{verified}/{len(integrations)} verified",
            "memory_mode": config.memory_mode,
        },
    }


__all__ = ["repair"]
