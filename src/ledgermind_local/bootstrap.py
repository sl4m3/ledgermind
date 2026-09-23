"""Bootstrap utilities for the Local service and its Rust Core boundary."""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledgermind_inference.core_task_executor import CoreTaskExecutor
from ledgermind_inference.embedding_provider import EmbeddingProvider
from ledgermind_inference.openai_vectorizer import OpenAIEmbeddingVectorizer
from ledgermind_inference.strict import STRICT_JSON_SCHEMA_MODE
from ledgermind_inference.structured_json_provider import StructuredJsonProvider

from ledgermind_local.config import CURRENT_CONFIG_VERSION, LocalConfig, WorkerConfig
from ledgermind_local.core_gateway import (
    CoreGateway,
    ProcessCoreGateway,
    RunControlMaintenanceCommand,
    TransientCoreError,
)
from ledgermind_local.core_gateway.compatibility import (
    compatibility_reason,
    knowledge_schema_supported,
)
from ledgermind_local.core_gateway.security_policy import (
    build_core_isolation_requirements,
)
from ledgermind_local.core_gateway.signing import verify_core_binary
from ledgermind_local.core_gateway.supervisor import (
    CoreSupervisor,
    CoreSupervisorBusy,
    CoreSupervisorCrashed,
    CoreSupervisorError,
    CoreSupervisorTimeout,
)
from ledgermind_local.inference.embedding_provider import PersistentEmbeddingCache
from ledgermind_local.inference.gguf_vectorizer import GGUFVectorizer
from ledgermind_local.inference.profile_slots import (
    DatabaseBackedProfileResolver,
    ProfileSlot,
)
from ledgermind_local.inference.profile_store import (
    DatabaseBackedCapabilityStore,
    InferenceProfileStore,
)
from ledgermind_local.inference.secrets import SecretStore
from ledgermind_local.maintenance.coordinated_restore import (
    CoordinatedRestoreError,
    CoordinatedRestoreService,
)
from ledgermind_local.maintenance.core_backup import CoreBackupService
from ledgermind_local.paths import ServicePaths
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.persistence.contract_migration import migrate_contract_payloads
from ledgermind_local.persistence.migrations import MigrationError
from ledgermind_local.raw_rounds import RawRoundIngestHandler
from ledgermind_local.scheduler import (
    CoreCommandWorker,
    CoreExecutionTaskWorker,
    GuardedWorkerLoop,
    RawRoundRetentionWorker,
)
from ledgermind_local.scheduler.worker_state import WorkerState, WorkerStateSnapshot
from ledgermind_local.service_lock import ServiceLock

logger = logging.getLogger(__name__)

# Core model-task execution is bounded at 300 seconds.  Keep a grace window
# on the Core lease so a slow reasoning provider cannot be claimed twice while
# Local is still completing the first request.
MIN_CORE_MODEL_TASK_LEASE_SECONDS = 360


def _build_runtime_vectorizer_factory(config: LocalConfig) -> Callable[[], Any]:
    """Build the technical embedding backend used by generic Core tasks."""

    if not config.embedding.enabled:

        def unavailable_vectorizer() -> Any:
            raise RuntimeError("local embedding backend is disabled")

        return unavailable_vectorizer

    if config.embedding.provider_mode == "api":
        if (
            not config.embedding.endpoint
            or not config.embedding.model
            or not config.embedding.dimensions
            or not config.embedding.secret_ref
        ):
            raise RuntimeError("API embedding configuration is incomplete")
        token_store = SecretStore(config.inference_secrets_path)
        token = token_store.get(config.embedding.secret_ref)
        return lambda: OpenAIEmbeddingVectorizer(
            endpoint=config.embedding.endpoint or "",
            token=token,
            model=config.embedding.model or "",
            dimensions=config.embedding.dimensions,
            batch_size=config.embedding.batch_size,
            max_concurrency=config.embedding.max_concurrency,
            timeout_seconds=config.embedding.timeout_seconds,
        )

    model_path = Path(config.embedding.model_path).expanduser()
    return lambda: GGUFVectorizer(
        model_path=model_path,
        gpu_layers=config.embedding.gpu_layers,
    )


def build_ingest_raw_round_handler(
    *,
    database_path: str | Path,
    max_raw_round_bytes: int = 5_000_000,
    retention_days: int = 30,
) -> RawRoundIngestHandler:
    """Build the Local-owned RawRound capture handler."""

    return RawRoundIngestHandler(
        database_path=database_path,
        max_raw_round_bytes=max_raw_round_bytes,
        retention_days=retention_days,
    )


@dataclass(slots=True)
class _RuntimeWorkerHandle:
    """One worker, its guarded loop and its lifecycle state."""

    name: str
    config: WorkerConfig
    worker: object
    loop: GuardedWorkerLoop
    state: WorkerState


def build_process_core_gateway(
    *, paths: ServicePaths, config: LocalConfig
) -> ProcessCoreGateway:
    """Build the process Core boundary without starting the child process."""

    command_path = paths.resolve_core_path(config.core_binary_path)
    signature_path = paths.resolve_core_path(config.core_signature_path)
    public_key_path = paths.resolve_core_path(config.core_public_key_path)
    knowledge_database_path = paths.resolve_knowledge_database_path(
        config.knowledge_database_path
    )
    core_data_dir = knowledge_database_path.parent
    core_data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    signature_verified = False
    if config.verify_core_signature:
        verify_core_binary(
            command_path,
            signature_path=signature_path,
            public_key_path=public_key_path,
        )
        signature_verified = True
    requirements = build_core_isolation_requirements(
        config.core_security,
        verify_core_signature=config.verify_core_signature,
    )
    supervisor = CoreSupervisor(
        [str(command_path), "--database", str(knowledge_database_path)],
        startup_timeout_seconds=config.core_startup_timeout_seconds,
        operation_timeout_seconds=config.core_request_timeout_seconds,
        core_data_dir=core_data_dir,
        blocked_data_dirs=(paths.home,),
        rounds_database_path=paths.resolve_rounds_database_path(
            config.rounds_database_path
        ),
        runtime_paths=(core_data_dir,),
        isolation_requirements=requirements,
        strict_isolation=(
            config.core_security.profile == "secure"
            or any(requirements.as_dict().values())
        ),
        binary_signature_verified=signature_verified,
        semantic_language=config.semantic_language,
    )
    return ProcessCoreGateway(supervisor)


class LocalRuntime:
    """Own the Local service lifecycle from migration to shutdown.

    Core is deliberately optional for capture: a failed Core handshake, missing
    daemon or unavailable secure sandbox leaves the Local RawRound writer alive,
    while full readiness remains false and Core-dependent workers are not started.
    """

    _WORKER_ORDER = (
        "retention",
        "core_commands",
        "core_model_tasks",
    )

    def __init__(
        self,
        *,
        paths: ServicePaths,
        config: LocalConfig,
        api_token: str | None,
        database_path: str | Path | None = None,
        core_gateway: CoreGateway | None = None,
        core_gateway_factory: Callable[[], CoreGateway] | None = None,
        migration_runner: Callable[[sqlite3.Connection], object] | None = None,
        contract_migration_runner: Callable[..., object] | None = None,
        connection_factory: Callable[
            [str | Path], sqlite3.Connection
        ] = open_sqlite_connection,
        lock_factory: Callable[[Path], ServiceLock] = ServiceLock,
        pid_writer: Callable[[Path, int], None] | None = None,
        pid_remover: Callable[[Path], None] | None = None,
        worker_factories: Mapping[str, Callable[[LocalRuntime], object]] | None = None,
    ) -> None:
        self.paths = paths
        self.config = config
        self.api_token = api_token
        self.database_path = Path(
            database_path
            or paths.resolve_rounds_database_path(config.rounds_database_path)
        ).expanduser()
        self.core_gateway = core_gateway
        self.core_gateway_factory = core_gateway_factory or (
            lambda: build_process_core_gateway(paths=self.paths, config=self.config)
        )
        self.migration_runner = migration_runner or migrations.apply_migrations
        self.contract_migration_runner = contract_migration_runner
        self.connection_factory = connection_factory
        self.lock_factory = lock_factory
        self.pid_writer = pid_writer or _write_runtime_pid
        self.pid_remover = pid_remover or _remove_runtime_pid
        self.worker_factories = dict(worker_factories or {})
        self._service_lock: ServiceLock | None = None
        self._lock_acquired = False
        self._pid_owned = False
        self._started = False
        self._initialization_complete = False
        self._starting = False
        self._stop_requested = False
        self._migrations_applied = False
        self._core_ready = False
        self._core_protocol_version: int | None = None
        self._core_schema_version: int | None = None
        self._core_error_code: str | None = None
        self._component_errors: dict[str, str] = {}
        self._workers: dict[str, _RuntimeWorkerHandle] = {}
        self._prepared_workers: dict[str, object] = {}
        self._raw_round_handler: RawRoundIngestHandler | None = None
        self._context_gateway: object | None = None
        self._backup_service: CoreBackupService | None = None
        self._restore_service: CoordinatedRestoreService | None = None
        self._restore_status: dict[str, object] | None = None
        self._required_core_capabilities: tuple[str, ...] = ()
        self._worker_observations: dict[str, dict[str, object]] = {}
        self._shutdown_incomplete = False
        self._shutdown_timed_out_workers: list[str] = []
        self._control_maintenance: dict[str, object] | None = None
        self._object_facet_statistics: dict[str, object] | None = None
        self._object_facet_bootstrap_pending = False
        self._last_core_activity_snapshot: dict[str, object] | None = None
        self._last_automatic_recovery_at = 0.0

    @property
    def started(self) -> bool:
        return self._started

    @property
    def capture_ready(self) -> bool:
        return bool(
            self._started
            and self._migrations_applied
            and self._service_lock is not None
            and self._lock_acquired
            and self._raw_round_handler is not None
            and callable(getattr(self._raw_round_handler, "handle", None))
        )

    @property
    def initialization_complete(self) -> bool:
        """Whether maintenance and all configured workers finished starting."""

        return self._initialization_complete

    @property
    def core_error_code(self) -> str | None:
        """Return the content-free Core startup diagnostic, if any."""

        return self._core_error_code

    @property
    def secure_serving_ready(self) -> bool:
        """Whether HTTP may bind without weakening the secure Core boundary.

        Control maintenance and worker startup are deliberately excluded: they
        can take tens of seconds on a large database, while authenticated
        capture and recall are already safe after the signed Core handshake.
        """

        isolation = self._isolation_report()
        capabilities = self._capabilities_report()
        restore = self._restore_status or {"ready": True}
        return bool(
            self.capture_ready
            and self._core_ready
            and knowledge_schema_supported(self._core_schema_version)
            and isolation.get("ready", False)
            and capabilities.get("ready", False)
            and restore.get("ready", False)
        )

    @property
    def full_ready(self) -> bool:
        report = self.health_report()
        return bool(report["full_ready"])

    @property
    def context_gateway(self) -> object | None:
        return self._context_gateway

    @property
    def ingest_handler(self) -> RawRoundIngestHandler | None:
        """B2 composition name for the Local-owned capture handler."""

        return self._raw_round_handler

    @property
    def worker_loops(self) -> dict[str, GuardedWorkerLoop]:
        return {name: handle.loop for name, handle in self._workers.items()}

    @property
    def retention_worker(self) -> object | None:
        handle = self._workers.get("retention")
        return handle.worker if handle is not None else None

    @property
    def backup_service(self) -> object | None:
        return getattr(self, "_backup_service", None)

    @property
    def restore_service(self) -> CoordinatedRestoreService | None:
        """Return the B1 coordinated restore owner for this runtime."""

        return self._restore_service

    @property
    def worker_states(self) -> dict[str, WorkerStateSnapshot]:
        return {name: handle.state.snapshot() for name, handle in self._workers.items()}

    def worker_state(self, name: str) -> WorkerStateSnapshot | None:
        handle = self._workers.get(name)
        return handle.state.snapshot() if handle is not None else None

    def build_ingest_raw_round_handler(self) -> RawRoundIngestHandler:
        if self._raw_round_handler is None:
            self._raw_round_handler = build_ingest_raw_round_handler(
                database_path=self.database_path,
                max_raw_round_bytes=self.config.max_raw_round_bytes,
                retention_days=self.config.raw_round_retention_days,
            )
        return self._raw_round_handler

    def start(self) -> LocalRuntime:
        """Acquire ownership, migrate, then start Core and guarded workers."""

        if self._initialization_complete:
            return self
        self.start_capture()
        try:
            self.finish_start()
        except BaseException:
            self._cleanup_after_failed_start()
            raise
        return self

    def start_capture(self) -> LocalRuntime:
        """Start the durable authenticated serving plane without maintenance."""

        if self._started:
            return self
        if self._shutdown_incomplete:
            if any(handle.loop.is_alive() for handle in self._workers.values()):
                raise RuntimeError("Local runtime shutdown is incomplete")
            self.stop()
        if self._starting:
            raise RuntimeError("Local runtime startup is already in progress")
        self._starting = True
        self._stop_requested = False
        self._initialization_complete = False
        self._component_errors.clear()
        self._workers.clear()
        self._worker_observations.clear()
        self._core_error_code = None
        self._core_ready = False
        self._core_protocol_version = None
        self._core_schema_version = None
        self._required_core_capabilities = ()
        self._restore_status = None
        self._restore_service = None
        self._shutdown_incomplete = False
        self._shutdown_timed_out_workers = []
        self._control_maintenance = None
        self._object_facet_statistics = None
        self._object_facet_bootstrap_pending = False
        self._migrations_applied = False
        self._context_gateway = None
        self._backup_service = None
        self._raw_round_handler = None
        if self.config.core_security.profile == "permissive":
            logger.warning(
                "permissive Core security profile is enabled; isolation guarantees are not enforced"
            )
        try:
            self.paths.home.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.paths.logs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._service_lock = self.lock_factory(self.paths.service_lock_file)
            self._acquire_service_lock()
            self._run_migrations_before_workers()
            self._raw_round_handler = build_ingest_raw_round_handler(
                database_path=self.database_path,
                max_raw_round_bytes=self.config.max_raw_round_bytes,
                retention_days=self.config.raw_round_retention_days,
            )
            self.pid_writer(self.paths.service_pid_file, os.getpid())
            self._pid_owned = True
            # Core is brought up only after Local's durable schema is ready;
            # no worker can observe a partially migrated database.
            self._start_core_if_available()
            self._recover_restore_journal()
            self._build_context_gateway()
            self._started = True
            return self
        except BaseException:
            self._cleanup_after_failed_start()
            raise
        finally:
            self._starting = False

    def finish_start(self) -> LocalRuntime:
        """Complete slow maintenance and worker startup after HTTP can bind."""

        if self._initialization_complete:
            return self
        if not self._started:
            raise RuntimeError("Local capture plane is not started")
        if self._starting:
            raise RuntimeError("Local runtime startup is already in progress")
        self._starting = True
        try:
            self._refresh_object_facet_health()
            if not self._stop_requested:
                self._recover_verified_provider_capability_failures()
            if not self._stop_requested:
                self._start_workers()
            self._initialization_complete = not self._stop_requested
            return self
        except Exception as exc:
            self._component_errors["startup_maintenance"] = _safe_error_code(exc)
            raise
        finally:
            self._starting = False

    def request_stop(self) -> None:
        """Signal all workers without waiting; used by HTTP server signal hooks."""

        self._stop_requested = True
        for handle in reversed(tuple(self._workers.values())):
            handle.loop.request_stop()

    def embed_query(self, memory_space_id: str, query: str) -> tuple[float, ...]:
        """Compute a retrieval embedding through the Local technical backend."""

        return self.embed_query_with_metadata(memory_space_id, query)[0]

    @property
    def retrieval_reranker(self) -> Any | None:
        """Create the configured scorer lazily; disabled installs stay Core-only."""
        if not self.config.reranker.enabled:
            return None
        from ledgermind_local.inference.retrieval_reranker import (
            ApiReranker,
            QwenWorkerReranker,
        )

        scorer = getattr(self, "_retrieval_reranker", None)
        if scorer is None:
            if self.config.reranker.mode == "api":
                secret_ref = self.config.reranker.secret_ref or ""
                token = SecretStore(self.config.inference_secrets_path).get(secret_ref)
                scorer = ApiReranker(
                    self.config.reranker.endpoint or "",
                    token,
                    self.config.reranker.model or "",
                    timeout_seconds=self.config.reranker.timeout_seconds,
                )
            else:
                scorer = QwenWorkerReranker(
                    self.config.reranker.model_path or "", self.config.reranker.device,
                    runtime_path=self.config.reranker.runtime_path,
                )
            self._retrieval_reranker = scorer
        return scorer

    def embed_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        """Compute a retrieval embedding and preserve its model identity."""

        resolver = DatabaseBackedProfileResolver(self.database_path)
        profile = resolver.resolve_profile(memory_space_id, ProfileSlot.EMBEDDING)
        provider = EmbeddingProvider(
            vectorizer_factory=_build_runtime_vectorizer_factory(self.config)
        )
        batch = provider.embed((query,), profile, "retrieval_query")
        return batch.vectors[0], batch.model, batch.model_version

    def embed_object_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        """Compute the asymmetric query vector for object identity passages."""

        resolver = DatabaseBackedProfileResolver(self.database_path)
        profile = resolver.resolve_profile(memory_space_id, ProfileSlot.EMBEDDING)
        provider = EmbeddingProvider(
            vectorizer_factory=_build_runtime_vectorizer_factory(self.config)
        )
        batch = provider.embed(
            (query,),
            profile,
            "object_candidate_query",
            role="query",
        )
        return batch.vectors[0], batch.model, batch.model_version

    def embedding_profile_metadata(self, memory_space_id: str) -> dict[str, object]:
        """Resolve the active embedding identity without exposing provider secrets."""

        resolver = DatabaseBackedProfileResolver(self.database_path)
        profile = resolver.resolve_profile(memory_space_id, ProfileSlot.EMBEDDING)
        provider = EmbeddingProvider(
            vectorizer_factory=_build_runtime_vectorizer_factory(self.config)
        )
        readiness = provider.readiness(profile)
        if not readiness.ready:
            raise RuntimeError(
                f"embedding profile is not ready: {readiness.error_code or 'unknown'}"
            )
        return readiness.to_core_metadata()

    def _embedding_profiles_by_memory_space(self) -> dict[str, dict[str, object]]:
        """Resolve every Local embedding binding for a Core maintenance pass."""

        connection = self.connection_factory(self.database_path)
        try:
            self.migration_runner(connection)
            rows = connection.execute(
                """
                SELECT DISTINCT memory_space_id
                FROM memory_space_model_profiles
                WHERE profile_slot = 'embedding'
                ORDER BY memory_space_id
                """
            ).fetchall()
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        profiles: dict[str, dict[str, object]] = {}
        for row in rows:
            memory_space_id = str(row[0])
            try:
                profiles[memory_space_id] = self.embedding_profile_metadata(
                    memory_space_id
                )
            except Exception as exc:  # noqa: BLE001 - readiness remains content-free
                logger.warning(
                    "embedding profile identity unavailable",
                    extra={
                        "memory_space_id": memory_space_id,
                        "error_code": _safe_error_code(exc),
                    },
                )
        return profiles

    def stop(self) -> None:
        """Stop workers before Core and preserve incomplete shutdown state."""

        if not self._started and self._service_lock is None and not self._pid_owned:
            return
        self.request_stop()
        timed_out_workers: list[str] = []
        for name in reversed(self._WORKER_ORDER):
            handle = self._workers.get(name)
            if handle is None:
                continue
            try:
                result = handle.loop.shutdown(handle.config.shutdown_timeout_seconds)
                stopped = bool(getattr(result, "stopped", False))
            except Exception as exc:  # noqa: BLE001 - shutdown remains observable
                stopped = False
                self._component_errors[name] = _safe_error_code(exc)
                handle.state.mark_shutdown_timed_out()
            if not stopped:
                timed_out_workers.append(name)
                self._component_errors[name] = "shutdown_timeout"

        if timed_out_workers:
            # Keep worker handles, the Core gateway, the lock and all resources
            # reachable by a live worker.  A later stop() can finish the join.
            self._shutdown_incomplete = True
            self._shutdown_timed_out_workers = list(reversed(timed_out_workers))
            self._started = False
            return

        self._shutdown_incomplete = False
        self._shutdown_timed_out_workers = []
        self._workers.clear()
        reranker = getattr(self, "_retrieval_reranker", None)
        if reranker is not None:
            reranker.close()
            self._retrieval_reranker = None
        self._context_gateway = None
        self._backup_service = None
        self._restore_service = None
        self._raw_round_handler = None
        gateway = self.core_gateway
        self.core_gateway = None
        if gateway is not None:
            close = getattr(gateway, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # noqa: BLE001 - cleanup is best effort
                    self._component_errors["core"] = _safe_error_code(exc)
        if self._pid_owned:
            try:
                self.pid_remover(self.paths.service_pid_file)
            finally:
                self._pid_owned = False
        if self._service_lock is not None:
            self._release_service_lock()
            self._service_lock = None
        self._started = False
        self._initialization_complete = False
        self._stop_requested = False

    def _capabilities_report(self) -> dict[str, object]:
        gateway = self.core_gateway
        advertised_operations = getattr(gateway, "advertised_operations", ())
        advertised_capabilities = getattr(gateway, "advertised_capabilities", ())

        def _safe_strings(value: object) -> list[str]:
            if not isinstance(value, (list, tuple, set, frozenset)):
                return []
            return sorted(item for item in value if isinstance(item, str))

        return {
            "ready": self._core_ready,
            "ok": self._core_ready,
            "protocol_version": self._core_protocol_version,
            "schema_version": self._core_schema_version,
            "compatibility_reason": compatibility_reason(
                self._core_protocol_version, self._core_schema_version
            ),
            "required": list(self._required_core_capabilities),
            "advertised_operations": _safe_strings(advertised_operations),
            "advertised_capabilities": _safe_strings(advertised_capabilities),
        }

    def health_report(self) -> dict[str, object]:
        """Return secret-free capture/full readiness and component diagnostics."""

        worker_reports: dict[str, object] = {}
        workers_ready = True
        for name, config_worker in self._configured_workers():
            handle = self._workers.get(name)
            if not config_worker.enabled:
                worker_reports[name] = {"enabled": False, "ready": True}
                continue
            if handle is None:
                error_code = self._component_errors.get(name, "not_started")
                worker_reports[name] = {
                    "enabled": True,
                    "ready": False,
                    "error_code": error_code,
                }
                workers_ready = False
                continue
            state = handle.state.snapshot()
            loop_thread = getattr(handle.loop, "_thread", None)
            alive = bool(loop_thread is not None and loop_thread.is_alive())
            provider_circuit_open = bool(
                getattr(handle.worker, "provider_circuit_open", False)
            )
            ready = bool(
                alive
                and state.healthy
                and name not in self._component_errors
                and not provider_circuit_open
            )
            worker_reports[name] = {
                "enabled": True,
                "ready": ready,
                "error_code": (
                    "provider_configuration_error"
                    if provider_circuit_open
                    else self._component_errors.get(name)
                ),
                "state": {
                    "running": state.running,
                    "healthy": state.healthy,
                    "last_error_code": state.last_error_code,
                    "consecutive_failures": state.consecutive_failures,
                    "processed_count": state.processed_count,
                    "failed_count": state.failed_count,
                    "last_progress_at": state.last_progress_at,
                    "shutdown_timed_out": state.shutdown_timed_out,
                    "degraded": state.degraded,
                },
                "observability": dict(self._worker_observations.get(name, {})),
            }
            workers_ready = workers_ready and ready

        isolation = self._isolation_report()
        capabilities = self._capabilities_report()
        profile_slots = self._profile_slots_report()
        if self._object_facet_bootstrap_pending:
            # The initial control pass schedules the static facet catalogue,
            # while workers drain it asynchronously.  Refresh the bounded
            # control projection on the health path so the prewarm finding is
            # closed after the queue reaches zero; otherwise readiness would
            # wait forever on a stale cached finding.
            self._refresh_object_facet_health()
        statistics = dict(self._object_facet_statistics or {})
        core_report = {
            "ready": self._core_ready,
            "ok": self._core_ready,
            "available": self.core_gateway is not None,
            "error_code": self._core_error_code,
            "protocol_version": self._core_protocol_version,
            "schema_version": self._core_schema_version,
            "compatibility_reason": compatibility_reason(
                self._core_protocol_version, self._core_schema_version
            ),
            "isolation": isolation,
            "capabilities": capabilities,
        }
        capture_ready = self.capture_ready
        core_security_ready = bool(isolation.get("ready", True))
        generic_worker = worker_reports.get("core_model_tasks")
        generic_worker_ready = bool(
            self.config.workers.core_model_tasks.enabled
            and isinstance(generic_worker, dict)
            and generic_worker.get("ready") is True
        )
        inference_ready = bool(
            profile_slots["ready"]
            and generic_worker_ready
            and not self._component_errors.get("core_model_tasks")
        )
        restore = dict(self._restore_status or {"ready": True, "state": "clean"})
        restore_ready = bool(restore.get("ready", False))
        capabilities_ready = bool(capabilities.get("ready", False))
        schema_ready = knowledge_schema_supported(self._core_schema_version)
        control_ready = not bool(self._component_errors.get("control"))
        statistics_ready = not bool(self._component_errors.get("statistics"))
        terminal_worker_failure = any(
            isinstance(observation, dict)
            and _is_positive_int(observation.get("terminal_failures"))
            for observation in self._worker_observations.values()
        )
        legacy_digest_upgrade_required = bool(
            statistics.get("legacy_digest_upgrade_required", False)
        )
        shutdown = {
            "incomplete": self._shutdown_incomplete,
            "timed_out_workers": list(self._shutdown_timed_out_workers),
        }
        retention_report = worker_reports.get(
            "retention", {"enabled": False, "ready": True}
        )
        isolation_report = dict(isolation)
        capabilities_payload = isolation_report.get("capabilities")
        if isinstance(capabilities_payload, dict):
            capabilities_payload = dict(capabilities_payload)
            capabilities_payload.pop("detail", None)
            isolation_report["capabilities"] = capabilities_payload
        object_facet_empty = bool(
            statistics.get("object_count") == 0
            and statistics.get("active_value_count") == 0
            and statistics.get("superseded_value_count") == 0
        )
        object_facet_no_work = all(
            not _is_positive_int(statistics.get(name))
            for name in (
                "operational_backlog",
                "background_backlog",
                "embedding_backlog",
            )
        )
        integrity_finding_count = statistics.get("integrity_finding_count", 0)
        blocking_integrity_finding_count = statistics.get(
            "blocking_integrity_finding_count", integrity_finding_count
        )
        non_blocking_integrity_findings = bool(
            _is_positive_int(integrity_finding_count)
            and not _is_positive_int(blocking_integrity_finding_count)
        )
        object_facet_initializing = bool(
            statistics_ready
            and not legacy_digest_upgrade_required
            and object_facet_empty
            and object_facet_no_work
            and (
                _is_positive_int(statistics.get("integrity_finding_count"))
                or _is_positive_int(statistics.get("missing_card_embeddings"))
                or _is_positive_int(statistics.get("missing_facet_embeddings"))
            )
        )
        object_facet_ready = bool(
            statistics_ready
            and not legacy_digest_upgrade_required
            and (
                all(
                    not _is_positive_int(statistics.get(name))
                    for name in (
                        "blocking_integrity_finding_count",
                        "missing_card_embeddings",
                        "missing_facet_embeddings",
                        "operational_backlog",
                        "background_backlog",
                        "embedding_backlog",
                    )
                )
                or object_facet_initializing
            )
        )
        full_ready = bool(
            capture_ready
            and self._core_ready
            and schema_ready
            and core_security_ready
            and capabilities_ready
            and workers_ready
            and inference_ready
            and control_ready
            and statistics_ready
            and object_facet_ready
            and restore_ready
            and not legacy_digest_upgrade_required
            and not terminal_worker_failure
            and not self._shutdown_incomplete
        )
        readiness_reason = self._readiness_reason(
            schema_ready=schema_ready,
            capabilities_ready=capabilities_ready,
            profile_slots=profile_slots,
            workers_ready=workers_ready,
            inference_ready=inference_ready,
            control_ready=control_ready,
            statistics_ready=statistics_ready,
            object_facet_ready=object_facet_ready,
            object_facet_initializing=object_facet_initializing,
            restore_ready=restore_ready,
        )
        core_report["isolation"] = isolation_report
        degraded_workers = any(
            isinstance(report, dict)
            and isinstance(report.get("state"), dict)
            and bool(report["state"].get("degraded"))
            for report in worker_reports.values()
        )
        degraded = bool(
            degraded_workers
            or self._shutdown_incomplete
            or not restore_ready
            or object_facet_initializing
            or non_blocking_integrity_findings
        )
        workers_component = dict(worker_reports)
        workers_component.update({"ready": workers_ready, "ok": workers_ready})
        control_component = {
            "ready": control_ready,
            "ok": control_ready,
            **dict(self._control_maintenance or {"status": "unavailable"}),
        }
        control_component["ready"] = control_ready
        control_component["ok"] = control_ready
        restore_component = dict(restore)
        restore_component.setdefault("ready", restore_ready)
        restore_component["ok"] = restore_ready
        return {
            "status": "ready"
            if full_ready
            else ("capture-ready" if capture_ready else "unavailable"),
            "capture_ready": capture_ready,
            "full_ready": full_ready,
            "readiness_reason": readiness_reason,
            "degraded_reason": (
                "facet_catalogue_preload"
                if object_facet_initializing
                else ("integrity_findings" if non_blocking_integrity_findings else None)
            ),
            "degraded": degraded,
            "shutdown": shutdown,
            "components": {
                "capture": {
                    "ready": capture_ready,
                    "ok": capture_ready,
                    "migrations_applied": self._migrations_applied,
                    "service_lock_held": self._lock_acquired,
                    "raw_round_writer": self._raw_round_handler is not None,
                },
                "core": core_report,
                "isolation": isolation_report,
                "capabilities": capabilities,
                "restore": restore_component,
                "inference": {
                    "ready": inference_ready,
                    "ok": inference_ready,
                    "profile_slots": profile_slots,
                },
                "control": control_component,
                "object_facet": {
                    **statistics,
                    "ready": object_facet_ready,
                    "ok": object_facet_ready,
                    "initialization_pending": object_facet_initializing,
                    "degraded_reason": (
                        "facet_catalogue_preload"
                        if object_facet_initializing
                        else (
                            "integrity_findings"
                            if non_blocking_integrity_findings
                            else None
                        )
                    ),
                },
                "workers": workers_component,
                "retention": retention_report,
            },
            "workers": worker_reports,
            "missing_profile_slots_by_memory_space": profile_slots[
                "missing_profile_slots_by_memory_space"
            ],
            "operational_backlog": statistics.get("operational_backlog"),
            "background_backlog": statistics.get("background_backlog"),
            "embedding_backlog": statistics.get("embedding_backlog"),
            "control_findings": statistics.get("integrity_finding_count"),
            "blocking_control_findings": statistics.get(
                "blocking_integrity_finding_count"
            ),
            "missing_card_embeddings": statistics.get("missing_card_embeddings"),
            "missing_facet_embeddings": statistics.get("missing_facet_embeddings"),
            "legacy_digest_upgrade_required": legacy_digest_upgrade_required,
            "terminal_worker_failure": terminal_worker_failure,
        }

    def activity_report(self) -> dict[str, object]:
        """Return a fresh, content-free shutdown activity snapshot.

        Local commands cover the durable Local-to-Core handoff. Core backlog
        covers semantic, resolution, and embedding work scheduled after that
        handoff completes. Both must be empty before the runtime is idle.
        """

        local_leased = 0
        local_pending = 0
        try:
            connection = self.connection_factory(self.database_path)
            try:
                row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN status = 'delivering' THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN status IN ('pending', 'retry_wait') THEN 1 ELSE 0 END), 0)
                    FROM core_commands
                    """
                ).fetchone()
            finally:
                connection.close()
            local_leased = max(int(row[0]), 0) if row is not None else 0
            local_pending = max(int(row[1]), 0) if row is not None else 0

            gateway = self.core_gateway
            get_statistics = getattr(
                gateway, "try_get_object_facet_statistics", None
            )
            if not callable(get_statistics):
                # Compatibility for alternate/test gateways. The production
                # process gateway always exposes the bounded diagnostic path.
                get_statistics = getattr(gateway, "get_object_facet_statistics", None)
            if not callable(get_statistics):
                raise TypeError("Core activity statistics are unavailable")
            statistics = get_statistics(f"local-activity:{os.getpid()}:{uuid.uuid4()}")
            core_backlog: dict[str, int] = {}
            for name in (
                "operational_backlog",
                "background_backlog",
                "embedding_backlog",
            ):
                value = getattr(statistics, name)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"Core activity {name} must be an integer")
                core_backlog[name] = max(value, 0)
        except Exception as exc:  # noqa: BLE001 - shutdown must fail closed
            if isinstance(exc, CoreSupervisorBusy):
                error_code = "core_activity_busy"
            elif isinstance(exc, CoreSupervisorTimeout):
                error_code = "core_activity_timeout"
            elif isinstance(
                exc,
                (CoreSupervisorCrashed, CoreSupervisorError, ConnectionError),
            ):
                error_code = "core_activity_unreachable"
            elif isinstance(exc, (TransientCoreError, TypeError, ValueError)):
                error_code = "activity_response_invalid"
            else:
                error_code = _safe_error_code(exc)

            cached = self._last_core_activity_snapshot or {}
            cached_core_value = cached.get("core", {})
            cached_core = (
                dict(cached_core_value)
                if isinstance(cached_core_value, Mapping)
                else {}
            )
            return {
                "schema_version": 1,
                "known": False,
                "stale": True,
                "quiescent": False,
                "leased_tasks": local_leased,
                "pending_writes": local_pending
                + sum(
                    value
                    for value in cached_core.values()
                    if isinstance(value, int) and not isinstance(value, bool)
                ),
                "error_code": error_code,
                "observed_at": cached.get("observed_at"),
                "local": {
                    "delivering_commands": local_leased,
                    "pending_commands": local_pending,
                },
                "core": cached_core,
            }

        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._last_core_activity_snapshot = {
            "core": dict(core_backlog),
            "observed_at": observed_at,
        }
        leased_tasks = local_leased
        pending_writes = local_pending + sum(core_backlog.values())
        return {
            "schema_version": 1,
            "known": True,
            "stale": False,
            "quiescent": leased_tasks == 0 and pending_writes == 0,
            "leased_tasks": leased_tasks,
            "pending_writes": pending_writes,
            "observed_at": observed_at,
            "local": {
                "delivering_commands": local_leased,
                "pending_commands": local_pending,
            },
            "core": core_backlog,
        }

    def _readiness_reason(
        self,
        *,
        schema_ready: bool,
        capabilities_ready: bool,
        profile_slots: Mapping[str, object],
        workers_ready: bool,
        inference_ready: bool,
        control_ready: bool,
        statistics_ready: bool,
        object_facet_ready: bool,
        object_facet_initializing: bool,
        restore_ready: bool,
    ) -> str | None:
        """Return one stable blocker code for status/doctor consumers."""

        if not self._migrations_applied:
            return "local_db_migration_incomplete"
        if self._core_error_code:
            return self._core_error_code
        if self.core_gateway is None or not self._core_ready:
            return "core_unreachable"
        compatibility = compatibility_reason(
            self._core_protocol_version, self._core_schema_version
        )
        if compatibility is not None:
            return compatibility
        if not schema_ready:
            return "core_knowledge_schema_incompatible"
        if not capabilities_ready:
            return "core_capability_missing"
        if not bool(profile_slots.get("ready", False)):
            return "provider_profile_invalid"
        if not workers_ready or not inference_ready:
            return "worker_not_ready"
        if not control_ready or not statistics_ready:
            return "control_integrity_not_ready"
        if not object_facet_ready:
            return (
                "object_facet_initializing"
                if object_facet_initializing
                else "object_facet_not_ready"
            )
        if not restore_ready:
            return "restore_inconsistent"
        if self._shutdown_incomplete:
            return "shutdown_incomplete"
        return None

    def _acquire_service_lock(self) -> None:
        if self._service_lock is None:
            raise RuntimeError("service lock is not configured")
        acquire = getattr(self._service_lock, "acquire", None)
        if callable(acquire):
            acquire()
        else:
            enter = getattr(self._service_lock, "__enter__", None)
            if not callable(enter):
                raise TypeError("service lock does not implement acquire()")
            enter()
        self._lock_acquired = True

    def _release_service_lock(self) -> None:
        if self._service_lock is None or not self._lock_acquired:
            return
        release = getattr(self._service_lock, "release", None)
        if callable(release):
            release()
        else:
            exit_method = getattr(self._service_lock, "__exit__", None)
            if callable(exit_method):
                exit_method(None, None, None)
        self._lock_acquired = False

    def _run_migrations_before_workers(self) -> None:
        connection = self.connection_factory(self.database_path)
        entered = False
        try:
            enter = getattr(connection, "__enter__", None)
            if callable(enter):
                connection = enter()
                entered = True
            self.migration_runner(connection)
            if self.contract_migration_runner is None:
                migrate_contract_payloads(
                    database_path=self.database_path,
                    connection=connection,
                    stop_delivery=self._stop_delivery_integration,
                )
            else:
                self.contract_migration_runner(connection)
            if getattr(connection, "in_transaction", False):
                connection.commit()
            execute = getattr(connection, "execute", None)
            if callable(execute):
                result = execute("PRAGMA integrity_check").fetchone()
                if result is not None and result[0] != "ok":
                    raise RuntimeError("Local database integrity check failed")
            self._migrations_applied = True
        finally:
            if entered:
                exit_method = getattr(connection, "__exit__", None)
                if callable(exit_method):
                    exit_method(None, None, None)
            else:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()

    def _stop_delivery_integration(self) -> None:
        """Ensure no already-created delivery loop can write during cutover."""

        handle = self._workers.get("core_commands")
        if handle is None or not handle.loop.is_alive():
            return
        handle.loop.request_stop()
        result = handle.loop.shutdown(handle.config.shutdown_timeout_seconds)
        if not bool(getattr(result, "stopped", False)):
            raise RuntimeError(
                "Core delivery worker did not stop for contract migration"
            )

    def _build_restore_service(self) -> CoordinatedRestoreService | None:
        backup_service = self._backup_service
        gateway = self.core_gateway
        if backup_service is None or gateway is None:
            return None
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
            raise TypeError("Core gateway cannot be restarted for restore")
        return CoordinatedRestoreService(
            core_backup_service=backup_service,
            rounds_database_path=self.database_path,
            journal_path=self.database_path.with_name("restore-journal.json"),
            stop_core=stop_candidate,
            start_core=start_candidate,
            health_check=health_candidate,
        )

    def _recover_restore_journal(self) -> None:
        """Recover a durable restore journal before advertising readiness."""

        journal_path = self.database_path.with_name("restore-journal.json")
        if not journal_path.exists():
            self._restore_status = {"ready": True, "state": "clean"}
            return
        if self._backup_service is None or self.core_gateway is None:
            self._restore_status = {
                "ready": False,
                "state": "pending",
                "error_code": "restore_pending",
            }
            self._component_errors["restore"] = "restore_pending"
            return
        try:
            self._restore_service = self._build_restore_service()
            if self._restore_service is None:
                raise RuntimeError("restore service is unavailable")
            result = self._restore_service.recover()
            self._restore_status = {
                "ready": True,
                "state": result.state if result is not None else "clean",
            }
        except CoordinatedRestoreError as exc:
            error_code = exc.code if exc.code else "restore_inconsistent"
            self._restore_status = {
                "ready": False,
                "state": "restore_inconsistent" if exc.inconsistent else "pending",
                "error_code": error_code,
            }
            self._component_errors["restore"] = error_code
        except Exception as exc:  # noqa: BLE001 - startup must expose, not hide, journals
            error_code = _safe_error_code(exc)
            self._restore_status = {
                "ready": False,
                "state": "pending",
                "error_code": error_code,
            }
            self._component_errors["restore"] = error_code

    def _start_core_if_available(self) -> None:
        try:
            if self.core_gateway is None:
                self.core_gateway = self.core_gateway_factory()
            if self.core_gateway is None:
                raise RuntimeError("Core gateway is unavailable")
            required = ["base", "maintenance", "object_facet"]
            workers = self.config.workers
            if workers.core_model_tasks.enabled:
                required.append("execution_tasks")
            self._required_core_capabilities = tuple(required)
            start = getattr(self.core_gateway, "start", None)
            if callable(start):
                start()
            require_capabilities = getattr(
                self.core_gateway, "require_capabilities", None
            )
            if callable(require_capabilities):
                require_capabilities(*required)
            health = getattr(self.core_gateway, "health", None)
            if callable(health):
                health_result = health()
                self._core_ready = bool(
                    getattr(health_result, "healthy", health_result is True)
                )
                health_schema = getattr(health_result, "schema_version", None)
                if isinstance(health_schema, int) and not isinstance(
                    health_schema, bool
                ):
                    self._core_schema_version = health_schema
                health_protocol = getattr(health_result, "protocol_version", None)
                if isinstance(health_protocol, int) and not isinstance(
                    health_protocol, bool
                ):
                    self._core_protocol_version = health_protocol
            else:
                self._core_ready = True
            advertised_schema = getattr(
                self.core_gateway, "advertised_schema_version", None
            )
            if isinstance(advertised_schema, int) and not isinstance(
                advertised_schema, bool
            ):
                self._core_schema_version = advertised_schema
            advertised_protocol = getattr(
                self.core_gateway, "advertised_protocol_version", None
            )
            if isinstance(advertised_protocol, int) and not isinstance(
                advertised_protocol, bool
            ):
                self._core_protocol_version = advertised_protocol
            if not self._core_ready:
                self._core_error_code = "core_unreachable"
                raise RuntimeError("Core health check failed")
            self._backup_service = CoreBackupService(
                gateway=self.core_gateway,
                core_data_dir=self.paths.resolve_knowledge_database_path(
                    self.config.knowledge_database_path
                ).parent,
                rounds_database_path=self.database_path,
            )
        except Exception as exc:  # noqa: BLE001 - capture remains available
            self._core_ready = False
            self._core_error_code = self._core_error_code or _safe_error_code(exc)
            gateway = self.core_gateway
            if gateway is not None:
                close = getattr(gateway, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.debug("failed to close Core gateway", exc_info=True)
            self.core_gateway = None

    def _refresh_object_facet_health(self) -> None:
        """Run the Core control pass and cache content-free readiness stats."""

        gateway = self.core_gateway
        if gateway is None:
            return
        run_control = getattr(gateway, "run_control_maintenance", None)
        get_statistics = getattr(gateway, "get_object_facet_statistics", None)

        def refresh_statistics() -> None:
            if not callable(get_statistics):
                self._component_errors["statistics"] = "unsupported"
                return
            try:
                result = get_statistics(f"local-stats:{os.getpid()}:{uuid.uuid4()}")
                self._object_facet_statistics = {
                    name: getattr(result, name)
                    for name in (
                        "object_count",
                        "active_value_count",
                        "superseded_value_count",
                        "operational_backlog",
                        "background_backlog",
                        "embedding_backlog",
                        "integrity_finding_count",
                        "blocking_integrity_finding_count",
                        "missing_card_embeddings",
                        "missing_facet_embeddings",
                        "legacy_digest_upgrade_required",
                    )
                    if hasattr(result, name)
                }
            except Exception as exc:  # noqa: BLE001 - diagnostics must not crash startup
                self._component_errors["statistics"] = _safe_error_code(exc)

        # Core already exposes durable backlog and integrity counters. Read
        # those first and avoid an unconditional full maintenance scan on a
        # clean cold start. The scan serializes Core IPC and used to make the
        # first recall time out even though authenticated /ping was available.
        refresh_statistics()
        statistics = self._object_facet_statistics
        maintenance_indicators = (
            "operational_backlog",
            "background_backlog",
            "embedding_backlog",
            "integrity_finding_count",
            "blocking_integrity_finding_count",
            "missing_card_embeddings",
            "missing_facet_embeddings",
        )
        if (
            statistics is not None
            and not bool(statistics.get("legacy_digest_upgrade_required", False))
            and all(
                not _is_positive_int(statistics.get(name))
                for name in maintenance_indicators
            )
        ):
            self._control_maintenance = {
                "status": "not_required",
                "ready": True,
            }
            self._component_errors.pop("control", None)
            self._component_errors.pop("statistics", None)
            self._object_facet_bootstrap_pending = False
            return

        if not callable(run_control):
            self._component_errors["control"] = "unsupported"
        else:
            try:
                embedding_profiles = self._embedding_profiles_by_memory_space()
                result = run_control(
                    RunControlMaintenanceCommand(
                        f"local-control:{os.getpid()}:{uuid.uuid4()}",
                        embedding_profiles=embedding_profiles,
                    )
                )
                self._control_maintenance = {
                    "status": getattr(result, "status", "completed"),
                    "ready": True,
                }
            except Exception as exc:  # noqa: BLE001 - readiness remains observable
                self._control_maintenance = {
                    "status": "failed",
                    "ready": False,
                    "error_code": _safe_error_code(exc),
                }
                self._component_errors["control"] = _safe_error_code(exc)

        refresh_statistics()

        # A control pass can observe a missing facet vector before the
        # lifecycle scheduler has drained the already-queued embedding task.
        # Once all embedding and contour backlogs are empty, one bounded
        # reconciliation pass closes that stale projection without hiding a
        # still-live finding.
        statistics = self._object_facet_statistics or {}
        if (
            callable(run_control)
            and all(
                statistics.get(name, 0) == 0
                for name in (
                    "operational_backlog",
                    "background_backlog",
                    "embedding_backlog",
                    "missing_card_embeddings",
                    "missing_facet_embeddings",
                )
            )
            and statistics.get("integrity_finding_count", 0) > 0
        ):
            try:
                embedding_profiles = self._embedding_profiles_by_memory_space()
                result = run_control(
                    RunControlMaintenanceCommand(
                        f"local-control-reconcile:{os.getpid()}:{uuid.uuid4()}",
                        embedding_profiles=embedding_profiles,
                    )
                )
                self._control_maintenance = {
                    "status": getattr(result, "status", "completed"),
                    "ready": True,
                }
                refresh_statistics()
            except Exception as exc:  # noqa: BLE001 - readiness remains observable
                self._control_maintenance = {
                    "status": "failed",
                    "ready": False,
                    "error_code": _safe_error_code(exc),
                }
                self._component_errors["control"] = _safe_error_code(exc)

        statistics = self._object_facet_statistics or {}
        self._object_facet_bootstrap_pending = bool(
            statistics.get("object_count") == 0
            and statistics.get("active_value_count") == 0
            and statistics.get("superseded_value_count") == 0
            and any(
                _is_positive_int(statistics.get(name))
                for name in (
                    "missing_card_embeddings",
                    "missing_facet_embeddings",
                    "operational_backlog",
                    "background_backlog",
                    "embedding_backlog",
                )
            )
        )

    def run_control_maintenance(self) -> dict[str, object]:
        """Run a fresh control pass and return content-free maintenance evidence.

        Startup performs the same pass before workers begin processing model
        tasks.  Operators and lifecycle certification also need an explicit
        post-drain pass: embedding jobs may resolve a finding that was valid at
        startup, and the cached health projection must then be refreshed.
        """

        self._refresh_object_facet_health()
        maintenance = dict(self._control_maintenance or {})
        statistics = dict(self._object_facet_statistics or {})
        return {
            "status": maintenance.get("status", "unavailable"),
            "ready": bool(maintenance.get("ready", False)),
            "statistics": {
                name: statistics.get(name)
                for name in (
                    "object_count",
                    "active_value_count",
                    "superseded_value_count",
                    "operational_backlog",
                    "background_backlog",
                    "embedding_backlog",
                    "integrity_finding_count",
                    "blocking_integrity_finding_count",
                    "missing_card_embeddings",
                    "missing_facet_embeddings",
                    "legacy_digest_upgrade_required",
                )
                if name in statistics
            },
        }

    def retry_failed_round_semantic(
        self,
        *,
        limit: int = 100,
        error_code: str | None = None,
        memory_space_id: str | None = None,
    ) -> dict[str, object]:
        """Explicitly requeue size rejects and pre-materialization failures."""

        gateway = self.core_gateway
        if gateway is None:
            raise RuntimeError("Core gateway is unavailable")
        connection = self.connection_factory(self.database_path)
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows = connection.execute(
                """
                SELECT command_id FROM core_commands
                WHERE status = 'rejected'
                  AND LOWER(COALESCE(last_error_detail, ''))
                      LIKE '%normalized%budget%'
                  AND (? IS NULL OR last_error_code = ?)
                  AND (? IS NULL OR memory_space_id = ?)
                ORDER BY created_at, command_id LIMIT ?
                """,
                (
                    error_code,
                    error_code,
                    memory_space_id,
                    memory_space_id,
                    limit,
                ),
            ).fetchall()
            command_ids = [str(row[0]) for row in rows]
            for command_id in command_ids:
                connection.execute(
                    """
                    UPDATE core_commands
                    SET status = 'pending', attempts = 0, available_at = ?,
                        lease_expires_at = NULL, claimed_by = NULL,
                        completed_at = NULL, result_json = NULL,
                        last_error_code = NULL, last_error_detail = NULL
                    WHERE command_id = ? AND status = 'rejected'
                    """,
                    (now, command_id),
                )
                connection.execute(
                    """
                    UPDATE raw_round_core_deliveries
                    SET transport_status = 'queued', last_error_code = NULL,
                        updated_at = ? WHERE command_id = ?
                    """,
                    (now, command_id),
                )
            connection.commit()
        finally:
            connection.close()
        result = gateway.run_control_maintenance(
            RunControlMaintenanceCommand(
                f"local-replay:{os.getpid()}:{uuid.uuid4()}",
                embedding_profiles=self._embedding_profiles_by_memory_space(),
                retry_failed_round_semantic=True,
                retry_limit=limit,
                retry_error_code=error_code,
                retry_memory_space_id=memory_space_id,
            )
        )
        return {
            "status": result.status,
            "error_code": error_code,
            "memory_space_id": memory_space_id,
            "requeued_normalization_commands": len(command_ids),
            "retried_failed_round_semantic": result.retried_failed_round_semantic,
        }

    def _recover_verified_provider_capability_failures(self) -> None:
        """Requeue one stalled round after its provider became usable.

        Recovery is intentionally serialized.  A completed round can change
        the memory snapshot used by KR, so bulk requeueing independent rounds
        here would manufacture avoidable stale-snapshot conflicts.
        """

        gateway = self.core_gateway
        if gateway is None or not self._core_ready:
            return
        connection = self.connection_factory(self.database_path)
        try:
            store = InferenceProfileStore(connection)
            memory_space_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
                ).fetchall()
            ]
            for memory_space_id in memory_space_ids:
                try:
                    profile_id = store.get_slot(memory_space_id, "operational")
                    profile = store.get(profile_id) if profile_id is not None else None
                    capabilities = (
                        store.get_capabilities_for_profile(profile, fresh_only=True)
                        if profile is not None and profile.enabled
                        else None
                    )
                    if capabilities is None or not capabilities.supports(
                        STRICT_JSON_SCHEMA_MODE
                    ):
                        continue
                    gateway.run_control_maintenance(
                        RunControlMaintenanceCommand(
                            f"startup-recovery:{os.getpid()}:{uuid.uuid4()}",
                            embedding_profiles=self._embedding_profiles_by_memory_space(),
                            retry_failed_round_semantic=True,
                            retry_limit=1,
                            retry_memory_space_id=memory_space_id,
                            retry_only=True,
                            automatic_recovery=True,
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - isolate memory spaces
                    logger.warning(
                        "automatic provider capability recovery failed",
                        extra={
                            "memory_space_id": memory_space_id,
                            "error_code": _safe_error_code(exc),
                        },
                    )
        finally:
            connection.close()

    def _start_workers(self) -> None:
        for name in self._WORKER_ORDER:
            config_worker = getattr(self.config.workers, name)
            if not config_worker.enabled:
                continue
            if name in {"core_commands", "core_model_tasks"} and not self._core_ready:
                self._component_errors[name] = "core_unavailable"
                continue
            try:
                worker = self._build_worker(name)
                handle = self._start_worker_loop(name, config_worker, worker)
                self._workers[name] = handle
            except Exception as exc:  # noqa: BLE001 - one worker cannot kill capture
                self._component_errors[name] = _safe_error_code(exc)
                logger.warning(
                    "worker startup failed",
                    extra={"worker": name, "error_code": _safe_error_code(exc)},
                )

    def _build_worker(self, name: str) -> object:
        factory = self.worker_factories.get(name)
        if factory is not None:
            return factory(self)
        if name == "retention":
            return RawRoundRetentionWorker(self.database_path)
        if self.core_gateway is None:
            raise RuntimeError("Core gateway is unavailable")
        if name == "core_commands":
            return CoreCommandWorker(
                database_path=self.database_path,
                gateway=self.core_gateway,
                worker_id=f"core-command:{os.getpid()}",
                max_attempts=self.config.worker_max_attempts,
                retry_delay_seconds=self.config.worker_retry_delay_seconds,
                lease_seconds=self.config.worker_lease_seconds,
                state=WorkerState(name),
                embedding_profile_metadata_factory=self.embedding_profile_metadata,
            )
        if name == "core_model_tasks":
            secret_store = SecretStore(
                self.paths.resolve_home_path(self.config.inference_secrets_path)
            )
            profile_resolver = DatabaseBackedProfileResolver(self.database_path)
            return CoreExecutionTaskWorker(
                database_path=self.database_path,
                gateway=self.core_gateway,
                executor=CoreTaskExecutor(
                    json_provider=StructuredJsonProvider(
                        profile_resolver=profile_resolver,
                        secret_store=secret_store,
                        capability_store=DatabaseBackedCapabilityStore(
                            str(self.database_path)
                        ),
                    ),
                    embedding_provider=EmbeddingProvider(
                        vectorizer_factory=_build_runtime_vectorizer_factory(
                            self.config
                        ),
                        cache=PersistentEmbeddingCache(self.database_path),
                    ),
                    profile_resolver=profile_resolver,
                    generate_json_timeout_seconds=300,
                    embed_texts_timeout_seconds=300,
                ),
                worker_id="local-execution-tasks",
                lease_seconds=max(
                    int(self.config.worker_lease_seconds),
                    MIN_CORE_MODEL_TASK_LEASE_SECONDS,
                ),
            )
        raise ValueError(f"unknown Local worker: {name}")

    def _start_worker_loop(
        self,
        name: str,
        config_worker: WorkerConfig,
        worker: object,
    ) -> _RuntimeWorkerHandle:
        state = getattr(worker, "state", None)
        if not isinstance(state, WorkerState):
            state = WorkerState(name)
        observer = lambda result, observed_state: self._observe_worker_result(
            name, result, observed_state
        )
        create_loop = getattr(worker, "create_loop", None)
        if callable(create_loop):
            loop = create_loop(
                poll_interval_seconds=config_worker.interval_seconds,
                max_backoff_seconds=config_worker.max_backoff_seconds,
            )
            # A5 owns the observer hook; the A5 worker implementations that
            # predate B3 expose it on the constructed loop rather than their
            # create_loop signature.
            loop._result_observer = observer
        else:
            loop = GuardedWorkerLoop(
                worker,  # type: ignore[arg-type]
                state=state,
                name=name,
                poll_interval_seconds=config_worker.interval_seconds,
                max_backoff_seconds=config_worker.max_backoff_seconds,
                close_on_stop=callable(getattr(worker, "close", None)),
                result_observer=observer,
            )
        if not isinstance(loop, GuardedWorkerLoop):
            raise TypeError("worker factory returned an unsupported loop")
        loop.start()
        return _RuntimeWorkerHandle(name, config_worker, worker, loop, state)

    def _observe_worker_result(
        self,
        name: str,
        result: object | None,
        state: WorkerState,
    ) -> None:
        """Keep result observation content-free at the worker boundary."""

        del result, state
        if name != "core_model_tasks" or self._stop_requested:
            return
        now = time.monotonic()
        if now - self._last_automatic_recovery_at < 2.0:
            return
        self._last_automatic_recovery_at = now
        try:
            self._recover_verified_provider_capability_failures()
        except Exception as exc:  # noqa: BLE001 - recovery must not stop workers
            logger.warning(
                "automatic stalled-round recovery failed",
                extra={"error_code": _safe_error_code(exc)},
            )

    def _build_context_gateway(self) -> None:
        if self.core_gateway is None:
            self._context_gateway = None
            return
        self._context_gateway = self.core_gateway

    def _configured_workers(self) -> tuple[tuple[str, WorkerConfig], ...]:
        return tuple(
            (name, getattr(self.config.workers, name)) for name in self._WORKER_ORDER
        )

    def _profile_slots_report(self) -> dict[str, object]:
        """Check all four enabled profile slots without legacy fallbacks."""

        slots = tuple(slot.value for slot in ProfileSlot)
        missing: dict[str, list[str]] = {}
        connection = self.connection_factory(self.database_path)
        try:
            migrations.apply_migrations(connection)
            connection.row_factory = sqlite3.Row
            from ledgermind_local.inference.profile_store import InferenceProfileStore

            store = InferenceProfileStore(connection)
            rows = connection.execute(
                "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
            ).fetchall()
            for row in rows:
                memory_space_id = str(row["memory_space_id"])
                bindings = store.list_slots(memory_space_id)
                for slot in slots:
                    profile_id = bindings.get(slot)
                    profile = store.get(profile_id) if profile_id is not None else None
                    if profile_id is None or profile is None or not profile.enabled:
                        missing.setdefault(memory_space_id, []).append(slot)
        except Exception as exc:  # noqa: BLE001 - readiness must expose the blocker
            return {
                "ready": False,
                "ok": False,
                "missing_profile_slots_by_memory_space": {},
                "error_code": _safe_error_code(exc),
            }
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        return {
            "ready": not missing,
            "ok": not missing,
            "missing_profile_slots_by_memory_space": missing,
        }

    def _isolation_report(self) -> dict[str, object]:
        gateway = self.core_gateway
        if gateway is None:
            return {"ready": False, "ok": False, "missing": (), "capabilities": {}}
        capabilities = getattr(gateway, "isolation_capabilities", None)
        if capabilities is None:
            return {"ready": True, "ok": True, "missing": (), "capabilities": {}}
        as_dict = getattr(capabilities, "as_dict", None)
        payload = as_dict() if callable(as_dict) else {}
        missing = build_core_isolation_requirements(
            self.config.core_security,
            verify_core_signature=self.config.verify_core_signature,
        ).missing(capabilities)
        return {
            "ready": not missing,
            "ok": not missing,
            "missing": missing,
            "capabilities": payload,
        }

    def _cleanup_after_failed_start(self) -> None:
        self.request_stop()
        timed_out_workers: list[str] = []
        for name, handle in reversed(tuple(self._workers.items())):
            try:
                result = handle.loop.shutdown(handle.config.shutdown_timeout_seconds)
                stopped = bool(getattr(result, "stopped", False))
            except Exception as exc:  # noqa: BLE001
                stopped = False
                self._component_errors[name] = _safe_error_code(exc)
                handle.state.mark_shutdown_timed_out()
            if not stopped:
                timed_out_workers.append(name)
                self._component_errors[name] = "shutdown_timeout"
        if timed_out_workers:
            self._shutdown_incomplete = True
            self._shutdown_timed_out_workers = list(reversed(timed_out_workers))
            self._started = False
            return
        self._workers.clear()
        gateway = self.core_gateway
        self.core_gateway = None
        self._backup_service = None
        self._restore_service = None
        if gateway is not None:
            close = getattr(gateway, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.debug("failed to close Core gateway", exc_info=True)
        if self._pid_owned:
            try:
                self.pid_remover(self.paths.service_pid_file)
            finally:
                self._pid_owned = False
        if self._service_lock is not None:
            self._release_service_lock()
            self._service_lock = None
        self._started = False
        self._initialization_complete = False


def _safe_error_code(error: BaseException) -> str:
    code = getattr(error, "reason_code", None)
    if not isinstance(code, str):
        code = getattr(error, "code", None)
    if isinstance(code, str) and code.strip():
        if code == "profile_missing":
            return "provider_profile_invalid"
        return code
    if isinstance(error, (CoreSupervisorError, ConnectionError, TimeoutError)):
        return "core_unreachable"
    if isinstance(error, MigrationError):
        return "local_db_migration_incomplete"
    if "migration" in str(error).casefold():
        return "local_db_migration_incomplete"
    return type(error).__name__ or "RuntimeError"


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _write_runtime_pid(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = pid_file.with_name(f".{pid_file.name}.{pid}.tmp")
    try:
        temporary.write_text(f"{pid}\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, pid_file)
        os.chmod(pid_file, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_runtime_pid(pid_file: Path) -> None:
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        if int(content) != os.getpid():
            return
    except (FileNotFoundError, ValueError, OSError):
        return
    pid_file.unlink(missing_ok=True)


def bootstrap_local_service(
    *,
    home: str | Path = "~/.ledgermind/local",
    config: LocalConfig | None = None,
) -> tuple[ServicePaths, LocalConfig]:
    """Prepare Local filesystem and return resolved runtime objects."""

    paths = ServicePaths(home=home)
    cfg = config or LocalConfig(config_version=CURRENT_CONFIG_VERSION)
    if cfg.config_version < CURRENT_CONFIG_VERSION:
        cfg = cfg.model_copy(update={"config_version": CURRENT_CONFIG_VERSION})
    paths.home.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths.logs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    database_path = paths.resolve_rounds_database_path(cfg.rounds_database_path)
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = open_sqlite_connection(database_path)
    connection.close()
    return paths, cfg


def _atomic_write_text(path: Path, data: str, *, mode: int) -> None:
    """Write text atomically with explicit permissions."""

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
        ) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
            os.chmod(tmp_path, mode)
            tmp_path.replace(path)
            os.chmod(path, mode)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def initialize_local_layout(
    *,
    home: str | Path = "~/.ledgermind/local",
    force: bool = False,
    rotate_token: bool = False,
    config: LocalConfig | None = None,
) -> tuple[ServicePaths, LocalConfig, str]:
    """Initialize Local directories, config and API token."""

    preloaded_config = config
    if preloaded_config is None and not force:
        candidate = ServicePaths(home=home).config_file
        if candidate.exists():
            preloaded_config = LocalConfig.from_file(candidate)
    paths, cfg = bootstrap_local_service(home=home, config=preloaded_config)

    config_path = paths.config_file
    if force or not config_path.exists():
        cfg = config or LocalConfig(config_version=CURRENT_CONFIG_VERSION)
        if cfg.config_version < CURRENT_CONFIG_VERSION:
            cfg = cfg.model_copy(update={"config_version": CURRENT_CONFIG_VERSION})
        _atomic_write_text(config_path, cfg.to_json(), mode=0o600)
    elif config is None:
        cfg = LocalConfig.from_file(config_path)
        # Persist the canonical schema after loading any legacy config so a
        # later startup never reintroduces the removed isolation flag.
        _atomic_write_text(config_path, cfg.to_json(), mode=0o600)
    else:
        cfg = config

    database_path = paths.resolve_rounds_database_path(cfg.rounds_database_path)
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = open_sqlite_connection(database_path)
    connection.close()

    if not paths.token_file.exists() or (force and rotate_token):
        token = _generate_token()
        _atomic_write_text(paths.token_file, token, mode=0o600)
        return paths, cfg, token

    if rotate_token:
        token = _generate_token()
        _atomic_write_text(paths.token_file, token, mode=0o600)
        return paths, cfg, token

    existing_token = paths.token_file.read_text(encoding="utf-8")
    normalized_token = existing_token.strip()
    if not normalized_token:
        raise ValueError("Local API token file must contain a non-empty token")
    if normalized_token != existing_token:
        _atomic_write_text(paths.token_file, normalized_token, mode=0o600)
    return paths, cfg, normalized_token
