"""Transactional install orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config_writer import (
    build_local_config,
    persist_generation_probe,
    resolve_provider_tokens,
    resolve_reranker_token,
    write_installer_config,
    write_local_config,
    write_local_profiles,
)
from ..embeddings.model_download import download_model
from ..embeddings.runtime_install import install_runtime
from ..embeddings.verification import (
    verify_local_runtime_inference,
    verify_model_files,
)
from ..errors import ConfigurationError, InstallerError
from ..lock import InstallerLock
from ..manifest import InstallManifest
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..preflight import check_preflight
from ..profiles.embedding_local import build_local_embedding_plan
from ..profiles.generation import build_generation_profiles
from ..profiles.probes import probe_embedding_api, probe_generation
from ..transaction import InstallTransaction
from ..verify import (
    public_key_from_environment,
    sha256_file,
    verify_artifact_signature,
    verify_bundle_tree,
    verify_file,
)
from .common import (
    fetch_bundle,
    fetch_manifest,
    install_bin_link,
    platform_manifest,
    resolve_manifest,
    unpack_bundle,
    verify_manifest_signature,
    write_install_history,
)
from .doctor import doctor
from .integrations import connect_integration


def install_plan(
    config: InstallerConfig,
    *,
    paths: InstallerPaths,
    manifest: InstallManifest | None = None,
) -> dict[str, Any]:
    profiles = list(build_generation_profiles(config.generation))
    if config.embedding.mode == "api" and config.embedding.api is not None:
        profiles.append(
            {
                "profile_id": "embedding-default",
                "slot": "embedding",
                "endpoint": config.embedding.api.endpoint,
                "model": config.embedding.api.model,
                "dimensions": config.embedding.api.dimensions,
            }
        )
    else:
        assert config.embedding.local is not None
        if manifest is None:
            raise ConfigurationError(
                "local embeddings require a signed install manifest"
            )
        entry = manifest.catalog_entry(config.embedding.local.catalog_id)
        profiles.append(build_local_embedding_plan(config.embedding.local, entry))
    return {
        "integrations": [item.model_dump(mode="json") for item in config.integrations],
        "memory_mode": config.memory_mode,
        "platform": _platform_name(),
        "memory_data_path": config.memory_data_path or str(paths.memory_data_dir),
        "profiles": profiles,
        "reranker": config.reranker.model_dump(mode="json"),
        "runtime": config.runtime.model_dump(mode="json"),
        "release_version": manifest.release_version if manifest else None,
        "requires_signed_bundle": True,
    }


def _prepare_opt_in_reranker(
    config: InstallerConfig, paths: InstallerPaths,
    report: Callable[[str, str], None],
) -> InstallerConfig:
    """Never commit a configuration that would silently fall back forever."""
    if not config.reranker.enabled:
        return config
    try:
        from ledgermind_local.inference.retrieval_reranker import (
            ApiReranker,
            QwenWorkerReranker,
            Reranker,
        )

        scorer: Reranker
        if config.reranker.mode == "api":
            assert config.reranker.api is not None
            token = resolve_reranker_token(config, paths)
            assert token is not None
            report("reranker", "Checking reranker API")
            scorer = ApiReranker(
                config.reranker.api.endpoint,
                token,
                config.reranker.api.model,
                timeout_seconds=config.reranker.api.timeout_seconds,
            )
        else:
            model_path = config.reranker.model_path
            if not model_path or not config.reranker.runtime_path:
                raise ValueError(
                    "signed, separately installed reranker runtime is required"
                )
            report("reranker", "Checking separately installed local reranker")
            scorer = QwenWorkerReranker(
                model_path,
                config.reranker.device,
                runtime_path=config.reranker.runtime_path,
            )
        try:
            scores = scorer.score("installation check", ["content: installation check"])
        finally:
            scorer.close()
        if len(scores) != 1:
            raise ValueError("incomplete reranker smoke response")
        return config
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"reranker preflight failed ({type(exc).__name__}); "
            "check its API/runtime settings or select Core-only ranking"
        ) from exc


def _platform_name() -> str:
    from ..preflight import platform_id

    return platform_id()


def _download_progress(label: str, transferred: int, total: int | None) -> str:
    transferred_mib = transferred / (1024 * 1024)
    if total is None or total <= 0:
        return f"{label} · {transferred_mib:.1f} MiB"
    total_mib = total / (1024 * 1024)
    percent = min(100, transferred * 100 // total)
    width = 20
    filled = percent * width // 100
    bar = "━" * filled + "─" * (width - filled)
    return (
        f"{label}  {bar}  {percent:3d}%  "
        f"{transferred_mib:.1f}/{total_mib:.1f} MiB"
    )


def install(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    manifest_path: str | Path | None = None,
    bundle: str | Path | None = None,
    manifest_signature: str | Path | None = None,
    public_key: bytes | str | None = None,
    dry_run: bool = False,
    skip_provider_probe: bool = False,
    bundle_root_override: str | Path | None = None,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
    preserve_provider_credentials: bool = False,
    progress: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Install one release and return safe operation metadata."""

    paths.ensure()
    report = progress or (lambda _phase, _message: None)
    manifest, bundle_root = resolve_manifest(
        manifest_path, bundle_root_override or bundle
    )
    if dry_run:
        plan = install_plan(config, paths=paths, manifest=manifest)
        plan["status"] = "dry_run"
        return plan
    config = _prepare_opt_in_reranker(config, paths, report)
    if manifest is None:
        report("download", "Downloading the signed release manifest")
        fetched_manifest, fetched_signature, manifest = fetch_manifest(
            paths,
            public_key=public_key or public_key_from_environment(),
        )
        manifest_path = fetched_manifest
        manifest_signature = fetched_signature
    manifest_file = (
        Path(manifest_path).expanduser()
        if manifest_path
        else (Path(bundle_root) / "install-manifest.json" if bundle_root else None)
    )
    signature_file = (
        Path(manifest_signature).expanduser()
        if manifest_signature
        else (manifest_file.with_suffix(".sig") if manifest_file else None)
    )
    if manifest_file is None or signature_file is None or not signature_file.is_file():
        raise ConfigurationError("manifest signature is required")
    verify_manifest_signature(
        manifest_file, signature_file, public_key or public_key_from_environment()
    )
    release_record = platform_manifest(manifest)
    preflight = check_preflight(
        paths,
        required_bytes=release_record.bundle.size,
        minimum_glibc=release_record.bundle.minimum_glibc,
    )
    # Validate user-supplied provider settings before downloading or unpacking
    # the platform bundle. A bad endpoint/model should fail fast and cheaply.
    provider_probes: dict[str, Any] = {}
    if not skip_provider_probe:
        report("providers", "Checking generation and embedding providers")
        generation_token, embedding_token = resolve_provider_tokens(
            config,
            paths,
            generation_stdin=generation_stdin,
            embedding_stdin=embedding_stdin,
        )
        provider_probes["generation_probe"] = probe_generation(
            config.generation, token=generation_token
        )
        if config.embedding.mode == "api" and config.embedding.api is not None:
            assert embedding_token is not None
            provider_probes["embedding_probe"] = probe_embedding_api(
                config.embedding.api, token=embedding_token
            )
    report("verify", "Verifying release signatures and platform compatibility")
    if bundle_root is None:
        bundle_root = fetch_bundle(
            paths,
            manifest,
            public_key=public_key or public_key_from_environment(),
            progress=lambda transferred, total: report(
                "download",
                _download_progress("Signed runtime", transferred, total),
            ),
        )
    plan = install_plan(config, paths=paths, manifest=manifest)
    plan.update(provider_probes)
    bundle_source = Path(bundle_root)
    if bundle_source.is_file():
        bundle_record = platform_manifest(manifest).bundle
        verify_file(bundle_source, bundle_record)
        verify_artifact_signature(
            bundle_source,
            bundle_record,
            public_key=public_key or public_key_from_environment(),
        )
    bundle_path = unpack_bundle(bundle_root, paths.staging_dir / "bundle-unpacked")
    plan["bundle_verification"] = verify_bundle_tree(
        bundle_path, public_key=public_key or public_key_from_environment()
    )
    local_embedding_metadata: dict[str, Any] | None = None
    effective_config = config
    if config.embedding.mode == "local" and config.embedding.local is not None:
        report("embeddings", "Preparing the signed local embedding model")
        entry = manifest.catalog_entry(config.embedding.local.catalog_id)
        local_plan = build_local_embedding_plan(config.embedding.local, entry)
        if config.embedding.local.model_path is not None:
            model_path = Path(config.embedding.local.model_path).expanduser()
            if not model_path.is_file():
                raise ConfigurationError(
                    f"custom embedding model is missing: {model_path}"
                )
            catalog_compatibility = entry.get("runtime_compatibility")
            configured_compatibility = config.advanced.custom_runtime_compatibility
            if (
                catalog_compatibility is not None
                and str(catalog_compatibility) != configured_compatibility
            ):
                raise ConfigurationError(
                    "custom embedding runtime compatibility does not match catalog"
                )
            expected_digest = config.advanced.custom_model_sha256
            if (
                expected_digest is None
                or sha256_file(model_path).lower() != expected_digest.lower()
            ):
                raise ConfigurationError(
                    "custom embedding model SHA-256 does not match configuration"
                )
            local_plan["model"] = {
                "status": "passed",
                "source": "advanced-custom-model",
                "files_checked": 1,
                "sha256": expected_digest,
                "license": entry.get("license"),
            }
        else:
            model_dir = download_model(
                entry,
                paths,
                progress=lambda transferred, total: report(
                    "embeddings",
                    _download_progress("Nemotron model", transferred, total),
                ),
            )
            local_plan["model"] = verify_model_files(model_dir, entry)
            model_path = model_dir
        runtime_path = install_runtime(
            entry,
            device=str(local_plan["device"]),
            bundle_root=bundle_path,
            paths=paths,
        )
        local_plan["runtime"] = runtime_path
        local_plan["inference_smoke"] = verify_local_runtime_inference(
            runtime_path=runtime_path,
            model_path=model_path,
            device=str(local_plan["device"]),
            dimensions=int(local_plan["dimensions"]),
        )
        effective_config = config.model_copy(
            update={
                "embedding": config.embedding.model_copy(
                    update={
                        "local": config.embedding.local.model_copy(
                            update={
                                "device": local_plan["device"],
                                "model_storage_path": str(model_path),
                                "runtime_id": str(local_plan["runtime_id"]),
                                "runtime_path": str(runtime_path),
                                "dimensions": int(local_plan["dimensions"]),
                            }
                        )
                    }
                )
            }
        )
        local_embedding_metadata = local_plan
    release_dir = paths.release_dir(manifest.release_version)
    platform_config = effective_config.model_copy(update={"integrations": ()})
    local_database_path = Path(
        build_local_config(platform_config, paths).rounds_database_path
    )
    doctor_report: dict[str, Any] = {}
    report("install", "Installing the local runtime")
    with (
        InstallerLock(paths.install_lock),
        InstallTransaction(
            paths, release_version=manifest.release_version
        ) as transaction,
    ):
        staged = transaction.copy_bundle(bundle_path)
        transaction.write_marker(
            {
                "release_version": manifest.release_version,
                "platform": preflight["platform"],
            }
        )
        transaction.commit(staged_bundle=staged, switch_current=False)
        try:
            for path in (
                paths.config_file,
                paths.profiles_file,
                paths.secrets_file,
                paths.config_dir / "local-config.json",
                paths.data_dir / "local" / "config.json",
                paths.data_dir / "local" / "server.token",
                paths.data_dir / "embedding" / "server.token",
                local_database_path,
                Path(f"{local_database_path}-wal"),
                Path(f"{local_database_path}-shm"),
            ):
                transaction.backup_file(path)
            config_metadata = write_installer_config(
                platform_config,
                paths,
                generation_stdin=generation_stdin,
                embedding_stdin=embedding_stdin,
                preserve_provider_credentials=preserve_provider_credentials,
            )
            config_metadata["local_config"] = str(
                write_local_config(platform_config, paths, release_dir=release_dir)
            )
            config_metadata["local_profiles"] = write_local_profiles(
                platform_config, paths
            )
            if not skip_provider_probe:
                config_metadata["generation_capabilities"] = persist_generation_probe(
                    platform_config,
                    paths,
                    provider_probes["generation_probe"],
                )
            transaction.switch_current()
            install_bin_link(paths)
            doctor_report = doctor(
                paths=paths,
                full_smoke=True,
                # Providers were already validated before any download. Do
                # not spend more API calls repeating the same probe here.
                probe_providers=False,
                verify_integrations=False,
            )
            if doctor_report.get("status") != "passed":
                raise InstallerError("post-install doctor or sandbox smoke failed")
        except Exception:
            transaction.rollback()
            transaction.restore_backups()
            raise
    integration_results: dict[str, Any] = {}
    integration_failures: list[str] = []
    report("agents", "Connecting selected agents")
    for selected in effective_config.integrations:
        try:
            integration_results[selected.id] = connect_integration(
                paths=paths, target_id=selected.id, enabled=selected.enabled
            )
        except Exception as exc:  # noqa: BLE001
            integration_results[selected.id] = {
                "status": "failed",
                "error": str(exc),
            }
            integration_failures.append(selected.id)
    write_install_history(
        paths,
        {
            "operation": "install",
            "release_version": manifest.release_version,
            "platform": preflight["platform"],
            "timestamp": time.time(),
            "current": str(paths.current_link),
        },
    )
    report("complete", "Installation completed")
    connected_agents = sum(
        1
        for item in integration_results.values()
        if isinstance(item, dict) and item.get("status") == "passed"
    )
    total_agents = len(effective_config.integrations)
    generation_status = (
        "skipped"
        if skip_provider_probe
        else str(provider_probes.get("generation_probe", {}).get("status", "passed"))
    )
    if effective_config.embedding.mode == "local":
        embedding_status = "local-ready"
    elif skip_provider_probe:
        embedding_status = "skipped"
    else:
        embedding_status = str(
            provider_probes.get("embedding_probe", {}).get("status", "passed")
        )
    generation_route = " -> ".join(
        item
        for item in (
            effective_config.generation.route,
            *effective_config.generation.fallback_routes,
        )
        if item
    )
    generation_readiness = (
        f"{generation_status}; model={effective_config.generation.model}"
        + (f"; route={generation_route}" if generation_route else "")
    )
    if effective_config.embedding.mode == "api":
        assert effective_config.embedding.api is not None
        embedding_readiness = (
            f"{embedding_status}; model={effective_config.embedding.api.model}; "
            f"dimensions={effective_config.embedding.api.dimensions}"
        )
    else:
        assert effective_config.embedding.local is not None
        embedding_readiness = (
            f"{embedding_status}; model={effective_config.embedding.local.catalog_id}"
        )
    readiness = {
        "platform": preflight["platform"],
        "core": doctor_report.get("status", "unknown"),
        "generation": generation_readiness,
        "embeddings": embedding_readiness,
        "reranker": (
            (
                f"local-ready; model=Qwen3-Reranker-0.6B; "
                f"device={effective_config.reranker.device}"
            )
            if effective_config.reranker.mode == "local"
            else (
                f"api-ready; model={effective_config.reranker.api.model}"
                if effective_config.reranker.api is not None
                else "disabled; Core ranking"
            )
        ),
        "smoke_test": doctor_report.get("smoke_test", {}).get("status", "unknown"),
        "agents": f"{connected_agents}/{total_agents} connected"
        if total_agents
        else "none selected",
        "memory_mode": effective_config.memory_mode,
    }
    return {
        "status": "partial" if integration_failures else "success",
        "release_version": manifest.release_version,
        "platform": preflight["platform"],
        "preflight": preflight,
        "plan": plan,
        "local_embedding": local_embedding_metadata,
        "config": config_metadata,
        "integrations": integration_results,
        "integration_failures": integration_failures,
        "doctor": doctor_report,
        "smoke_test": doctor_report.get("smoke_test", {}),
        "current": str(paths.current_link),
        "release_dir": str(release_dir),
        "doctor_required": True,
        "smoke_test_required": True,
        "readiness": readiness,
    }


__all__ = ["install", "install_plan"]
