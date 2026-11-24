"""Public ``ledgermind`` installer command surface."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from ..model_defaults import load_model_defaults
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
from .operations.update import check_update, rollback, update
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
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="output structured machine-readable JSON",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="fail instead of prompting for interactive input",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="path to a private installer JSON configuration file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate inputs and simulate changes without modifying files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable detailed diagnostic logging during the operation",
    )
    parser.add_argument(
        "--home",
        type=Path,
        help="override home directory for rootless or isolated installs",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledgermind",
        description="LedgerMind local memory installer, diagnostics, and runtime manager.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common workflows:\n"
            "  ledgermind install              Install and configure LedgerMind (Web UI or --cli)\n"
            "  ledgermind status               Show installation, runtime, agent, and memory status\n"
            "  ledgermind doctor               Verify signatures, config, providers, sandbox, and agents\n"
            "  ledgermind update               Check and apply signed updates (uses fast layered patches)\n"
            "  ledgermind rollback             Restore the previous verified LedgerMind release\n"
            "  ledgermind integrations status  Inspect all supported agent integrations\n"
            "  ledgermind runtime status       Check or stop the local LedgerMind background service\n\n"
            "Run 'ledgermind <command> --help' for detailed options."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="COMMAND"
    )

    install_parser = subparsers.add_parser(
        "install",
        help="install LedgerMind, configure providers, and connect agents",
        description=(
            "Install or manage the local LedgerMind runtime, verify signed release artifacts,\n"
            "configure generation/embedding providers, and register supported agent hooks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    install_subparsers = install_parser.add_subparsers(
        dest="install_command", metavar="SUBCOMMAND"
    )
    schema_parser = install_subparsers.add_parser(
        "schema",
        help="print JSON schema for installer config, manifest, or result",
        description="Print the JSON Schema definition for an installer contract object.",
    )
    schema_parser.add_argument(
        "--name",
        choices=("install-config", "install-manifest", "install-result"),
        default="install-config",
        help="schema document to emit (default: install-config)",
    )
    schema_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="wrap the schema in the standard installer JSON result envelope",
    )
    plan_parser = install_subparsers.add_parser(
        "plan",
        help="preview runtime profiles and installation paths without installing",
        description="Compute and display the planned LedgerMind installation layout and profiles without writing files.",
    )
    _common(plan_parser)
    plan_parser.add_argument(
        "--manifest",
        type=Path,
        help="path to a signed install-manifest.json file",
    )
    for option in (install_parser,):
        _common(option)
        option.add_argument(
            "--manifest",
            type=Path,
            help="path to a local signed install-manifest.json file",
        )
        option.add_argument(
            "--bundle",
            type=Path,
            help="path to a local release archive (.tar.zst)",
        )
        option.add_argument(
            "--manifest-signature",
            type=Path,
            help="path to the detached Ed25519 manifest signature file",
        )
        option.add_argument(
            "--skip-provider-probe",
            action="store_true",
            help="skip live provider capability checks during installation",
        )
        option.add_argument(
            "--ui",
            choices=("auto", "web", "cli"),
            default="auto",
            help="setup interface: auto (browser on desktop, CLI on headless/SSH), web, or cli",
        )
        option.add_argument(
            "--web",
            action="store_true",
            help="launch the local Web UI setup wizard",
        )
        option.add_argument(
            "--cli",
            "--terminal",
            action="store_true",
            dest="cli_ui",
            help="use the interactive terminal setup wizard",
        )
        option.add_argument(
            "--web-port",
            type=int,
            default=0,
            help="port for the local Web UI setup server (default: free port)",
        )
        option.add_argument(
            "--no-browser",
            action="store_true",
            help="print the Web UI setup URL without launching a browser",
        )
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

    configure_parser = subparsers.add_parser(
        "configure",
        help="reconfigure providers, models, and memory settings",
        description=(
            "Update provider endpoints, models, secret bindings, or agent selection on an existing installation."
        ),
    )
    _common(configure_parser)
    configure_parser.add_argument(
        "--validate-providers",
        action="store_true",
        help="probe configured generation, embedding, and decision endpoints before saving",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="show installation, runtime, agents, and memory pipeline status",
        description=(
            "Display read-only status of the active installation, local runtime service,\n"
            "connected agent integrations, and durable memory pipeline health without waking the runtime."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _common(status_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="run full diagnostic checks on release, config, providers, and sandbox",
        description=(
            "Verify release bundle signatures, private file permissions, config/profile sync,\n"
            "connected agent adapters, live provider probes, runtime status, and bubblewrap isolation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _common(doctor_parser)
    doctor_parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="skip the temporary disposable sandbox smoke test",
    )

    repair_parser = subparsers.add_parser(
        "repair",
        help="repair symlinks, private tokens, local configs, and agent hooks",
        description=(
            "Re-synchronize local config/profiles from config.json, restore permissions and binary links,\n"
            "and repair registered agent integrations without probing remote providers."
        ),
    )
    _common(repair_parser)

    update_parser = subparsers.add_parser(
        "update",
        help="check for or apply signed updates cleanly",
        description=(
            "Download and verify the latest signed LedgerMind release (using fast layered patches\n"
            "when the local runtime layer matches), or update offline from --manifest and --bundle.\n"
            "Preserves configuration, credentials, memory data, and keeps a rollback backup."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _common(update_parser)
    update_parser.add_argument(
        "--check",
        action="store_true",
        help="check whether a newer signed release is available without installing",
    )
    update_parser.add_argument(
        "--version",
        dest="target_version",
        help="install or switch to a specific release version from GitHub Releases",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="reinstall even when the target release version is already active",
    )
    update_parser.add_argument(
        "--keep-releases",
        type=int,
        default=2,
        help="number of installed releases to keep after updating (default: 2)",
    )
    update_parser.add_argument(
        "--manifest",
        type=Path,
        help="optional path to a local signed install-manifest.json for offline updates",
    )
    update_parser.add_argument(
        "--bundle",
        type=Path,
        help="optional path to a local release bundle (.tar.zst) for offline updates",
    )
    update_parser.add_argument(
        "--skip-provider-probe",
        action="store_true",
        help="skip live provider capability probes after upgrading",
    )

    rollback_parser = subparsers.add_parser(
        "rollback",
        help="restore a previous verified LedgerMind release",
        description=(
            "Atomically switch the active installation back to a previously kept release\n"
            "after verifying its signed bundle manifest and running local smoke checks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _common(rollback_parser)
    rollback_parser.add_argument(
        "--version",
        dest="target_version",
        help="specific retained release version to restore (default: most recent previous release)",
    )

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="remove LedgerMind binaries and disconnect agents cleanly",
        description=(
            "Stop the local runtime, disconnect all agent hooks, and remove LedgerMind binaries.\n"
            "By default, memory databases and configuration are preserved unless purge flags are passed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _common(uninstall_parser)
    uninstall_parser.add_argument(
        "--purge-data",
        action="store_true",
        help="also delete stored memory databases and local state data",
    )
    uninstall_parser.add_argument(
        "--purge-config",
        action="store_true",
        help="also delete config directory and stored local secrets",
    )
    uninstall_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm destructive purge actions without interactive prompt",
    )

    integrations_parser = subparsers.add_parser(
        "integrations",
        help="discover, inspect, and manage agent integrations",
        description="Discover supported coding agents and connect, enable, disable, or disconnect LedgerMind hooks.",
    )
    integration_commands = integrations_parser.add_subparsers(
        dest="integration_command", required=True, metavar="ACTION"
    )
    integrations_discover = integration_commands.add_parser(
        "discover",
        help="scan the host for supported agent installations",
        description="Detect which supported agents are present on this machine without modifying configs.",
    )
    _common(integrations_discover)
    integrations_status = integration_commands.add_parser(
        "status",
        help="show detailed connection and delivery status for all agents",
        description="Inspect runtime state and connection/verification/queue status for each supported agent.",
    )
    _common(integrations_status)
    integrations_connect = integration_commands.add_parser(
        "connect",
        help="connect LedgerMind hooks to a supported agent",
        description="Register hooks and profile bindings for an agent.",
    )
    _common(integrations_connect)
    integrations_connect.add_argument(
        "integration",
        choices=target_ids(),
        help="agent identifier to connect",
    )
    integrations_connect.add_argument(
        "--disabled",
        action="store_true",
        help="connect the integration in disabled state initially",
    )
    integration_action_help = {
        "enable": ("enable hooks for a connected agent", "Enable LedgerMind memory hooks for a connected agent."),
        "disable": ("temporarily disable hooks for a connected agent", "Pause LedgerMind memory hooks without removing configuration."),
        "disconnect": ("remove LedgerMind hooks from an agent", "Unregister LedgerMind hooks and integration state for an agent."),
    }
    for action in ("enable", "disable", "disconnect"):
        short_help, long_desc = integration_action_help[action]
        action_parser = integration_commands.add_parser(
            action,
            help=short_help,
            description=long_desc,
        )
        _common(action_parser)
        action_parser.add_argument(
            "integration",
            choices=target_ids(),
            help=f"agent identifier to {action}",
        )

    export_parser = subparsers.add_parser(
        "export-config",
        help="export installer configuration to a private JSON file",
        description="Write installer configuration to a 0600 JSON file (excluding secrets unless --include-secrets is set).",
    )
    _common(export_parser)
    export_parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="destination file path for exported configuration",
    )
    export_parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="include resolved provider API tokens in the exported file",
    )

    import_parser = subparsers.add_parser(
        "import-config",
        help="validate and import configuration from a private JSON file",
        description="Load an exported configuration file, save secrets if present, and optionally probe providers.",
    )
    _common(import_parser)
    import_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="path to a private 0600 configuration JSON file to import",
    )
    import_parser.add_argument(
        "--validate-providers",
        action="store_true",
        help="probe generation and API embedding providers during import",
    )
    import_parser.add_argument(
        "--register-target",
        action="store_true",
        help="mark target integrations for registration metadata",
    )
    import_parser.add_argument(
        "--delete-config-after-import",
        action="store_true",
        help="securely remove the source file after successful import",
    )

    runtime_parser = subparsers.add_parser(
        "runtime",
        help="inspect or control the local background memory service",
        description="Manage the local LedgerMind runtime daemon and session leases.",
    )
    _common(runtime_parser)
    runtime_subparsers = runtime_parser.add_subparsers(
        dest="runtime_command", required=True, metavar="ACTION"
    )

    def _runtime_flags(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            default=argparse.SUPPRESS,
            help="output structured machine-readable JSON",
        )
        command_parser.add_argument(
            "--non-interactive",
            action="store_true",
            default=argparse.SUPPRESS,
            help="fail instead of prompting for interactive input",
        )
        command_parser.add_argument(
            "--config",
            type=Path,
            default=argparse.SUPPRESS,
            help="path to a private installer JSON configuration file",
        )
        command_parser.add_argument(
            "--dry-run",
            action="store_true",
            default=argparse.SUPPRESS,
            help="simulate action without changing runtime state",
        )
        command_parser.add_argument(
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="enable verbose diagnostic output",
        )
        command_parser.add_argument(
            "--home",
            type=Path,
            default=argparse.SUPPRESS,
            help="override home directory for isolated runtime state",
        )

    acquire = runtime_subparsers.add_parser(
        "acquire",
        help="acquire a runtime session lease (starts service if sleeping)",
        description="Acquire a timed lease for a client session and ensure the local runtime is running.",
    )
    _runtime_flags(acquire)
    acquire.add_argument(
        "--client",
        required=True,
        help="client identifier (for example codex or opencode)",
    )
    acquire.add_argument(
        "--session-id",
        required=True,
        help="unique client session identifier",
    )
    acquire.add_argument(
        "--ttl-seconds",
        type=float,
        help="requested lease lifetime in seconds",
    )
    heartbeat = runtime_subparsers.add_parser(
        "heartbeat",
        help="renew an active runtime session lease",
        description="Extend an existing runtime lease TTL while an agent session remains active.",
    )
    _runtime_flags(heartbeat)
    heartbeat.add_argument(
        "--lease-id",
        required=True,
        help="lease identifier returned by runtime acquire",
    )
    release = runtime_subparsers.add_parser(
        "release",
        help="release an active runtime session lease",
        description="Release a session lease and allow idle shutdown when no leases remain.",
    )
    _runtime_flags(release)
    release.add_argument(
        "--lease-id",
        required=True,
        help="lease identifier to release",
    )
    runtime_status = runtime_subparsers.add_parser(
        "status",
        help="show local runtime process, endpoint, and lease state",
        description="Inspect whether the local runtime is running, its HTTP endpoint, processes, and active leases.",
    )
    _runtime_flags(runtime_status)
    stop = runtime_subparsers.add_parser(
        "stop",
        help="stop the local LedgerMind background runtime",
        description="Stop the managed local runtime processes.",
    )
    _runtime_flags(stop)
    stop.add_argument(
        "--force",
        action="store_true",
        help="stop even if active session leases still exist",
    )
    idle_reap = runtime_subparsers.add_parser("_idle-reap")
    _runtime_flags(idle_reap)

    hook = subparsers.add_parser("integration-hook")
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
    if config is not None and (
        (config.embedding.mode == "local" and config.embedding.local is not None)
        or config.reranker.mode == "local"
    ):
        from .hardware import choose_device

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
        if config.embedding.mode == "local" and config.embedding.local is not None:
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
            embedding_command = [
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
                "8767",
                "--lock-file",
                str(paths.runtime_dir / "embedding.lock"),
                "--token-file",
                str(local_embedding_token_file),
                "--embedding-alias",
                load_model_defaults().embedding_local_alias,
            ]
        else:
            reranker_runtime = (
                Path(config.reranker.runtime_path).expanduser()
                if config.reranker.runtime_path
                else None
            )
            candidate_python = (
                reranker_runtime / "bin" / "python3" if reranker_runtime else None
            )
            runtime_python = (
                candidate_python
                if candidate_python is not None and candidate_python.is_file()
                else Path(sys.executable)
            )
            embedding_command = [
                str(runtime_python),
                "-c",
                module_bootstrap,
                "--port",
                "8767",
                "--lock-file",
                str(paths.runtime_dir / "embedding.lock"),
                "--token-file",
                str(local_embedding_token_file),
            ]
        if config.reranker.mode == "local" and config.reranker.model_path:
            embedding_command.extend(
                [
                    "--reranker-model-path",
                    str(Path(config.reranker.model_path).expanduser()),
                    "--reranker-device",
                    config.reranker.device,
                ]
            )
            if config.reranker.runtime_path:
                embedding_command.extend(
                    [
                        "--reranker-runtime",
                        str(Path(config.reranker.runtime_path).expanduser()),
                    ]
                )
        commands["embedding"] = tuple(embedding_command)
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

    values = {
        "--home",
        "--config",
        "--manifest",
        "--bundle",
        "--manifest-signature",
        "--ui",
        "--web-port",
    }
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
        if "-h" in raw or "--help" in raw:
            return raw
        return ["install", *raw]
    return [raw[index], *prefix, *raw[index + 1 :]]


def _resolve_embedding_catalog(
    args: argparse.Namespace, paths: InstallerPaths
) -> Sequence[dict[str, object]]:
    if getattr(args, "manifest", None) is not None:
        from .manifest import load_manifest

        return load_manifest(args.manifest).embedding_catalog
    try:
        from .operations.common import fetch_manifest
        from .verify import public_key_from_environment

        manifest_path, signature_path, manifest = fetch_manifest(
            paths, public_key=public_key_from_environment()
        )
        args.manifest = manifest_path
        args.manifest_signature = signature_path
        return manifest.embedding_catalog
    except InstallerError:
        # API embeddings remain available. A local option is never shown
        # without a verified signed catalog from this release.
        return ()


def _resolve_ui_mode(args: argparse.Namespace) -> str:
    if bool(getattr(args, "web", False)) and bool(getattr(args, "cli_ui", False)):
        raise ConfigurationError("--web and --cli cannot be combined")
    if bool(getattr(args, "web", False)):
        return "web"
    if bool(getattr(args, "cli_ui", False)):
        return "cli"
    return str(getattr(args, "ui", "auto") or "auto")


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

    embedding_catalog = _resolve_embedding_catalog(args, _paths(args))

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
        interactive_progress = (
            _terminal_progress
            if not bool(args.non_interactive) and not bool(args.json_output)
            else None
        )
        if interactive_progress is not None:
            _terminal_progress.phase = None  # type: ignore[attr-defined]
        return update(
            config=existing,
            paths=paths,
            skip_provider_probe=bool(args.skip_provider_probe),
            dry_run=bool(args.dry_run),
            progress=interactive_progress,
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
            "resolution_decision": (
                existing.resolution_decision or candidate.resolution_decision
            ),
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


def _format_timestamp(raw: Any) -> str:
    """Format ISO-8601 or epoch timestamps into compact readable UTC strings."""

    if raw is None:
        return "none"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
        except (OverflowError, OSError, ValueError):
            return str(raw)
    text = str(raw).strip()
    if not text:
        return "none"
    normalized = re.sub(r"\.(\d{6})\d*", r".\1", text)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _status_summary(value: Any, *, default: str = "unknown") -> str:
    if isinstance(value, dict):
        state = value.get("status")
        if not state and (
            value.get("strict_structured_outputs") or value.get("structured_json")
        ):
            state = "passed"
        state_text = str(state or default)
        error = value.get("error")
        return f"{state_text} ({error})" if error else state_text
    if value is None:
        return default
    return str(value)


def _format_runtime_endpoint(runtime: dict[str, Any]) -> str:
    endpoint = str(
        runtime.get("endpoint") or runtime.get("preferred_endpoint") or "unavailable"
    )
    if runtime.get("endpoint_failover"):
        endpoint += " (fallback port)"
    return endpoint


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
        _emit_doctor_details(result)
        _emit_runtime_details(result)
        _emit_config_transfer_details(result)
        _emit_update_details(result)
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
    data = result.steps[-1].data
    installed = bool(data.get("installed"))
    current = data.get("current")
    release_label = (
        f"{Path(str(current)).name} ({current})" if current else "not installed"
    )
    print("\nInstallation:")
    print(f"  Installed:    {'yes' if installed else 'no'}")
    print(f"  Release:      {release_label}")
    if data.get("config"):
        cfg_state = "present" if data.get("config_exists") else "missing"
        print(f"  Config:       {data['config']} ({cfg_state})")

    runtime = data.get("runtime")
    if isinstance(runtime, dict):
        running = bool(runtime.get("running"))
        residency = str(runtime.get("residency_mode") or "unknown")
        if running:
            state_label = "running"
        elif residency == "always_on":
            state_label = "stopped"
        else:
            state_label = "sleeping (starts on agent activity)"
        leases = runtime.get("active_leases")
        lease_list = leases if isinstance(leases, list) else []
        clients = sorted(
            {
                str(item.get("client"))
                for item in lease_list
                if isinstance(item, dict) and item.get("client")
            }
        )
        lease_summary = f"{len(lease_list)} active"
        if clients:
            lease_summary += f" ({', '.join(clients)})"
        print("\nRuntime:")
        print(f"  State:        {state_label}")
        print(f"  Residency:    {residency}")
        print(f"  Endpoint:     {_format_runtime_endpoint(runtime)}")
        if runtime.get("endpoint_conflict"):
            print("  Warning:      configured port is occupied by another process")
        print(f"  Leases:       {lease_summary}")

    integrations = data.get("integrations")
    if isinstance(integrations, dict):
        connected_items = [
            (target_id, item)
            for target_id, item in integrations.items()
            if isinstance(item, dict) and item.get("connected")
        ]
        print("\nAgents:")
        if connected_items:
            for target_id, item in connected_items:
                discovery = item.get("discovery")
                label = (
                    str(discovery.get("label") or target_id)
                    if isinstance(discovery, dict)
                    else target_id
                )
                parts = ["enabled" if item.get("enabled") else "disabled"]
                verify = item.get("verify")
                if isinstance(verify, dict) and verify.get("status"):
                    parts.append(f"verify={verify['status']}")
                if item.get("active"):
                    parts.append("active session")
                delivery = item.get("delivery")
                if isinstance(delivery, dict) and delivery.get("queued_rounds"):
                    parts.append(f"queued={delivery['queued_rounds']}")
                print(f"  {label} ({target_id}): {', '.join(parts)}")
            print("  Details:      run 'ledgermind integrations status'")
        elif installed:
            print(
                "  none connected (run 'ledgermind integrations discover' to inspect agents)"
            )
        else:
            print("  not configured")

    health = data.get("memory_health")
    if not isinstance(health, dict):
        return
    print("\nMemory pipeline:")
    health_status = str(health.get("status", "unknown"))
    if health.get("reason"):
        health_status = f"{health_status} ({health['reason']})"
    print(f"  Health:       {health_status}")
    summary = data.get("memory_summary")
    if isinstance(summary, dict):
        print(
            "  Knowledge:    "
            f"{summary.get('active_knowledge_values', 0)} stored value(s), "
            f"{summary.get('processed_batches', 0)} processed batch(es)"
        )
    if health.get("last_successful_pipeline_at"):
        print(f"  Last success: {_format_timestamp(health['last_successful_pipeline_at'])}")
    elif health.get("status") in {"healthy", "degraded"}:
        print("  Last success: none yet")
    if health.get("last_materialized_at"):
        print(f"  Last write:   {_format_timestamp(health['last_materialized_at'])}")
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
        when = f" at {_format_timestamp(latest['at'])}" if latest.get("at") else ""
        if health.get("status") == "healthy":
            print(
                f"  Prior error:  {latest['error_code']}{when} "
                "(resolved by later success)"
            )
        else:
            print(f"  Latest error: {latest['error_code']}{when}")
    update_check = data.get("update_check")
    if (
        isinstance(update_check, dict)
        and update_check.get("update_available")
        and update_check.get("latest_version")
    ):
        installed_ver = update_check.get("installed_version") or "unknown"
        print("\nUpdate:")
        print(
            f"  Available:    {installed_ver} -> {update_check['latest_version']} "
            "(run 'ledgermind update')"
        )


def _format_provider_probe(name: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    if payload.get("status") == "local-runtime-configured":
        return "local runtime configured"
    state = _status_summary(payload)
    details: list[str] = []
    if name == "resolution_decision" and payload.get("backend"):
        details.append(f"backend={payload['backend']}")
    if payload.get("model"):
        details.append(f"model={payload['model']}")
    if payload.get("route"):
        details.append(f"route={payload['route']}")
    if payload.get("reasoning_effort"):
        details.append(f"reasoning={payload['reasoning_effort']}")
    if payload.get("dimensions") is not None:
        details.append(f"dims={payload['dimensions']}")
    if payload.get("latency_ms") is not None:
        details.append(f"latency={payload['latency_ms']}ms")
    if payload.get("endpoint"):
        details.append(f"endpoint={payload['endpoint']}")
    return f"{state} ({', '.join(details)})" if details else state


def _emit_doctor_details(result: InstallResult) -> None:
    if result.operation != "doctor" or not result.steps:
        return
    data = result.steps[-1].data
    delivery = data.get("delivery") if isinstance(data.get("delivery"), dict) else {}
    config_info = (
        data.get("configuration") if isinstance(data.get("configuration"), dict) else {}
    )
    providers = (
        data.get("providers") if isinstance(data.get("providers"), dict) else {}
    )
    runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    smoke = data.get("smoke_test") if isinstance(data.get("smoke_test"), dict) else {}
    integrations = (
        data.get("integrations") if isinstance(data.get("integrations"), dict) else {}
    )

    print("\nDelivery:")
    print(f"  Platform:      {data.get('platform') or 'unknown'}")
    print(f"  Release:       {delivery.get('current', 'missing')}")
    print(f"  Signature:     {_status_summary(delivery.get('signature'))}")
    binaries = [
        f"{name}={'ok' if delivery.get(key) else 'missing'}"
        for name, key in (
            ("core", "core"),
            ("local", "local"),
            ("installer", "installer"),
            ("manifest", "bundle_manifest"),
        )
    ]
    print(f"  Artifacts:     {', '.join(binaries)}")

    print("\nConfiguration:")
    print(f"  Schema:        {_status_summary(config_info.get('schema'))}")
    print(f"  Permissions:   {_status_summary(config_info.get('permissions'))}")
    if config_info.get("secret_store"):
        print(f"  Secret store:  {config_info['secret_store']}")
    if config_info.get("local_config") is not None:
        print(f"  Local sync:    {_status_summary(config_info.get('local_config'))}")
    if config_info.get("profile_slots") is not None:
        print(f"  Profile slots: {_status_summary(config_info.get('profile_slots'))}")
    core_cfg = config_info.get("core_config")
    if isinstance(core_cfg, dict):
        print(
            "  Core settings: "
            f"security={core_cfg.get('security_profile')}, "
            f"language={core_cfg.get('semantic_language')}, "
            f"gen_concurrency={core_cfg.get('generation_concurrency')}, "
            f"emb_concurrency={core_cfg.get('embedding_max_concurrency')}"
        )

    print("\nProviders:")
    if "status" in providers and not any(
        key in providers for key in ("generation", "embedding", "resolution_decision")
    ):
        print(f"  Status:        {_status_summary(providers)}")
    else:
        for label, key in (
            ("Generation", "generation"),
            ("Embeddings", "embedding"),
            ("Decision", "resolution_decision"),
        ):
            if key in providers:
                print(f"  {label + ':':14} {_format_provider_probe(key, providers[key])}")

    print("\nRuntime & sandbox:")
    if runtime:
        leases = runtime.get("active_leases")
        lease_count = len(leases) if isinstance(leases, list) else 0
        state_text = "running" if runtime.get("running") else "sleeping"
        residency = runtime.get("residency_mode") or "unknown"
        print(
            f"  Runtime:       {state_text} at {_format_runtime_endpoint(runtime)} "
            f"(residency={residency}, leases={lease_count})"
        )
    smoke_line = _status_summary(smoke)
    if smoke.get("writes_user_memory") is False and smoke.get("status") == "passed":
        smoke_line += " (isolated, no user memory modified)"
    print(f"  Smoke test:    {smoke_line}")

    if integrations:
        print("\nConnected agents:")
        for target_id, item in integrations.items():
            if not isinstance(item, dict):
                continue
            discovery = (
                item.get("discovery") if isinstance(item.get("discovery"), dict) else {}
            )
            label = str(discovery.get("label") or target_id)
            detected = "yes" if discovery.get("detected") else "no"
            enabled = "enabled" if item.get("enabled") else "disabled"
            adapter_text = _status_summary(item.get("adapter"))
            print(
                f"  {label} ({target_id}): {enabled}, detected={detected}, verify={adapter_text}"
            )


def _emit_runtime_details(result: InstallResult) -> None:
    if not result.operation.startswith("runtime ") or not result.steps:
        return
    data = result.steps[-1].data
    action = result.operation.split(" ", 1)[1]
    if action == "status":
        running = bool(data.get("running"))
        leases = data.get("active_leases")
        lease_list = leases if isinstance(leases, list) else []
        processes = data.get("processes") if isinstance(data.get("processes"), dict) else {}
        print("\nRuntime state:")
        print(f"  State:         {'running' if running else 'sleeping'}")
        if data.get("residency_mode"):
            print(f"  Residency:     {data['residency_mode']}")
        print(f"  Endpoint:      {_format_runtime_endpoint(data)}")
        if data.get("endpoint_conflict"):
            print("  Warning:       configured port is occupied by another process")
        print(f"  Active leases: {len(lease_list)}")
        for lease in lease_list:
            if not isinstance(lease, dict):
                continue
            print(
                "    - "
                f"client={lease.get('client', 'unknown')}, "
                f"session={lease.get('session_id', 'unknown')}, "
                f"lease={lease.get('lease_id', 'unknown')}, "
                f"expires={_format_timestamp(lease.get('expires_at'))}"
            )
        if processes:
            proc_parts = [
                f"{name} (pid={info.get('pid', '?')})"
                if isinstance(info, dict)
                else f"{name}={info}"
                for name, info in processes.items()
            ]
            print(f"  Processes:     {', '.join(proc_parts)}")
        else:
            print("  Processes:     none running")
        return

    if action == "stop":
        stopped = bool(data.get("stopped"))
        processes = data.get("processes") if isinstance(data.get("processes"), dict) else {}
        print("\nRuntime stop:")
        print(f"  Stopped:       {'yes' if stopped else 'no'}")
        if processes:
            print(f"  Processes:     {', '.join(f'{k}={v}' for k, v in processes.items())}")
        if data.get("reason"):
            print(f"  Reason:        {data['reason']}")
        return

    print(f"\nRuntime {action}:")
    for label, key in (
        ("Lease ID", "lease_id"),
        ("Client", "client"),
        ("Session ID", "session_id"),
        ("Endpoint", "endpoint"),
        ("Started", "started"),
        ("Released", "released"),
        ("Active leases", "active_leases"),
        ("Stopped", "stopped"),
    ):
        if key in data and data[key] is not None:
            print(f"  {label + ':':14} {data[key]}")
    if data.get("expires_at") is not None:
        print(f"  Expires at:    {_format_timestamp(data['expires_at'])}")


def _emit_config_transfer_details(result: InstallResult) -> None:
    if not result.steps:
        return
    data = result.steps[-1].data
    if result.operation == "export-config":
        print("\nExport result:")
        print(f"  File:          {data.get('out', 'unknown')}")
        print(
            "  Secrets:       "
            + ("included" if data.get("include_secrets") else "excluded (refs only)")
        )
        return
    if result.operation == "import-config":
        cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
        probes = data.get("probes") if isinstance(data.get("probes"), dict) else {}
        print("\nImport result:")
        if cfg.get("config"):
            print(f"  Config file:   {cfg['config']}")
        print(f"  Probes run:    {', '.join(probes.keys()) if probes else 'none'}")
        print(
            "  Target agents: "
            + ("marked for registration" if data.get("target_registered") else "preserved")
        )
        return
    if result.operation == "install plan":
        print("\nInstall plan:")
        print(f"  Platform:      {data.get('platform', 'unknown')}")
        if data.get("release_version"):
            print(f"  Release:       {data['release_version']}")
        print(f"  Memory mode:   {data.get('memory_mode', 'unknown')}")
        if data.get("memory_data_path"):
            print(f"  Memory path:   {data['memory_data_path']}")
        integrations = data.get("integrations")
        if isinstance(integrations, list):
            agent_labels = [
                f"{item.get('id')}({'on' if item.get('enabled') else 'off'})"
                for item in integrations
                if isinstance(item, dict) and item.get("id")
            ]
            print(f"  Agents:        {', '.join(agent_labels) if agent_labels else 'none'}")
        profiles = data.get("profiles")
        if isinstance(profiles, list):
            print(f"  Profiles:      {len(profiles)} planned")
        runtime = data.get("runtime")
        if isinstance(runtime, dict) and runtime.get("residency_mode"):
            print(f"  Residency:     {runtime['residency_mode']}")
        return
    if result.operation == "install schema":
        print()
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _emit_update_details(result: InstallResult) -> None:
    if result.operation not in {"update", "update check", "rollback"} or not result.steps:
        return
    data = result.steps[-1].data
    if result.operation == "update check":
        print("\nUpdate check:")
        print(f"  Installed:    {data.get('installed_version') or 'not installed'}")
        print(f"  Latest:       {data.get('latest_version') or 'unknown'}")
        print(
            "  Status:       "
            + ("update available" if data.get("update_available") else "up to date")
        )
        dl_bytes = data.get("download_bytes")
        full_bytes = data.get("full_bundle_bytes")
        if isinstance(dl_bytes, int):
            dl_mib = dl_bytes / (1024 * 1024)
            if data.get("layered_patch_available") and isinstance(full_bytes, int):
                full_mib = full_bytes / (1024 * 1024)
                print(
                    f"  Download:     layered patch (~{dl_mib:.1f} MiB vs {full_mib:.1f} MiB full)"
                )
            else:
                print(f"  Download:     full bundle (~{dl_mib:.1f} MiB)")
        if data.get("update_available"):
            print("  Apply:        run 'ledgermind update'")
        return

    if result.operation == "update":
        if data.get("up_to_date"):
            print("\nUpdate:")
            print(f"  Status:       already up to date ({data.get('release_version')})")
            return
        print("\nUpdate summary:")
        previous = data.get("previous_version") or "unknown"
        target = data.get("release_version") or "unknown"
        print(f"  Version:      {previous} -> {target}")
        if data.get("delivery_mode"):
            print(f"  Delivery:     {data['delivery_mode']}")
        pruned = data.get("pruned_releases")
        if isinstance(pruned, list) and pruned:
            print(f"  Pruned:       {', '.join(str(item) for item in pruned)}")
        if data.get("rollback_available"):
            print("  Rollback:     available ('ledgermind rollback')")
        return

    print("\nRollback:")
    print(
        f"  Version:      {data.get('previous_version') or 'unknown'} "
        f"-> {data.get('release_version') or 'unknown'}"
    )
    if data.get("release_dir"):
        print(f"  Release dir:  {data['release_dir']}")
    doc = data.get("doctor")
    if isinstance(doc, dict) and doc.get("status"):
        print(f"  Doctor:       {doc['status']}")


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
    if result.operation == "integrations status":
        runtime = step.data.get("runtime")
        if isinstance(runtime, dict):
            state = "running" if runtime.get("running") else "sleeping"
            endpoint = runtime.get("preferred_endpoint") or "unavailable"
            suffix = " (fallback port)" if runtime.get("endpoint_failover") else ""
            print(f"\nMemory runtime: {state} at {endpoint}{suffix}")
            if runtime.get("endpoint_conflict"):
                print("  warning: configured port is occupied by another process")
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
        delivery = raw_item.get("delivery")
        if isinstance(delivery, dict) and delivery.get("queued_rounds"):
            fields.append(f"queued={delivery['queued_rounds']}")
        print(f"  {label} ({target_id}): {', '.join(fields)}")
        if raw_item.get("orphaned_hook_config"):
            print("    warning: hook config exists but this agent is not selected")
        if isinstance(delivery, dict) and delivery.get("last_failure_reason"):
            print(f"    delivery: {delivery['last_failure_reason']}")
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
            # Stop requires JSON stdout, including the no-context success path.
            # Always emit an object so failures remain fail-open, not malformed
            # host responses. Diagnostic errors are still recorded separately.
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
            ui_mode = _resolve_ui_mode(args)
            if args.config is None:
                from .web_wizard import run_web_install, should_use_web_ui

                if should_use_web_ui(
                    ui_mode,
                    json_output=bool(args.json_output),
                    non_interactive=bool(args.non_interactive),
                ):
                    embedding_catalog = _resolve_embedding_catalog(args, paths)
                    payload = run_web_install(
                        install_callback=lambda cfg, progress: install(
                            config=cfg,
                            paths=paths,
                            manifest_path=args.manifest,
                            bundle=args.bundle,
                            manifest_signature=args.manifest_signature,
                            dry_run=bool(args.dry_run),
                            skip_provider_probe=bool(args.skip_provider_probe),
                            progress=progress,
                        ),
                        port=int(getattr(args, "web_port", 0) or 0),
                        open_browser=not bool(getattr(args, "no_browser", False)),
                        preflight_home=getattr(args, "home", None),
                        embedding_catalog=embedding_catalog,
                    )
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
            if bool(args.manifest) != bool(args.bundle):
                raise ConfigurationError(
                    "--manifest and --bundle must be provided together"
                )
            if args.check:
                payload = check_update(
                    paths=paths,
                    version=args.target_version,
                )
                return _emit(
                    _result("update check", payload=payload, paths=paths),
                    json_output=bool(args.json_output),
                )
            if args.config is not None:
                raise ConfigurationError(
                    "update preserves provider configuration; use configure to change it"
                )
            if not paths.config_file.is_file():
                raise ConfigurationError("LedgerMind must be installed before update")
            from .config_writer import load_installer_config

            config = load_installer_config(paths.config_file)
            interactive_progress = (
                _terminal_progress
                if not bool(args.non_interactive) and not bool(args.json_output)
                else None
            )
            if interactive_progress is not None:
                _terminal_progress.phase = None  # type: ignore[attr-defined]
            update_kwargs: dict[str, Any] = {
                "config": config,
                "paths": paths,
                "manifest_path": args.manifest,
                "bundle": args.bundle,
                "dry_run": bool(args.dry_run),
                "skip_provider_probe": bool(args.skip_provider_probe),
                "generation_stdin": None,
                "embedding_stdin": None,
            }
            if args.target_version is not None:
                update_kwargs["version"] = args.target_version
            if args.force:
                update_kwargs["force"] = True
            if args.keep_releases != 2:
                update_kwargs["keep_releases"] = args.keep_releases
            if interactive_progress is not None:
                update_kwargs["progress"] = interactive_progress
            payload = update(**update_kwargs)
            return _emit(
                _result("update", payload=payload, paths=paths),
                json_output=bool(args.json_output),
            )
        if operation == "rollback":
            payload = rollback(
                paths=paths,
                target_version=args.target_version,
                dry_run=bool(args.dry_run),
            )
            return _emit(
                _result("rollback", payload=payload, paths=paths),
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
