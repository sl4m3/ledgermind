"""Public ``ledgermind`` installer command surface."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from .errors import (
    ConfigurationError,
    ExitCode,
    InstallerError,
    ProviderProbeError,
    UserCancelledError,
)
from .models import InstallerConfig
from .non_interactive import load_non_interactive_config
from .operations.configure import configure
from .operations.doctor import doctor
from .operations.export_config import export_config
from .operations.import_config import import_config
from .operations.install import install, install_plan
from .operations.integrations import (
    connect_integration,
    disconnect_integration,
    discover_integrations,
    integration_status,
    set_integration_enabled,
)
from .operations.repair import repair
from .operations.status import status
from .operations.uninstall import uninstall
from .operations.update import update
from .paths import InstallerPaths
from .result import InstallResult, ResultStep
from .schema import schema
from .targets.registry import target_ids


def _record_integration_hook_failure(
    config_path: Path, event: str, exc: BaseException
) -> Path | None:
    """Record a redacted hook failure without exposing prompts or credentials."""

    diagnostic_path = config_path.parent / "hook-errors.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "event": event,
        "error_type": type(exc).__name__,
        "error": str(exc)[:1000],
    }
    encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        diagnostic_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            diagnostic_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, encoded)
        finally:
            os.close(descriptor)
        os.chmod(diagnostic_path, 0o600)
    except OSError:
        return None
    return diagnostic_path


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--home", type=Path, help="test/rootless home override")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledgermind", description="LedgerMind universal installer"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install")
    install_subparsers = install_parser.add_subparsers(dest="install_command")
    schema_parser = install_subparsers.add_parser("schema")
    schema_parser.add_argument(
        "--name",
        choices=("install-config", "install-manifest", "install-result"),
        default="install-config",
    )
    schema_parser.add_argument("--json", action="store_true", dest="json_output")
    plan_parser = install_subparsers.add_parser("plan")
    _common(plan_parser)
    plan_parser.add_argument("--manifest", type=Path)
    for option in (install_parser,):
        _common(option)
        option.add_argument("--manifest", type=Path)
        option.add_argument("--bundle", type=Path)
        option.add_argument("--manifest-signature", type=Path)
        option.add_argument("--skip-provider-probe", action="store_true")
        option.add_argument(
            "--existing-mode",
            choices=("add-agent", "update", "repair", "reconfigure", "exit"),
            help="safe action when LedgerMind is already installed",
        )
        option.add_argument(
            "--agent",
            action="append",
            choices=target_ids(),
            default=[],
            help="agent to connect with --existing-mode add-agent",
        )

    configure_parser = subparsers.add_parser("configure")
    _common(configure_parser)
    configure_parser.add_argument("--validate-providers", action="store_true")

    doctor_parser = subparsers.add_parser("doctor")
    _common(doctor_parser)
    doctor_parser.add_argument("--no-smoke", action="store_true")

    repair_parser = subparsers.add_parser("repair")
    _common(repair_parser)

    update_parser = subparsers.add_parser("update")
    _common(update_parser)
    update_parser.add_argument("--manifest", type=Path, required=True)
    update_parser.add_argument("--bundle", type=Path, required=True)
    update_parser.add_argument("--skip-provider-probe", action="store_true")

    uninstall_parser = subparsers.add_parser("uninstall")
    _common(uninstall_parser)
    uninstall_parser.add_argument("--purge-data", action="store_true")
    uninstall_parser.add_argument("--purge-config", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")

    status_parser = subparsers.add_parser("status")
    _common(status_parser)

    integrations_parser = subparsers.add_parser("integrations")
    integration_commands = integrations_parser.add_subparsers(
        dest="integration_command", required=True
    )
    integrations_discover = integration_commands.add_parser("discover")
    _common(integrations_discover)
    integrations_status = integration_commands.add_parser("status")
    _common(integrations_status)
    integrations_connect = integration_commands.add_parser("connect")
    _common(integrations_connect)
    integrations_connect.add_argument("integration", choices=target_ids())
    integrations_connect.add_argument("--disabled", action="store_true")
    for action in ("enable", "disable", "disconnect"):
        action_parser = integration_commands.add_parser(action)
        _common(action_parser)
        action_parser.add_argument("integration", choices=target_ids())

    export_parser = subparsers.add_parser("export-config")
    _common(export_parser)
    export_parser.add_argument("--out", type=Path, required=True)
    export_parser.add_argument("--include-secrets", action="store_true")

    import_parser = subparsers.add_parser("import-config")
    _common(import_parser)
    import_parser.add_argument("--file", type=Path, required=True)
    import_parser.add_argument("--validate-providers", action="store_true")
    import_parser.add_argument("--register-target", action="store_true")
    import_parser.add_argument("--delete-config-after-import", action="store_true")

    runtime_parser = subparsers.add_parser("runtime")
    _common(runtime_parser)
    runtime_subparsers = runtime_parser.add_subparsers(
        dest="runtime_command", required=True
    )

    def _runtime_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
        )
        command_parser.add_argument(
            "--non-interactive", action="store_true", default=argparse.SUPPRESS
        )
        command_parser.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        command_parser.add_argument(
            "--dry-run", action="store_true", default=argparse.SUPPRESS
        )
        command_parser.add_argument(
            "--verbose", action="store_true", default=argparse.SUPPRESS
        )
        command_parser.add_argument("--home", type=Path, default=argparse.SUPPRESS)

    acquire = runtime_subparsers.add_parser("acquire")
    _runtime_flags(acquire)
    acquire.add_argument("--client", required=True)
    acquire.add_argument("--session-id", required=True)
    acquire.add_argument("--ttl-seconds", type=float)
    heartbeat = runtime_subparsers.add_parser("heartbeat")
    _runtime_flags(heartbeat)
    heartbeat.add_argument("--lease-id", required=True)
    release = runtime_subparsers.add_parser("release")
    _runtime_flags(release)
    release.add_argument("--lease-id", required=True)
    runtime_status = runtime_subparsers.add_parser("status")
    _runtime_flags(runtime_status)
    stop = runtime_subparsers.add_parser("stop")
    _runtime_flags(stop)
    stop.add_argument("--force", action="store_true")
    idle_reap = runtime_subparsers.add_parser("_idle-reap", help=argparse.SUPPRESS)
    _runtime_flags(idle_reap)

    hook = subparsers.add_parser("integration-hook", help=argparse.SUPPRESS)
    hook.add_argument("--config", type=Path, required=True)
    hook.add_argument("--event", required=True)
    return parser


def _paths(args: argparse.Namespace) -> InstallerPaths:
    return InstallerPaths(home_override=getattr(args, "home", None))


def _runtime(paths: InstallerPaths) -> RuntimeSupervisor:
    config: InstallerConfig | None = None
    settings: dict[str, float] = {
        "idle_shutdown_seconds": 60.0,
        "lease_ttl_seconds": 30.0,
        "max_session_ttl_seconds": 3_600.0,
    }
    automatic_shutdown = True
    if paths.config_file.is_file():
        try:
            from .config_writer import load_installer_config

            config = load_installer_config(paths.config_file)
            settings.update(
                {
                    "idle_shutdown_seconds": (
                        config.runtime.idle_timeout_seconds
                        if config.runtime.residency_mode == "idle"
                        else 0.0
                    ),
                    "lease_ttl_seconds": config.runtime.lease_ttl_seconds,
                    "max_session_ttl_seconds": config.runtime.session_safety_ttl_seconds,
                }
            )
            automatic_shutdown = config.runtime.residency_mode != "always_on"
        except (OSError, ValueError):
            return RuntimeSupervisor(
                paths,
                idle_shutdown_seconds=settings["idle_shutdown_seconds"],
                lease_ttl_seconds=settings["lease_ttl_seconds"],
                max_session_ttl_seconds=settings["max_session_ttl_seconds"],
                residency_mode="idle",
            )
    local = paths.current_link / "bin" / "ledgermind-local"
    commands: dict[str, Sequence[str]] = {}
    if local.is_file() and local.stat().st_mode & 0o111:
        commands["local"] = (
            str(local),
            "--home",
            str(paths.data_dir / "local"),
            "serve",
        )
    if (
        config is not None
        and config.embedding.mode == "local"
        and config.embedding.local is not None
    ):
        from .hardware import choose_device

        local_config = config.embedding.local
        device: str = local_config.device
        if device == "auto":
            device = choose_device("auto", supported={"cpu", "cuda", "rocm"}).kind
        model_path = local_config.model_path or local_config.model_storage_path
        if model_path is None:
            model_path = str(paths.models_dir / local_config.catalog_id)
        runtime_path = (
            Path(local_config.runtime_path).expanduser()
            if local_config.runtime_path
            else None
        )
        runtime_python = runtime_path / "bin" / "python3" if runtime_path else None
        if runtime_python is None or not runtime_python.is_file():
            raise ConfigurationError(
                "signed local embedding runtime is missing; run ledgermind repair"
            )
        local_embedding_token_file = paths.data_dir / "embedding" / "server.token"
        if not local_embedding_token_file.is_file():
            raise ConfigurationError(
                "local embedding credential is missing; run ledgermind repair"
            )
        module_bootstrap = (
            "import runpy,sys;"
            f"sys.path[:0]=[{str(paths.current_link / 'python' / 'local')!r},"
            f"{str(paths.current_link / 'python' / 'site-packages')!r}];"
            "runpy.run_module('ledgermind_local.installer.embeddings.serve',"
            "run_name='__main__')"
        )
        commands["embedding"] = (
            str(runtime_python),
            "-c",
            module_bootstrap,
            "--model-path",
            str(Path(model_path).expanduser()),
            "--model",
            local_config.catalog_id,
            "--device",
            device,
            "--threads",
            str(local_config.threads or 4),
            "--gpu-layers",
            "99" if device != "cpu" else "0",
            "--dimensions",
            str(local_config.dimensions),
            "--port",
            "8766",
            "--token-file",
            str(local_embedding_token_file),
        )
    return RuntimeSupervisor(
        paths,
        idle_shutdown_seconds=settings["idle_shutdown_seconds"],
        lease_ttl_seconds=settings["lease_ttl_seconds"],
        automatic_shutdown=automatic_shutdown,
        max_session_ttl_seconds=settings["max_session_ttl_seconds"],
        residency_mode=(
            config.runtime.residency_mode if config is not None else "idle"
        ),
        commands=commands,
    )


def _normalize_argv(argv: Sequence[str]) -> list[str]:
    """Accept global options before the command as the legacy CLI did."""

    values = {"--home", "--config", "--manifest", "--bundle", "--manifest-signature"}
    raw = list(argv)
    if not raw or not raw[0].startswith("-"):
        return raw
    prefix: list[str] = []
    index = 0
    while index < len(raw) and raw[index].startswith("-"):
        option = raw[index]
        prefix.append(option)
        if option in values:
            index += 1
            if index >= len(raw):
                return raw
            prefix.append(raw[index])
        index += 1
    if index >= len(raw):
        return raw
    return [raw[index], *prefix, *raw[index + 1 :]]


def _config(args: argparse.Namespace) -> tuple[InstallerConfig, str | None, str | None]:
    if args.config is not None and args.non_interactive:
        return load_non_interactive_config(args.config)
    if args.config is not None:
        from .config_writer import load_installer_config

        try:
            return load_installer_config(args.config), None, None
        except (OSError, UnicodeError, ValueError) as exc:
            raise ConfigurationError("install config is invalid") from exc
    if args.non_interactive:
        raise InstallerError("--config is required in non-interactive mode")
    from .wizard import build_interactive_config

    embedding_catalog: Sequence[dict[str, object]] = ()
    if getattr(args, "manifest", None) is not None:
        from .manifest import load_manifest

        embedding_catalog = load_manifest(args.manifest).embedding_catalog
    else:
        try:
            from .operations.common import fetch_manifest
            from .verify import public_key_from_environment

            manifest_path, signature_path, manifest = fetch_manifest(
                _paths(args), public_key=public_key_from_environment()
            )
            args.manifest = manifest_path
            args.manifest_signature = signature_path
            embedding_catalog = manifest.embedding_catalog
        except InstallerError:
            # API embeddings remain available. A local option is never shown
            # without a verified signed catalog from this release.
            embedding_catalog = ()

    return (
        build_interactive_config(
            preflight_home=getattr(args, "home", None),
            embedding_catalog=embedding_catalog,
        ),
        None,
        None,
    )


def _existing_install(
    args: argparse.Namespace, paths: InstallerPaths
) -> dict[str, Any]:
    """Route a repeated install into one explicit, non-destructive operation."""

    from .config_writer import load_installer_config
    from .wizard import (
        build_interactive_config,
        choose_existing_install_action,
        choose_integrations_to_connect,
    )

    existing = load_installer_config(paths.config_file)
    mode = args.existing_mode
    if mode is None:
        if args.non_interactive:
            raise ConfigurationError(
                "LedgerMind is already installed; --existing-mode is required "
                "(add-agent, update, repair, reconfigure, or exit)"
            )
        mode = choose_existing_install_action()
    if mode == "exit":
        return {
            "status": "success",
            "existing_install_action": "exit",
            "readiness": {
                "platform": "linux",
                "core": "unchanged",
                "generation": "preserved",
                "embeddings": "preserved",
                "agents": "preserved",
                "memory_mode": existing.memory_mode,
            },
        }
    if mode == "update":
        from .operations.common import fetch_release
        from .verify import public_key_from_environment

        manifest_path, _signature_path, bundle_path = fetch_release(
            paths, public_key=public_key_from_environment()
        )
        return update(
            config=existing,
            paths=paths,
            manifest_path=manifest_path,
            bundle=bundle_path,
            skip_provider_probe=bool(args.skip_provider_probe),
            dry_run=bool(args.dry_run),
        )
    if mode == "repair":
        return repair(paths=paths, dry_run=bool(args.dry_run))
    if mode == "add-agent":
        selected = tuple(dict.fromkeys(args.agent))
        if not selected:
            if args.non_interactive:
                raise ConfigurationError(
                    "--agent is required with --existing-mode add-agent"
                )
            selected = choose_integrations_to_connect(existing)
        if not selected:
            raise ConfigurationError("no unconnected supported agents were selected")
        results: dict[str, Any] = {}
        failures: list[str] = []
        for target_id in selected:
            try:
                results[target_id] = connect_integration(
                    paths=paths,
                    target_id=target_id,
                    dry_run=bool(args.dry_run),
                )
            except Exception as exc:  # noqa: BLE001
                results[target_id] = {"status": "failed", "error": str(exc)}
                failures.append(target_id)
        return {
            "status": "partial" if failures else "success",
            "existing_install_action": "add-agent",
            "integrations": results,
            "integration_failures": failures,
            "readiness": {
                "platform": "linux",
                "core": "unchanged",
                "generation": "preserved",
                "embeddings": "preserved",
                "agents": f"{len(selected) - len(failures)}/{len(selected)} connected",
                "memory_mode": existing.memory_mode,
            },
        }
    if args.config is not None:
        candidate, generation_stdin, embedding_stdin = _config(args)
    else:
        if args.non_interactive:
            raise ConfigurationError(
                "--config is required with --existing-mode reconfigure"
            )
        embedding_catalog: Sequence[dict[str, object]] = ()
        try:
            from .operations.common import fetch_manifest
            from .verify import public_key_from_environment

            _manifest_path, _signature_path, manifest = fetch_manifest(
                paths, public_key=public_key_from_environment()
            )
            embedding_catalog = manifest.embedding_catalog
        except InstallerError:
            embedding_catalog = ()
        candidate = build_interactive_config(
            existing_config=existing,
            preflight_home=getattr(args, "home", None),
            embedding_catalog=embedding_catalog,
        )
        generation_stdin = None
        embedding_stdin = None
    # Reconfiguration owns provider identities only.  Agent selection, memory
    # topology, language, runtime settings, and storage paths remain stable.
    provider_config = existing.model_copy(
        update={
            "generation": candidate.generation,
            "embedding": candidate.embedding,
            "reranker": candidate.reranker,
        }
    )
    return configure(
        config=provider_config,
        paths=paths,
        validate_providers=True,
        generation_stdin=generation_stdin,
        embedding_stdin=embedding_stdin,
        dry_run=bool(args.dry_run),
    )


def _result(
    operation: str,
    *,
    payload: dict[str, Any] | None = None,
    paths: InstallerPaths | None = None,
) -> InstallResult:
    result = InstallResult(operation)
    if paths is not None:
        result.paths.update(paths.as_dict())
    if payload:
        for key in ("current", "release_dir", "config", "out", "plugin_root"):
            if key not in payload:
                continue
            value = payload[key]
            if key == "config" and isinstance(value, dict):
                result.paths["config_metadata"] = value
            else:
                result.paths[key] = value
        if "profiles" in payload and isinstance(payload["profiles"], list):
            result.profiles = payload["profiles"]
        elif isinstance(payload.get("plan"), dict) and isinstance(
            payload["plan"].get("profiles"), list
        ):
            result.profiles = payload["plan"]["profiles"]
        if "runtime" in payload and isinstance(payload["runtime"], dict):
            result.runtime = payload["runtime"]
        elif operation.startswith("runtime "):
            result.runtime = dict(payload)
        elif isinstance(payload.get("plan"), dict) and isinstance(
            payload["plan"].get("runtime"), dict
        ):
            result.runtime = payload["plan"]["runtime"]
        if "smoke_test" in payload and isinstance(payload["smoke_test"], dict):
            result.smoke_test = payload["smoke_test"]
        payload_status = payload.get("status")
        step_status = (
            payload_status
            if isinstance(payload_status, str)
            and payload_status in {"passed", "success", "partial", "dry_run", "failed"}
            else "passed"
        )
        result.steps.append(ResultStep(operation, step_status, data=dict(payload)))
        if step_status == "dry_run":
            result.status = "dry_run"
        elif step_status == "failed":
            result.status = "failed"
            result.exit_code = ExitCode.TRANSACTION_FAILED
        elif step_status == "partial":
            result.status = "partial"
            result.exit_code = ExitCode.ADAPTER_FAILED
            failures = payload.get("integration_failures", [])
            if failures:
                result.warning(
                    "platform installed; integrations failed: "
                    + ", ".join(str(item) for item in failures)
                )
    return result


def _emit(result: InstallResult, *, json_output: bool) -> int:
    if json_output:
        print(result.to_json())
    else:
        print(
            f"{result.operation}: {result.status} (exit_code={int(result.exit_code)})"
        )
        for step in result.steps:
            print(f"- {step.name}: {step.status}")
        _emit_integration_details(result)
        _emit_status_details(result)
        _emit_install_details(result)
        _emit_uninstall_details(result)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return int(result.exit_code)


def _emit_status_details(result: InstallResult) -> None:
    if result.operation != "status" or not result.steps:
        return
    health = result.steps[-1].data.get("memory_health")
    if not isinstance(health, dict):
        return
    print("\nMemory pipeline:")
    print(f"  Health:       {health.get('status', 'unknown')}")
    if health.get("last_successful_pipeline_at"):
        print(f"  Last success: {health['last_successful_pipeline_at']}")
    if health.get("last_materialized_at"):
        print(f"  Last write:   {health['last_materialized_at']}")
    if health.get("failed_batches_since_last_success") is not None:
        print(
            "  Failed since: "
            f"{health['failed_batches_since_last_success']} semantic batch(es)"
        )
    if health.get("normalization_rejections") is not None:
        print(
            "  Rejected:     "
            f"{health['normalization_rejections']} normalization command(s)"
        )
    latest = health.get("latest_failure")
    if isinstance(latest, dict) and latest.get("error_code"):
        print(f"  Latest error: {latest['error_code']}")


def _emit_integration_details(result: InstallResult) -> None:
    if result.operation not in {
        "integrations discover",
        "integrations status",
        "integrations connect",
        "integrations enable",
        "integrations disable",
        "integrations disconnect",
    }:
        return
    if result.operation not in {"integrations discover", "integrations status"}:
        step = result.steps[-1] if result.steps else None
        if step is None:
            return
        data = step.data
        summary = data.get("summary")
        if not isinstance(summary, dict):
            return
        print("\nIntegration result:")
        print(
            f"  Agent:        {summary.get('label', data.get('integration', 'unknown'))}"
        )
        if summary.get("agent_location"):
            print(f"  Location:     {summary['agent_location']}")
        print(f"  Connected:    {'yes' if summary.get('connected') else 'no'}")
        print(f"  Enabled:      {'yes' if summary.get('enabled') else 'no'}")
        if summary.get("verification"):
            print(f"  Verification: {summary['verification']}")
        if summary.get("memory_space_id"):
            print(f"  Memory space: {summary['memory_space_id']}")
        print("  Models:       preserved")
        activation = summary.get("activation_required")
        if activation:
            print(f"  Next step:    {activation}")
        else:
            print("  Next step:    send a message to the agent")
        return
    step = next(
        (
            item
            for item in result.steps
            if isinstance(item.data.get("integrations"), dict)
        ),
        None,
    )
    if step is None:
        return
    integrations = step.data["integrations"]
    heading = (
        "Detected agents:"
        if result.operation == "integrations discover"
        else "Agent integrations:"
    )
    print(f"\n{heading}")
    for target_id, raw_item in integrations.items():
        if not isinstance(raw_item, dict):
            continue
        discovery = (
            raw_item.get("discovery", raw_item)
            if result.operation == "integrations status"
            else raw_item
        )
        if not isinstance(discovery, dict):
            discovery = {}
        label = str(discovery.get("label") or target_id)
        detected = bool(discovery.get("detected"))
        if result.operation == "integrations discover":
            location = discovery.get("config_dir") or discovery.get("home")
            detail = str(discovery.get("detail") or "").strip()
            suffix = f" — {location}" if detected and location else ""
            if not detected and detail:
                suffix = f" — {detail}"
            print(
                f"  {label} ({target_id}): "
                f"{'found' if detected else 'not found'}{suffix}"
            )
            continue
        fields = [
            f"detected={'yes' if detected else 'no'}",
            f"connected={'yes' if raw_item.get('connected') else 'no'}",
            f"enabled={'yes' if raw_item.get('enabled') else 'no'}",
        ]
        verification = raw_item.get("verify")
        if isinstance(verification, dict) and verification.get("status"):
            fields.append(f"verify={verification['status']}")
        print(f"  {label} ({target_id}): {', '.join(fields)}")
        if not detected and discovery.get("detail"):
            print(f"    {discovery['detail']}")
        if isinstance(verification, dict) and verification.get("activation_required"):
            print(f"    note: {verification['activation_required']}")


def _emit_install_details(result: InstallResult) -> None:
    if result.operation not in {"install", "configure", "repair", "update"}:
        return
    step = result.steps[-1] if result.steps else None
    if step is None:
        return
    readiness = step.data.get("readiness")
    if not isinstance(readiness, dict):
        return
    print("\n8/8  COMPLETE")
    print("Readiness:")
    for label, key in (
        ("Platform", "platform"),
        ("Core", "core"),
        ("Generation", "generation"),
        ("Embeddings", "embeddings"),
        ("Smoke test", "smoke_test"),
        ("Agents", "agents"),
        ("Memory", "memory_mode"),
    ):
        value = readiness.get(key)
        if value is not None:
            print(f"  {label + ':':12} {value}")
    print("  Diagnose:    ledgermind doctor")


def _emit_uninstall_details(result: InstallResult) -> None:
    if result.operation != "uninstall" or not result.steps:
        return
    data = result.steps[-1].data
    print("\nRemoval result:")
    print(f"  Memory:      {'preserved' if data.get('preserved_data') else 'removed'}")
    print(
        f"  Config:      {'preserved' if data.get('preserved_config') else 'removed'}"
    )
    backup = data.get("memory_backup")
    if backup:
        print(f"  Backup:      {backup}")
    elif data.get("backup_status"):
        print(f"  Backup:      {data['backup_status']}")


def _terminal_progress(phase: str, message: str) -> None:
    """Render installation phases as one stable terminal status line."""

    labels = {
        "providers": "CHECK",
        "download": "FETCH",
        "verify": "VERIFY",
        "embeddings": "MODEL",
        "install": "INSTALL",
        "agents": "AGENTS",
        "complete": "DONE",
    }
    stage = "8/8" if phase == "complete" else "7/8"
    previous = getattr(_terminal_progress, "phase", None)
    if previous is not None and previous != phase:
        print(file=sys.stderr)
    print(
        f"\r\033[2K  {stage} [{labels.get(phase, phase.upper())}] {message}",
        end="\n" if phase == "complete" else "",
        file=sys.stderr,
        flush=True,
    )
    _terminal_progress.phase = phase  # type: ignore[attr-defined]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv:
        raw_argv = ["install"]
    args = parser.parse_args(_normalize_argv(raw_argv))
    operation = args.command
    try:
        if operation == "integration-hook":
            try:
                lifecycle = importlib.import_module(
                    "ledgermind_integrations.adapters.lifecycle"
                )
                payload = json.load(sys.stdin)
                if not isinstance(payload, dict):
                    payload = {}
                response = lifecycle.handle_hook(
                    lifecycle.load_lifecycle_config(args.config), args.event, payload
                )
            except Exception as exc:  # noqa: BLE001 -- hooks must never break the agent
                diagnostic_path = _record_integration_hook_failure(
                    args.config, args.event, exc
                )
                location = (
                    f"; diagnostic: {diagnostic_path}"
                    if diagnostic_path is not None
                    else ""
                )
                print(
                    f"ledgermind: {args.event} hook failed: "
                    f"{type(exc).__name__}: {str(exc)[:500]}{location}",
                    file=sys.stderr,
                )
                response = {}
            if response:
                context = response.get("additional_context")
                if isinstance(context, str) and context:
                    response = {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": context,
                        }
                    }
                print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
            return 0
        paths = _paths(args)
        if operation == "install" and args.install_command == "schema":
            result = _result("install schema", payload=schema(args.name))
            return _emit(result, json_output=bool(args.json_output))
        if operation == "install" and args.install_command == "plan":
            config, _, _ = _config(args)
            manifest = None
            if args.manifest:
                from .manifest import load_manifest

                manifest = load_manifest(args.manifest)
            result = _result(
                "install plan",
                payload=install_plan(config, paths=paths, manifest=manifest),
                paths=paths,
            )
            return _emit(result, json_output=bool(args.json_output))
        if operation == "install":
            if paths.config_file.is_file():
                payload = _existing_install(args, paths)
                result = _result("install", payload=payload, paths=paths)
                return _emit(result, json_output=bool(args.json_output))
            config, generation_stdin, embedding_stdin = _config(args)
            interactive_progress = (
                _terminal_progress
                if not bool(args.non_interactive) and not bool(args.json_output)
                else None
            )
            if interactive_progress is not None:
                _terminal_progress.phase = None  # type: ignore[attr-defined]
            while True:
                try:
                    payload = install(
                        config=config,
                        paths=paths,
                        manifest_path=args.manifest,
                        bundle=args.bundle,
                        manifest_signature=args.manifest_signature,
                        dry_run=bool(args.dry_run),
                        skip_provider_probe=bool(args.skip_provider_probe),
                        generation_stdin=generation_stdin,
                        embedding_stdin=embedding_stdin,
                        progress=interactive_progress,
                    )
                    break
                except ProviderProbeError as exc:
                    if bool(args.non_interactive) or bool(args.json_output):
                        raise
                    print(f"\n  Provider check failed: {exc}", file=sys.stderr)
                    print(
                        "  No files were installed. Review the provider settings and retry.",
                        file=sys.stderr,
                    )
                    from .wizard import build_interactive_config

                    retry_catalog: Sequence[dict[str, object]] = ()
                    if args.manifest is not None:
                        from .manifest import load_manifest

                        retry_catalog = load_manifest(args.manifest).embedding_catalog

                    config = build_interactive_config(
                        existing_config=config,
                        preflight_home=getattr(args, "home", None),
                        embedding_catalog=retry_catalog,
                    )
                    generation_stdin = None
                    embedding_stdin = None
            result = _result("install", payload=payload, paths=paths)
            return _emit(result, json_output=bool(args.json_output))
        if operation == "configure":
            config, generation_stdin, embedding_stdin = _config(args)
            payload = configure(
                config=config,
                paths=paths,
                validate_providers=bool(args.validate_providers),
                generation_stdin=generation_stdin,
                embedding_stdin=embedding_stdin,
                dry_run=bool(args.dry_run),
            )
            return _emit(
                _result("configure", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "doctor":
            payload = doctor(paths=paths, full_smoke=not bool(args.no_smoke))
            result = _result("doctor", payload=payload, paths=paths)
            if payload.get("status") != "passed":
                result.fail(ExitCode.DOCTOR_FAILED, "doctor found failures")
            return _emit(result, json_output=bool(args.json_output))
        if operation == "repair":
            payload = repair(paths=paths, dry_run=bool(args.dry_run))
            result = _result("repair", payload=payload, paths=paths)
            if payload.get("status") == "failed":
                result.fail(ExitCode.DOCTOR_FAILED, "repair verification failed")
            return _emit(result, json_output=bool(args.json_output))
        if operation == "update":
            if args.config is not None:
                raise ConfigurationError(
                    "update preserves provider configuration; use configure to change it"
                )
            if not paths.config_file.is_file():
                raise ConfigurationError("LedgerMind must be installed before update")
            from .config_writer import load_installer_config

            config = load_installer_config(paths.config_file)
            payload = update(
                config=config,
                paths=paths,
                manifest_path=args.manifest,
                bundle=args.bundle,
                dry_run=bool(args.dry_run),
                skip_provider_probe=bool(args.skip_provider_probe),
                generation_stdin=None,
                embedding_stdin=None,
            )
            return _emit(
                _result("update", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "uninstall":
            payload = uninstall(
                paths=paths,
                purge_data=bool(args.purge_data),
                purge_config=bool(args.purge_config),
                yes=bool(args.yes),
                dry_run=bool(args.dry_run),
            )
            return _emit(
                _result("uninstall", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "status":
            return _emit(
                _result("status", payload=status(paths=paths), paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "integrations":
            if args.integration_command == "discover":
                payload = discover_integrations()
            elif args.integration_command == "status":
                payload = integration_status(paths=paths)
            elif args.integration_command == "connect":
                payload = connect_integration(
                    paths=paths,
                    target_id=args.integration,
                    enabled=not bool(args.disabled),
                    dry_run=bool(args.dry_run),
                )
            elif args.integration_command == "disconnect":
                payload = disconnect_integration(
                    paths=paths,
                    target_id=args.integration,
                    dry_run=bool(args.dry_run),
                )
            else:
                payload = set_integration_enabled(
                    paths=paths,
                    target_id=args.integration,
                    enabled=args.integration_command == "enable",
                    dry_run=bool(args.dry_run),
                )
            return _emit(
                _result(
                    "integrations " + args.integration_command,
                    payload=payload,
                    paths=paths,
                ),
                json_output=bool(args.json_output),
            )
        if operation == "export-config":
            payload = export_config(
                paths=paths, out=args.out, include_secrets=bool(args.include_secrets)
            )
            return _emit(
                _result("export-config", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "import-config":
            payload = import_config(
                paths=paths,
                file=args.file,
                validate_providers=bool(args.validate_providers),
                register_target=bool(args.register_target),
                delete_after_import=bool(args.delete_config_after_import),
            )
            return _emit(
                _result("import-config", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "runtime":
            supervisor = _runtime(paths)
            if args.runtime_command == "acquire":
                payload = supervisor.acquire(
                    client=args.client,
                    session_id=args.session_id,
                    ttl_seconds=args.ttl_seconds,
                )
            elif args.runtime_command == "heartbeat":
                payload = supervisor.heartbeat(args.lease_id)
            elif args.runtime_command == "release":
                payload = supervisor.release(args.lease_id)
            elif args.runtime_command == "status":
                payload = supervisor.status()
            elif args.runtime_command == "_idle-reap":
                payload = supervisor.watch_idle()
            else:
                payload = supervisor.stop(force=bool(args.force))
            return _emit(
                _result(
                    "runtime " + args.runtime_command,
                    payload=payload,
                    paths=paths,
                ),
                json_output=bool(args.json_output),
            )
        parser.error("unsupported installer command")
    except UserCancelledError:
        result = InstallResult(
            operation,
            exit_code=ExitCode.USER_CANCELLED,
            status="cancelled",
        )
        return _emit(result, json_output=bool(getattr(args, "json_output", False)))
    except InstallerError as exc:
        result = InstallResult(operation, exit_code=exc.exit_code)
        result.fail(exc.exit_code, str(exc))
        return _emit(result, json_output=bool(getattr(args, "json_output", False)))
    except PermissionError:
        result = InstallResult(operation, exit_code=ExitCode.PERMISSION_ERROR)
        result.fail(result.exit_code, "permission denied")
        return _emit(result, json_output=bool(getattr(args, "json_output", False)))
    except ValueError as exc:
        result = InstallResult(operation, exit_code=ExitCode.CONFIGURATION_INVALID)
        result.fail(result.exit_code, str(exc))
        return _emit(result, json_output=bool(getattr(args, "json_output", False)))
    except Exception as exc:  # noqa: BLE001
        result = InstallResult(operation, exit_code=ExitCode.TRANSACTION_FAILED)
        result.fail(result.exit_code, str(exc))
        return _emit(result, json_output=bool(getattr(args, "json_output", False)))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
