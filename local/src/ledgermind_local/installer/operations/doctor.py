"""Full release/configuration/provider/runtime diagnostic report."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ledgermind_local.config import LocalConfig
from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from ..config_writer import (
    load_installer_config,
    resolve_decision_token,
    resolve_provider_tokens,
    select_secret_backend,
)
from ..paths import InstallerPaths
from ..permissions import assert_private
from ..preflight import platform_id
from ..profiles.probes import (
    probe_embedding_api,
    probe_generation,
    probe_resolution_decision,
)
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
            local_config: LocalConfig | None = None
            try:
                local_config_paths = (
                    paths.config_dir / "local-config.json",
                    paths.data_dir / "local" / "config.json",
                )
                parsed_locals: list[LocalConfig] = []
                for path in local_config_paths:
                    if not path.is_file():
                        raise FileNotFoundError(
                            f"required local config is missing: {path}"
                        )
                    assert_private(path, directory=False)
                    parsed_locals.append(
                        LocalConfig.model_validate_json(
                            path.read_text(encoding="utf-8")
                        )
                    )
                if parsed_locals[0].model_dump(mode="json") != parsed_locals[
                    1
                ].model_dump(mode="json"):
                    raise ValueError(
                        "local-config.json and data/local/config.json differ"
                    )
                local_config = parsed_locals[0]
                if local_config.core_security.profile != "secure":
                    raise ValueError("core_security.profile must be 'secure'")
                if local_config.semantic_language != config.semantic_language:
                    raise ValueError(
                        "local semantic_language does not match installer config"
                    )
                if (
                    local_config.generation_concurrency
                    != config.generation.max_concurrency
                ):
                    raise ValueError(
                        "local generation_concurrency does not match installer config"
                    )
                if current.is_symlink() and current.exists():
                    core_bin = Path(local_config.core_binary_path).expanduser()
                    core_sig = Path(local_config.core_signature_path).expanduser()
                    core_pub = Path(local_config.core_public_key_path).expanduser()
                    for artifact in (core_bin, core_sig, core_pub):
                        if not artifact.is_file():
                            raise FileNotFoundError(
                                f"configured Core artifact is missing: {artifact}"
                            )
                    if not os.access(core_bin, os.X_OK):
                        raise PermissionError(
                            f"configured Core binary is not executable: {core_bin}"
                        )
                report["configuration"]["local_config"] = "passed"
                report["configuration"]["core_config"] = {
                    "security_profile": local_config.core_security.profile,
                    "semantic_language": local_config.semantic_language,
                    "generation_concurrency": local_config.generation_concurrency,
                    "embedding_max_concurrency": local_config.embedding.max_concurrency,
                    "resolution_decision_slot": (
                        local_config.profile_slots.resolution_decision
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                report["status"] = "failed"
                report["configuration"]["local_config"] = {
                    "status": "failed",
                    "error": str(exc),
                }

            if local_config is not None:
                try:
                    rounds_db = Path(
                        local_config.rounds_database_path
                    ).expanduser()
                    if not rounds_db.is_file():
                        raise FileNotFoundError(
                            f"rounds database is missing: {rounds_db}"
                        )
                    required_slots = {
                        "operational": local_config.profile_slots.operational,
                        "object_resolution": (
                            local_config.profile_slots.object_resolution
                        ),
                        "background": local_config.profile_slots.background,
                        "embedding": local_config.profile_slots.embedding,
                    }
                    if local_config.profile_slots.resolution_decision is not None:
                        required_slots["resolution_decision"] = (
                            local_config.profile_slots.resolution_decision
                        )
                    spaces = (
                        [config.memory_space_id_for("hermes")]
                        if config.memory_mode == "shared"
                        else sorted(
                            {
                                config.memory_space_id_for(target)
                                for target in (
                                    "hermes",
                                    *(item.id for item in config.integrations),
                                )
                            }
                        )
                    )
                    with closing(
                        sqlite3.connect(f"file:{rounds_db}?mode=ro", uri=True)
                    ) as conn:
                        profiles = {
                            str(row[0])
                            for row in conn.execute(
                                "SELECT profile_id FROM inference_profiles"
                            ).fetchall()
                        }
                        bindings = {
                            (str(row[0]), str(row[1])): str(row[2])
                            for row in conn.execute(
                                "SELECT memory_space_id, profile_slot, profile_id "
                                "FROM memory_space_model_profiles"
                            ).fetchall()
                        }
                    missing_slots: list[str] = []
                    for space in spaces:
                        for slot, expected_profile in required_slots.items():
                            bound = bindings.get((space, slot))
                            if bound is None:
                                missing_slots.append(f"{space}:{slot}:unbound")
                            elif (
                                expected_profile is not None
                                and bound != expected_profile
                            ):
                                missing_slots.append(
                                    f"{space}:{slot}:mismatch({bound}!={expected_profile})"
                                )
                            elif bound not in profiles:
                                missing_slots.append(
                                    f"{space}:{slot}:missing_profile({bound})"
                                )
                    if missing_slots:
                        raise ValueError(
                            "missing materialized profile slots: "
                            + ", ".join(missing_slots)
                        )
                    report["configuration"]["profile_slots"] = "passed"
                except Exception as exc:  # noqa: BLE001
                    report["status"] = "failed"
                    report["configuration"]["profile_slots"] = {
                        "status": "failed",
                        "error": str(exc),
                    }
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
                    if config.resolution_decision is not None:
                        report["providers"]["resolution_decision"] = probe_resolution_decision(
                            config, token=resolve_decision_token(config, paths)
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
