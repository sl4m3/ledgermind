"""Command-line interface for local service scaffolding."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import FrameType
from typing import Any, TypeVar, cast

from ledgermind_inference.structured_json_provider import default_provider_factory

from ledgermind_local.api.app import create_app
from ledgermind_local.api.dependencies import Settings
from ledgermind_local.bootstrap import (
    LocalRuntime,
    build_process_core_gateway,
    initialize_local_layout,
)
from ledgermind_local.config import CURRENT_CONFIG_VERSION, LocalConfig
from ledgermind_local.core_gateway import CoreGateway
from ledgermind_local.core_gateway.doctor import build_core_doctor_report
from ledgermind_local.diagnostics.integrity import run_database_integrity_checks
from ledgermind_local.inference import (
    InferenceProfile,
    InferenceProfileStore,
    SecretStore,
    StoreBackedProfileResolver,
)
from ledgermind_local.inference.provider_probe import ProviderProbe
from ledgermind_local.maintenance.coordinated_restore import (
    CoordinatedRestoreError,
    CoordinatedRestoreService,
)
from ledgermind_local.maintenance.core_backup import CoreBackupError, CoreBackupService
from ledgermind_local.paths import ServicePaths
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.scheduler import (
    RawRoundRetentionWorker,
)
from ledgermind_local.service_lock import ServiceLock, ServiceLockError

WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5.0
T = TypeVar("T")
logger = logging.getLogger(__name__)


def _build_core_gateway(*, paths: ServicePaths, config: LocalConfig) -> CoreGateway:
    """Build the isolated Core boundary without starting the daemon."""

    return build_process_core_gateway(paths=paths, config=config)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LedgerMind local service")
    parser.add_argument(
        "--home",
        default="~/.ledgermind/local",
        help="Path to local data directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Initialize local storage directory"
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config values",
    )
    init_parser.add_argument(
        "--rotate-token",
        action="store_true",
        help="Rotate token when force is used",
    )
    init_parser.add_argument(
        "--semantic-language",
        choices=("ru", "en", "es", "pt", "fr", "de", "uk"),
        help="Semantic language for a new or forced configuration",
    )
    init_parser.set_defaults(func=_command_init)

    serve_parser = subparsers.add_parser("serve", help="Run local HTTP service")
    serve_parser.add_argument(
        "--host",
        help="Override bind host from config",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        help="Override bind port from config",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    serve_parser.set_defaults(func=_command_serve)

    status_parser = subparsers.add_parser(
        "status", help="Print configured service state"
    )
    status_parser.set_defaults(func=_command_status)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run local database integrity checks",
    )
    doctor_parser.add_argument(
        "--database",
        type=Path,
        help="SQLite database file to check; defaults to ledgermind.db from --home",
    )
    doctor_parser.set_defaults(func=_command_doctor)

    core_parser = subparsers.add_parser("core", help="Rust Core operations")
    core_subparsers = core_parser.add_subparsers(
        dest="core_command",
        required=True,
    )
    core_doctor_parser = core_subparsers.add_parser(
        "doctor",
        help="Verify the Core binary and print secret-safe runtime diagnostics",
    )
    core_doctor_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable diagnostics",
    )
    core_doctor_parser.set_defaults(func=_command_core_doctor)

    rotate_token_parser = subparsers.add_parser(
        "rotate-token",
        help="Rotate local service API token in place",
    )
    rotate_token_parser.set_defaults(func=_command_rotate_token)

    backup_parser = subparsers.add_parser("backup", help="Backup operations")
    backup_subparsers = backup_parser.add_subparsers(
        dest="backup_command", required=True
    )
    backup_create_parser = backup_subparsers.add_parser(
        "create",
        help="Create a local backup archive",
    )
    backup_create_parser.add_argument(
        "--destination",
        type=Path,
        help="Directory or file path for the backup archive (default: <home>/backups)",
    )
    backup_create_parser.set_defaults(func=_command_backup_create)

    backup_restore_parser = backup_subparsers.add_parser(
        "restore",
        help="Restore the Local database and Core data from backup",
    )
    backup_restore_parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Backup archive path to restore",
    )
    backup_restore_parser.add_argument(
        "--database",
        type=Path,
        help="Target database path; defaults to layout database",
    )
    backup_restore_parser.set_defaults(func=_command_backup_restore)

    profiles_parser = subparsers.add_parser(
        "profiles",
        help="Manage Local-owned inference profiles and memory-space bindings",
    )
    profiles_subparsers = profiles_parser.add_subparsers(
        dest="profiles_command",
        required=True,
    )

    profiles_list_parser = profiles_subparsers.add_parser(
        "list",
        help="List configured inference profiles",
    )
    profiles_list_parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only include enabled profiles",
    )
    profiles_list_parser.set_defaults(func=_command_profiles_list)

    profiles_add_parser = profiles_subparsers.add_parser(
        "add",
        help="Create or update an inference profile",
    )
    profiles_add_parser.add_argument("--id", dest="profile_id", required=True)
    profiles_add_parser.add_argument(
        "--provider",
        dest="provider_kind",
        choices=("openai_compatible", "nvidia_nim"),
        default="openai_compatible",
    )
    profiles_add_parser.add_argument("--base-url", required=True)
    profiles_add_parser.add_argument("--model", required=True)
    profiles_add_parser.add_argument("--secret-ref", required=True)
    profiles_add_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    profiles_add_parser.add_argument("--max-retries", type=int, default=2)
    profiles_add_parser.add_argument("--max-input-tokens", type=int, default=12_000)
    profiles_add_parser.add_argument("--max-output-tokens", type=int, default=2_000)
    profiles_add_parser.add_argument(
        "--structured-output-preference",
        "--structured-output-mode",
        dest="structured_output_preference",
        choices=(
            "auto",
            "strict_json_schema",
            "json_schema",
            "tool_call",
            "json_object",
            "prompt_only",
        ),
        default="auto",
    )
    profiles_add_parser.add_argument(
        "--token-parameter",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
    )
    profiles_add_parser.add_argument(
        "--no-system-role",
        action="store_true",
        help="Fold system messages into a user-compatible request",
    )
    profiles_add_parser.add_argument(
        "--supports-seed",
        action="store_true",
        help="Allow the provider seed parameter when a task supplies one",
    )
    profiles_add_parser.add_argument("--disabled", action="store_true")
    profiles_add_parser.set_defaults(func=_command_profiles_add)

    profiles_remove_parser = profiles_subparsers.add_parser(
        "remove",
        help="Remove an inference profile",
    )
    profiles_remove_parser.add_argument("--id", dest="profile_id", required=True)
    profiles_remove_parser.set_defaults(func=_command_profiles_remove)

    inference_parser = subparsers.add_parser(
        "inference",
        help="Manage generic Core model profile slots",
    )
    inference_subparsers = inference_parser.add_subparsers(
        dest="inference_command",
        required=True,
    )
    inference_bind_parser = inference_subparsers.add_parser(
        "bind",
        help="Bind one model profile slot to a memory space",
    )
    inference_bind_parser.add_argument("--memory-space-id", required=True)
    inference_bind_parser.add_argument(
        "--slot",
        choices=("operational", "object_resolution", "background", "embedding"),
        required=True,
    )
    inference_bind_parser.add_argument("--profile-id", required=True)
    inference_bind_parser.set_defaults(func=_command_inference_bind)

    inference_probe_parser = inference_subparsers.add_parser(
        "probe",
        help="Run a real structured-output contract probe for a bound profile",
    )
    inference_probe_parser.add_argument("--memory-space-id", required=True)
    inference_probe_parser.add_argument(
        "--slot",
        choices=("operational", "object_resolution", "background"),
        required=True,
    )
    inference_probe_parser.add_argument(
        "--mode",
        "--structured-output-mode",
        dest="mode",
        choices=(
            "auto",
            "strict_json_schema",
            "json_schema",
            "tool_call",
            "json_object",
            "prompt_only",
        ),
    )
    inference_probe_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable probe diagnostics",
    )
    inference_probe_parser.set_defaults(func=_command_inference_probe)

    secrets_parser = subparsers.add_parser(
        "secrets",
        help="Manage Local-owned provider secrets without exposing values",
    )
    secrets_subparsers = secrets_parser.add_subparsers(
        dest="secrets_command",
        required=True,
    )

    secrets_set_parser = secrets_subparsers.add_parser(
        "set",
        help="Read one secret value from stdin and store it by reference",
    )
    secrets_set_parser.add_argument("--ref", dest="secret_ref", required=True)
    secrets_set_parser.add_argument(
        "--value-stdin",
        action="store_true",
        required=True,
        help="Read the secret value from stdin; never pass it as an argument",
    )
    secrets_set_parser.set_defaults(func=_command_secrets_set)

    secrets_list_parser = secrets_subparsers.add_parser(
        "list",
        help="List secret references without values",
    )
    secrets_list_parser.set_defaults(func=_command_secrets_list)

    secrets_delete_parser = secrets_subparsers.add_parser(
        "delete",
        help="Delete a secret by reference",
    )
    secrets_delete_parser.add_argument("--ref", dest="secret_ref", required=True)
    secrets_delete_parser.set_defaults(func=_command_secrets_delete)

    maintenance_parser = subparsers.add_parser(
        "maintenance", help="Run one-shot Local maintenance operations"
    )
    maintenance_subparsers = maintenance_parser.add_subparsers(
        dest="maintenance_command", required=True
    )
    maintenance_retention_parser = maintenance_subparsers.add_parser(
        "retention", help="Purge expired RawRound payload bodies"
    )
    maintenance_retention_parser.add_argument(
        "--limit", type=int, default=100, help="Maximum payloads to purge"
    )
    maintenance_retention_parser.set_defaults(func=_command_maintenance_retention)

    return parser


def _command_init(args: argparse.Namespace) -> int:
    rotate_token = bool(args.rotate_token)
    force = bool(args.force)
    if rotate_token and not force:
        print("--rotate-token requires --force")
        return 2

    home = Path(args.home).expanduser()
    config_path = ServicePaths(home=home).config_file
    semantic_language = getattr(args, "semantic_language", None)
    if (force or not config_path.exists()) and not semantic_language:
        print("--semantic-language is required when creating or replacing config")
        return 2
    init_config = (
        LocalConfig(
            config_version=CURRENT_CONFIG_VERSION,
            semantic_language=semantic_language,
        )
        if force or not config_path.exists()
        else None
    )

    paths, config, token = initialize_local_layout(
        home=home,
        force=force,
        rotate_token=rotate_token,
        config=init_config,
    )
    print(f"initialized {paths.home}")
    print(f"config: {paths.config_file}")
    print(f"token file: {paths.token_file}")
    print(
        f"database: {paths.resolve_rounds_database_path(config.rounds_database_path)}"
    )
    print(f"logs: {paths.logs_dir}")
    if not token:
        raise RuntimeError("token must be generated or loaded")
    return 0


def _open_profile_store(
    args: argparse.Namespace,
) -> tuple[ServicePaths, sqlite3.Connection, InferenceProfileStore]:
    paths, config, _ = initialize_local_layout(home=Path(args.home).expanduser())
    database_path = paths.resolve_rounds_database_path(config.rounds_database_path)
    connection = open_sqlite_connection(database_path)
    migrations.apply_migrations(connection)
    return paths, connection, InferenceProfileStore(connection)


def _command_profiles_list(args: argparse.Namespace) -> int:
    _, connection, store = _open_profile_store(args)
    try:
        profiles = store.list(enabled_only=bool(args.enabled_only))
        print(
            json.dumps(
                [profile.model_dump(mode="json") for profile in profiles],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    finally:
        connection.close()


def _command_profiles_add(args: argparse.Namespace) -> int:
    _, connection, store = _open_profile_store(args)
    try:
        profile = InferenceProfile(
            profile_id=args.profile_id,
            provider_kind=args.provider_kind,
            base_url=args.base_url,
            model=args.model,
            secret_ref=args.secret_ref,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
            structured_output_preference=args.structured_output_preference,
            token_parameter=args.token_parameter,
            supports_system_role=not bool(args.no_system_role),
            supports_seed=bool(args.supports_seed),
            enabled=not bool(args.disabled),
        )
        store.upsert(profile)
        connection.commit()
        print(f"profile saved: {profile.profile_id} (secret_ref={profile.secret_ref})")
        return 0
    except ValueError as exc:
        connection.rollback()
        print(f"invalid profile: {exc}")
        return 2
    finally:
        connection.close()


def _command_profiles_remove(args: argparse.Namespace) -> int:
    _, connection, store = _open_profile_store(args)
    try:
        try:
            removed = store.remove(args.profile_id)
            if not removed:
                print(f"profile not found: {args.profile_id}")
                return 1
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            print("profile is still bound to a memory space")
            return 2
        print(f"profile removed: {args.profile_id}")
        return 0
    finally:
        connection.close()


def _command_inference_bind(args: argparse.Namespace) -> int:
    _, connection, store = _open_profile_store(args)
    try:
        try:
            store.bind_slot(
                args.memory_space_id,
                slot=args.slot,
                profile_id=args.profile_id,
            )
            connection.commit()
        except (sqlite3.IntegrityError, ValueError) as exc:
            connection.rollback()
            print(f"invalid profile slot binding: {exc}")
            return 2
        print(
            f"profile slot bound: {args.memory_space_id} {args.slot} -> {args.profile_id}"
        )
        return 0
    finally:
        connection.close()


def _command_inference_probe(args: argparse.Namespace) -> int:
    """Run an operational/background contract probe and persist its result."""

    paths, connection, store = _open_profile_store(args)
    try:
        try:
            config = LocalConfig.from_file(paths.config_file)
            resolver = StoreBackedProfileResolver(store)
            secret_store = SecretStore(
                paths.resolve_home_path(config.inference_secrets_path)
            )
            result = ProviderProbe(
                profile_resolver=resolver,
                secret_store=secret_store,
                capability_store=store,
                provider_factory=default_provider_factory,
            ).probe(
                args.memory_space_id,
                args.slot,
                mode_override=args.mode,
            )
            connection.commit()
        except Exception as exc:  # noqa: BLE001 - CLI emits a safe diagnostic
            connection.rollback()
            error_code = getattr(exc, "code", None)
            if not isinstance(error_code, str) or not error_code:
                error_code = "probe_failed"
            payload: dict[str, object] = {
                "status": "failed",
                "error_code": error_code,
            }
            if bool(args.json_output):
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            else:
                print(f"inference probe: FAIL ({error_code})")
            return 1

        payload = result.model_dump(mode="json")
        if bool(args.json_output):
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(
                f"inference probe: {result.status.upper()} "
                f"profile={result.profile_id} mode={result.selected_mode}"
            )
        return 0 if result.status == "passed" else 1
    finally:
        connection.close()


def _open_secret_store(args: argparse.Namespace) -> SecretStore:
    paths, config, _ = initialize_local_layout(home=Path(args.home).expanduser())
    return SecretStore(paths.resolve_home_path(config.inference_secrets_path))


def _command_secrets_set(args: argparse.Namespace) -> int:
    store = _open_secret_store(args)
    value = sys.stdin.read().rstrip("\r\n")
    try:
        store.put(args.secret_ref, value)
    except (RuntimeError, ValueError) as exc:
        print(f"invalid secret: {exc}")
        return 2
    print(f"secret saved: {args.secret_ref}")
    return 0


def _command_secrets_list(args: argparse.Namespace) -> int:
    store = _open_secret_store(args)
    print(json.dumps(store.list_refs(), ensure_ascii=False))
    return 0


def _command_secrets_delete(args: argparse.Namespace) -> int:
    store = _open_secret_store(args)
    try:
        removed = store.delete(args.secret_ref)
    except (RuntimeError, ValueError) as exc:
        print(f"invalid secret reference: {exc}")
        return 2
    if not removed:
        print(f"secret not found: {args.secret_ref}")
        return 1
    print(f"secret deleted: {args.secret_ref}")
    return 0


def _coalesce_optional(value: object, fallback: T) -> T:
    if value is None or value == "":
        return fallback
    return cast(T, value)


def _build_uvicorn_server(
    app: Any,
    *,
    host: str,
    port: int,
    reload: bool,
) -> Any:
    import uvicorn

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
    return uvicorn.Server(config=config)


def _install_signal_handlers(
    server: Any,
    *,
    on_terminate: Callable[[], None] | None = None,
) -> dict[int, Callable[[int, FrameType | None], Any] | int | signal.Handlers | None]:
    previous: dict[
        int, Callable[[int, FrameType | None], Any] | int | signal.Handlers | None
    ] = {}

    def _handle(_signal: int, _frame: FrameType | None) -> None:
        server.should_exit = True
        if on_terminate is not None:
            on_terminate()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, _handle)
    return previous


def _restore_signal_handlers(
    previous: dict[
        int, Callable[[int, FrameType | None], Any] | int | signal.Handlers | None
    ],
) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _write_pid_file(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{pid}\\n", encoding="utf-8")
    os.chmod(pid_file, 0o600)


def _remove_pid_file(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)


def _command_status(args: argparse.Namespace) -> int:
    try:
        paths = ServicePaths(home=Path(args.home).expanduser())
        database_exists = paths.rounds_database_file.exists()
        config_exists = paths.config_file.exists()
        token_exists = paths.token_file.exists()
        print(f"service home: {paths.home}")
        print(
            f"database: {paths.rounds_database_file} "
            f"({'present' if database_exists else 'missing'})"
        )
        print(
            f"config: {paths.config_file} ({'present' if config_exists else 'missing'})"
        )
        print(f"token: {paths.token_file} ({'present' if token_exists else 'missing'})")
        if not (database_exists and config_exists and token_exists):
            print("service layout is incomplete")
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"failed to read service status: {exc}")
        return 1


def _command_doctor(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    paths = ServicePaths(home=home)
    database = Path(
        args.database if args.database is not None else paths.rounds_database_file
    ).expanduser()
    try:
        connection = open_sqlite_connection(database)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to open database for checks: {exc}")
        return 1
    try:
        issues = run_database_integrity_checks(connection)
    finally:
        connection.close()
    if issues:
        print("database integrity failed:")
        for issue in issues:
            print(f" - {issue}")
        return 1
    print("database integrity checks passed")
    if paths.config_file.is_file():
        try:
            config = LocalConfig.from_file(paths.config_file)
            report = build_core_doctor_report(paths=paths, config=config)
            _print_core_doctor_report(report)
        except Exception:  # noqa: BLE001
            print("core diagnostics: unavailable")
    return 0


def _command_core_doctor(args: argparse.Namespace) -> int:
    paths = ServicePaths(home=Path(args.home).expanduser())
    try:
        if not paths.config_file.is_file():
            raise FileNotFoundError("Local config is missing")
        config = LocalConfig.from_file(paths.config_file)
        report = build_core_doctor_report(paths=paths, config=config)
    except Exception:  # noqa: BLE001
        report = {
            "ok": False,
            "error": "unable to load Core diagnostics configuration",
        }
    if bool(args.json_output):
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        _print_core_doctor_report(report)
    return 0 if report.get("ok") is True else 1


def _print_core_doctor_report(report: dict[str, Any]) -> None:
    print(f"core doctor: {'PASS' if report.get('ok') else 'FAIL'}")
    if "error" in report:
        print(f"error: {report['error']}")
        return
    binary = report["binary"]
    signature = report["signature"]
    sandbox = report["sandbox"]
    health = report["health"]
    environment = report["environment"]
    capabilities = sandbox.get("capabilities", {})
    print(f"binary: {binary['path']} ({'present' if binary['present'] else 'missing'})")
    print(f"version: {report.get('version') or 'unavailable'}")
    print(f"sha256: {binary['sha256'] or 'unavailable'}")
    print(f"signature: {signature['status']}")
    print(f"sandbox: {sandbox['level']} ({sandbox['detail']})")
    if capabilities:
        rendered = ", ".join(
            f"{name}={value}" for name, value in sorted(capabilities.items())
        )
        print(f"isolation capabilities: {rendered}")
    else:
        print("isolation capabilities: unavailable")
    missing_requirements = sandbox.get("missing_requirements", [])
    print(
        "missing isolation requirements: "
        + (", ".join(str(item) for item in missing_requirements) or "none")
    )
    print(
        "health: "
        f"{'healthy' if health['healthy'] else 'unhealthy'} "
        f"protocol={health['protocol_version'] or 'unavailable'} "
        f"schema={health['schema_version'] or 'unavailable'}"
    )
    print(f"environment keys: {', '.join(environment['keys']) or 'none'}")
    print(
        "secret-like environment keys: "
        f"{', '.join(environment['secret_like_keys']) or 'none'}"
    )


def _command_rotate_token(args: argparse.Namespace) -> int:
    try:
        paths, _config, token = initialize_local_layout(
            home=Path(args.home).expanduser(),
            force=False,
            rotate_token=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"failed to rotate token: {exc}")
        return 1
    print(f"token rotated for {paths.home}")
    print(f"token file: {paths.token_file}")
    if not token:
        print("token is empty after rotation")
        return 1
    return 0


def _command_serve(args: argparse.Namespace) -> int:
    """Run the API through the single LocalRuntime composition owner."""

    paths, config, token = initialize_local_layout(home=Path(args.home).expanduser())
    host = _coalesce_optional(args.host, config.bind_host)
    port = int(_coalesce_optional(args.port, config.bind_port))
    if not config.allow_remote_bind and host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "refusing non-local bind; set allow_remote_bind=true explicitly",
            file=sys.stderr,
        )
        return 2

    runtime = LocalRuntime(
        paths=paths,
        config=config,
        api_token=token,
        core_gateway_factory=lambda: _build_core_gateway(paths=paths, config=config),
        connection_factory=open_sqlite_connection,
        migration_runner=migrations.apply_migrations,
        lock_factory=ServiceLock,
        pid_writer=_write_pid_file,
        pid_remover=_remove_pid_file,
    )
    try:
        runtime.start_capture()
    except ServiceLockError as exc:
        print(f"failed to acquire service lock: {exc}", file=sys.stderr)
        runtime.stop()
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI reports safe startup failure
        print(f"failed to start local runtime: {exc}", file=sys.stderr)
        runtime.stop()
        return 1

    if config.core_security.profile == "secure" and not runtime.secure_serving_ready:
        safe_code = runtime.core_error_code or "unavailable"
        print(
            "refusing to serve secure runtime: authenticated Core serving plane "
            f"is not ready (error_code={safe_code})",
            file=sys.stderr,
        )
        runtime.stop()
        return 1
    if config.core_security.profile == "permissive":
        print(
            "warning: serving with permissive Core security profile; "
            "isolation guarantees are not enforced",
            file=sys.stderr,
        )

    settings = Settings(
        rounds_database_path=runtime.database_path,
        api_token=token,
        service_lock_path=paths.service_lock_file,
        max_raw_round_bytes=config.max_raw_round_bytes,
        raw_round_retention_days=config.raw_round_retention_days,
        runtime_supervisor=_build_runtime_supervisor(
            config=config,
            host=host,
            port=port,
            activity_probe=runtime.activity_report,
        ),
    )
    app = create_app(
        application=runtime,
        settings=settings,
    )
    server = _build_uvicorn_server(
        app=app,
        host=host,
        port=port,
        reload=bool(args.reload),
    )
    installed_handlers = _install_signal_handlers(server)

    def finish_runtime_start() -> None:
        try:
            runtime.finish_start()
        except Exception:
            logger.exception("background runtime initialization failed")

    startup_thread = threading.Thread(
        target=finish_runtime_start,
        name="ledgermind-startup-maintenance",
        daemon=True,
    )
    startup_thread.start()
    try:
        server.run()
    except KeyboardInterrupt:
        return 0
    finally:
        _restore_signal_handlers(installed_handlers)
        runtime.request_stop()
        startup_thread.join(timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)
        runtime.stop()
    return 0


def _worker_recovery_pending(report: dict[str, Any]) -> bool:
    """Allow healthy workers to drain bounded Core work during startup.

    A non-empty operational, background, or embedding queue is work for the
    Local-owned workers, not a reason to stop those workers before they can
    process it. All security and execution dependencies must still be ready,
    and terminal worker failures remain fatal.
    """

    if report.get("readiness_reason") != "object_facet_not_ready":
        return False
    components = report.get("components")
    if not isinstance(components, dict):
        return False
    object_facet = components.get("object_facet")
    if not isinstance(object_facet, dict):
        return False
    required_ready = ("core", "inference", "workers")
    if any(
        not isinstance(components.get(name), dict) or not components[name].get("ready")
        for name in required_ready
    ):
        return False
    backlog = sum(
        max(int(object_facet.get(name) or 0), 0)
        for name in (
            "operational_backlog",
            "background_backlog",
            "embedding_backlog",
        )
    )
    return backlog > 0 and not bool(report.get("terminal_worker_failure"))


def _build_runtime_supervisor(
    *,
    config: LocalConfig,
    host: str,
    port: int,
    activity_probe: Callable[[], Mapping[str, object]] | None = None,
) -> object:
    from ledgermind_local.installer.paths import InstallerPaths
    from ledgermind_local.runtime.supervisor import RuntimeSupervisor

    endpoint_host = host if host in {"127.0.0.1", "localhost", "::1"} else "127.0.0.1"
    return RuntimeSupervisor(
        InstallerPaths(),
        endpoint=f"http://{endpoint_host}:{port}",
        idle_shutdown_seconds=(
            config.runtime_residency.idle_timeout_seconds
            if config.runtime_residency.mode == "idle"
            else 0.0
        ),
        lease_ttl_seconds=config.runtime_residency.lease_ttl_seconds,
        # This supervisor is embedded in the Local process and owns only the
        # HTTP lease bridge.  The outer installer supervisor owns the Local
        # and embedding processes and runs the single detached idle reaper.
        # Letting both instances manage process lifetime races on the shared
        # runtime state and can erase the authoritative PID records while the
        # services are still alive.
        automatic_shutdown=False,
        process_owner=False,
        max_session_ttl_seconds=(config.runtime_residency.session_safety_ttl_seconds),
        residency_mode=config.runtime_residency.mode,
        commands={},
        activity_probe=activity_probe,
    )


def _build_core_backup_service(
    *, paths: ServicePaths, config: LocalConfig
) -> tuple[CoreGateway, CoreBackupService]:
    gateway = _build_core_gateway(paths=paths, config=config)
    try:
        service = CoreBackupService(
            gateway=gateway,
            core_data_dir=paths.core_data_dir,
            rounds_database_path=paths.resolve_rounds_database_path(
                config.rounds_database_path
            ),
        )
    except BaseException:
        close = getattr(gateway, "close", None)
        if callable(close):
            close()
        raise
    return gateway, service


def _build_coordinated_restore_service(
    *,
    gateway: CoreGateway,
    backup_service: CoreBackupService,
    rounds_database_path: Path,
) -> CoordinatedRestoreService:
    """Build the B1 journaled restore owner around the Core gateway."""

    stop_candidate = getattr(gateway, "close", None)
    health_candidate = getattr(gateway, "health", None)
    supervisor = getattr(gateway, "_supervisor", None)
    start_candidate = getattr(gateway, "start", None)
    if not callable(start_candidate):
        start_candidate = getattr(supervisor, "start", None)
    if (
        not callable(stop_candidate)
        or not callable(start_candidate)
        or not callable(health_candidate)
    ):
        raise CoreBackupError("Core gateway cannot be restarted for restore")
    return CoordinatedRestoreService(
        core_backup_service=backup_service,
        rounds_database_path=rounds_database_path,
        journal_path=rounds_database_path.with_name("restore-journal.json"),
        stop_core=cast(Callable[[], object], stop_candidate),
        start_core=cast(Callable[[], object], start_candidate),
        health_check=cast(Callable[[], object], health_candidate),
    )


def _command_backup_create(args: argparse.Namespace) -> int:
    """Create a Core-owned backup archive without opening Core storage."""

    gateway: Any | None = None
    try:
        paths, config, _token = initialize_local_layout(
            home=Path(args.home).expanduser()
        )
        database_path = paths.resolve_rounds_database_path(config.rounds_database_path)
        with ServiceLock(paths.service_lock_file):
            connection = open_sqlite_connection(database_path)
            try:
                migrations.apply_migrations(connection)
                connection.commit()
            finally:
                connection.close()
            gateway, service = _build_core_backup_service(paths=paths, config=config)
            destination = (
                args.destination if args.destination is not None else paths.backups_dir
            )
            archive = service.create_backup(destination)
        print(f"backup created: {archive}")
        return 0
    except (
        CoreBackupError,
        ServiceLockError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"backup unavailable: {exc}", file=sys.stderr)
        return 1
    finally:
        if gateway is not None:
            close = getattr(gateway, "close", None)
            if callable(close):
                close()


def _command_backup_restore(args: argparse.Namespace) -> int:
    """Restore Local rounds through the B1 coordinated journaled saga."""

    gateway: CoreGateway | None = None
    prepared: object | None = None
    try:
        paths, config, _token = initialize_local_layout(
            home=Path(args.home).expanduser()
        )
        target = Path(
            args.database
            if args.database is not None
            else paths.resolve_rounds_database_path(config.rounds_database_path)
        ).expanduser()
        with ServiceLock(paths.service_lock_file):
            gateway, backup_service = _build_core_backup_service(
                paths=paths, config=config
            )
            restore_service = _build_coordinated_restore_service(
                gateway=gateway,
                backup_service=backup_service,
                rounds_database_path=target,
            )
            prepared = restore_service.prepare_restore(args.source)
            result = restore_service.apply_restore(prepared)
            if result.state != "committed":
                raise CoordinatedRestoreError(
                    "restore_not_committed",
                    "coordinated restore did not commit",
                    restore_id=result.restore_id,
                )
            health = getattr(gateway, "health", None)
            if callable(health):
                health_result = health()
                if not bool(getattr(health_result, "healthy", health_result is True)):
                    raise CoordinatedRestoreError(
                        "restore_health_failed",
                        "Core health check failed after restore",
                        restore_id=result.restore_id,
                    )
            initialize_local_layout(home=paths.home, rotate_token=True)
        print(f"backup restored: {args.source}")
        return 0
    except CoordinatedRestoreError as exc:
        print(f"restore unavailable: {exc.code}", file=sys.stderr)
        return 1
    except (
        CoreBackupError,
        ServiceLockError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"restore unavailable: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        cleanup = getattr(prepared, "cleanup", None)
        if callable(cleanup):
            cleanup()
        if gateway is not None:
            close = getattr(gateway, "close", None)
            if callable(close):
                close()


def _command_maintenance_retention(args: argparse.Namespace) -> int:
    """Run a bounded retention pass under the same service lock as serve."""

    try:
        paths, config, _token = initialize_local_layout(
            home=Path(args.home).expanduser()
        )
        database_path = paths.resolve_rounds_database_path(config.rounds_database_path)
        with ServiceLock(paths.service_lock_file):
            connection = open_sqlite_connection(database_path)
            try:
                migrations.apply_migrations(connection)
                connection.commit()
            finally:
                connection.close()
            result = RawRoundRetentionWorker(database_path).process_once(
                limit=args.limit
            )
        print(json.dumps({"purged": result.purged}, sort_keys=True))
        return 0
    except ServiceLockError as exc:
        print(f"maintenance unavailable: {exc}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError, sqlite3.DatabaseError) as exc:
        print(f"retention failed: {exc}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    installer_commands = {
        "install",
        "configure",
        "repair",
        "update",
        "uninstall",
        "status",
        "export-config",
        "import-config",
        "runtime",
    }
    command = _first_command(raw_argv)
    if command in installer_commands:
        from ledgermind_local.installer.cli import main as installer_main

        return installer_main(raw_argv)
    if command == "doctor" and "--database" not in raw_argv:
        from ledgermind_local.installer.cli import main as installer_main

        return installer_main(raw_argv)
    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    return int(args.func(args))


def _first_command(argv: Sequence[str]) -> str | None:
    """Return the first subcommand without matching option values as commands."""

    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--home":
            index += 2
            continue
        if value.startswith(("--home=", "-")):
            index += 1
            continue
        return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
