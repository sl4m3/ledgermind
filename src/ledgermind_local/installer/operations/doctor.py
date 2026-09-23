"""Full release/configuration/provider/runtime diagnostic report."""

from __future__ import annotations

from typing import Any

from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from ..config_writer import (
    load_installer_config,
    resolve_provider_tokens,
    select_secret_backend,
)
from ..paths import InstallerPaths
from ..permissions import assert_private
from ..preflight import platform_id
from ..profiles.probes import probe_embedding_api, probe_generation
from ..smoke import run_sandbox_smoke
from ..targets.base import AdapterContext
from ..targets.registry import get_target_adapter
from ..verify import verify_bundle_tree


def doctor(
    *,
    paths: InstallerPaths,
    full_smoke: bool = True,
    probe_providers: bool = True,
    verify_integrations: bool = True,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "passed",
        "platform": None,
        "delivery": {},
        "configuration": {},
        "providers": {},
        "runtime": {},
        "integrations": {},
        "smoke_test": {},
        "warnings": [],
    }
    try:
        report["platform"] = platform_id()
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["warnings"].append(str(exc))
    current = paths.current_link
    if not current.is_symlink() or not current.exists():
        report["status"] = "failed"
        report["delivery"]["current"] = "missing"
    else:
        bundle_manifest = current / "bundle-manifest.json"
        report["delivery"] = {
            "current": str(current.resolve()),
            "bundle_manifest": bundle_manifest.is_file(),
            "core": (current / "bin" / "ledgermind-core").is_file(),
            "local": (current / "bin" / "ledgermind-local").is_file(),
            "installer": (current / "bin" / "ledgermind").is_file(),
        }
        try:
            report["delivery"]["signature"] = verify_bundle_tree(current)
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["delivery"]["signature"] = {
                "status": "failed",
                "error": str(exc),
            }
    try:
        for path in (paths.config_dir, paths.state_dir, paths.data_dir):
            assert_private(path, directory=True)
        report["configuration"]["permissions"] = "passed"
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["configuration"]["permissions"] = str(exc)
    if paths.config_file.is_file():
        try:
            config = load_installer_config(paths.config_file)
            report["configuration"]["schema"] = "passed"
            backend = select_secret_backend(paths)
            report["configuration"]["secret_store"] = (
                "secret-service"
                if backend.__class__.__name__ == "SecretServiceStore"
                else "file-0600"
            )
            report["configuration"]["integrations"] = [
                item.model_dump(mode="json") for item in config.integrations
            ]
            for path in (
                paths.config_file,
                paths.profiles_file,
                paths.config_dir / "runtime.token",
                paths.data_dir / "local" / "server.token",
            ):
                if not path.is_file():
                    raise FileNotFoundError(f"required private file is missing: {path}")
                assert_private(path, directory=False)
                if path.name.endswith(".token") and not path.read_text(
                    encoding="utf-8"
                ).strip():
                    raise ValueError(f"required token is empty: {path}")
            for selected in config.integrations:
                adapter = get_target_adapter(selected.id)
                discovery = adapter.discover()
                integration = {
                    "connected": True,
                    "enabled": selected.enabled,
                    "discovery": discovery.as_dict(),
                }
                report["integrations"][selected.id] = integration
                if not verify_integrations:
                    integration["adapter"] = {"status": "skipped_by_request"}
                    continue
                if not discovery.detected:
                    report["status"] = "failed"
                    integration["adapter"] = {
                        "status": "failed",
                        "error": discovery.detail or "agent was not discovered",
                    }
                    continue
                context = AdapterContext(config=config, paths=paths, discovery=discovery)
                try:
                    integration["adapter"] = adapter.verify(context)
                except Exception as exc:  # noqa: BLE001
                    report["status"] = "failed"
                    integration["adapter"] = {
                        "status": "failed",
                        "error": str(exc),
                    }
            if probe_providers:
                try:
                    generation_token, embedding_token = resolve_provider_tokens(
                        config, paths
                    )
                    report["providers"]["generation"] = probe_generation(
                        config.generation, token=generation_token
                    )
                    if (
                        config.embedding.mode == "api"
                        and config.embedding.api is not None
                    ):
                        assert embedding_token is not None
                        report["providers"]["embedding"] = probe_embedding_api(
                            config.embedding.api, token=embedding_token
                        )
                    else:
                        report["providers"]["embedding"] = {
                            "status": "local-runtime-configured"
                        }
                except Exception as exc:  # noqa: BLE001
                    report["status"] = "failed"
                    report["providers"] = {"status": "failed", "error": str(exc)}
            else:
                report["providers"] = {"status": "skipped_by_request"}
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["configuration"]["schema"] = {"status": "failed", "error": str(exc)}
    else:
        report["status"] = "failed"
        report["configuration"]["schema"] = "missing"
    runtime = RuntimeSupervisor(paths).status()
    report["runtime"] = runtime
    if not report["providers"]:
        report["providers"] = {"status": "not_configured"}
    if full_smoke and report["status"] == "passed":
        try:
            report["smoke_test"] = run_sandbox_smoke(paths)
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["smoke_test"] = {"status": "failed", "error": str(exc)}
    else:
        report["smoke_test"] = {"status": "skipped", "writes_user_memory": False}
    return report


__all__ = ["doctor"]
