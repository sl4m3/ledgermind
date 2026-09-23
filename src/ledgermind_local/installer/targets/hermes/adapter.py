"""First-party Hermes TargetAdapter implementation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...errors import AdapterError
from ..base import AdapterContext, BaseTargetAdapter, TargetDiscovery
from .discover import discover_hermes
from .hooks import hook_registration
from .install import install_plugin
from .lifecycle import lifecycle_contract
from .verify import verify_hermes_plugin


class HermesTargetAdapter(BaseTargetAdapter):
    id = "hermes"
    label = "Hermes"

    def discover(self) -> TargetDiscovery:
        return discover_hermes()

    def _discovery(self, context: AdapterContext) -> TargetDiscovery:
        discovery = context.discovery or self.discover()
        if not discovery.detected or discovery.home is None:
            raise RuntimeError(discovery.detail or "Hermes was not discovered")
        return discovery

    def _home(self, context: AdapterContext) -> Path:
        home = self._discovery(context).home
        assert home is not None
        return home

    def preflight(self, context: AdapterContext) -> dict[str, Any]:
        discovery = self._discovery(context)
        return {
            "target": self.id,
            "discovery": discovery.as_dict(),
            "hooks": hook_registration(),
        }

    def _set_plugin_enabled(
        self, context: AdapterContext, *, enabled: bool
    ) -> dict[str, Any]:
        binary = shutil.which("hermes")
        if binary is None:
            raise AdapterError(
                "Hermes CLI is required to activate the LedgerMind plugin"
            )
        command = [
            binary,
            "plugins",
            "enable",
            "ledgermind-hermes",
            "--no-allow-tool-override",
        ]
        if not enabled:
            command = [binary, "plugins", "disable", "ledgermind-hermes"]
        environment = dict(os.environ)
        environment["HERMES_HOME"] = str(self._home(context))
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise AdapterError(
                f"Hermes plugin activation failed: {detail or 'unknown error'}"
            )
        return {"enabled": enabled, "status": "passed"}

    def install(self, context: AdapterContext) -> dict[str, Any]:
        home = self._home(context)
        if context.dry_run:
            return {
                "status": "dry_run",
                "plugin_root": str(home / "plugins" / "ledgermind-hermes"),
            }
        payload = {
            "enabled": bool(context.metadata.get("enabled", True)),
            "endpoint": "http://127.0.0.1:8765",
            "token_file": str(context.paths.data_dir / "local" / "server.token"),
            "memory_space_id": context.config.memory_space_id_for(self.id),
            "source_instance_id": f"hermes-{uuid4().hex}",
            "profile_id": "generation-operational",
            "state_db_path": str(home / "state.db"),
            "spool_dir": str(context.paths.integrations_dir / "hermes"),
            "runtime_endpoint": "http://127.0.0.1:8765",
            "runtime_command": str(context.paths.bin_link),
            "lease_ttl_seconds": context.config.runtime.lease_ttl_seconds,
            "heartbeat_seconds": context.config.runtime.heartbeat_seconds,
            "model_residency_mode": context.config.runtime.residency_mode,
            "session_safety_ttl_seconds": (
                context.config.runtime.session_safety_ttl_seconds
            ),
        }
        result = install_plugin(
            hermes_home=home,
            bundle_root=context.bundle_root,
            plugin_config=payload,
        )
        result["activation"] = self._set_plugin_enabled(
            context, enabled=bool(payload["enabled"])
        )
        result["hooks"] = self.register_hooks(context)
        return result

    def configure(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def register_hooks(self, context: AdapterContext) -> dict[str, Any]:
        return {
            **hook_registration(),
            "contract": lifecycle_contract(
                endpoint="http://127.0.0.1:8765",
                lease_ttl_seconds=context.config.runtime.lease_ttl_seconds,
                heartbeat_seconds=context.config.runtime.heartbeat_seconds,
                model_residency_mode=context.config.runtime.residency_mode,
                session_safety_ttl_seconds=(
                    context.config.runtime.session_safety_ttl_seconds
                ),
            ),
        }

    def verify(self, context: AdapterContext) -> dict[str, Any]:
        return verify_hermes_plugin(
            self._home(context) / "plugins" / "ledgermind-hermes",
            hermes_binary=shutil.which("hermes"),
            hermes_home=self._home(context),
        )

    def repair(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def uninstall(
        self, context: AdapterContext, *, purge: bool = False
    ) -> dict[str, Any]:
        from .uninstall import uninstall_plugin

        return uninstall_plugin(self._home(context), purge=purge)

    def runtime_environment(self, context: AdapterContext) -> dict[str, str]:
        return {
            "LEDGERMIND_HERMES_CONFIG": str(
                self._home(context) / "plugins" / "ledgermind-hermes" / "config.json"
            ),
            "LEDGERMIND_RUNTIME_ENDPOINT": "http://127.0.0.1:8765",
        }


__all__ = ["HermesTargetAdapter"]
