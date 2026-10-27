"""B3 runtime wiring regressions."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

from ledgermind_local import bootstrap, cli
from ledgermind_local.bootstrap import LocalRuntime
from ledgermind_local.config import CoreSecurityConfig, LocalConfig
from ledgermind_local.core_gateway.contracts import CoreHealth, ObjectFacetStatistics
from ledgermind_local.core_gateway.security_policy import (
    build_core_isolation_requirements,
)
from ledgermind_local.core_gateway.supervisor import CoreSupervisorBusy
from ledgermind_local.paths import ServicePaths


class _Gateway:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def require_capabilities(self, *capabilities: str) -> None:
        self.events.append("capabilities:" + ",".join(capabilities))

    def health(self) -> CoreHealth:
        self.events.append("health")
        return CoreHealth(healthy=True, backend="fake")

    def close(self) -> None:
        self.events.append("core-close")


class _ActivityGateway(_Gateway):
    def __init__(
        self,
        events: list[str],
        *,
        operational: int = 0,
        background: int = 0,
        embedding: int = 0,
    ) -> None:
        super().__init__(events)
        self.operational = operational
        self.background = background
        self.embedding = embedding

    def get_object_facet_statistics(self, request_id: str) -> ObjectFacetStatistics:
        del request_id
        return ObjectFacetStatistics(
            object_count=0,
            active_value_count=0,
            superseded_value_count=0,
            operational_backlog=self.operational,
            background_backlog=self.background,
            embedding_backlog=self.embedding,
            integrity_finding_count=0,
            blocking_integrity_finding_count=0,
        )


class _BusyAfterSnapshotGateway(_ActivityGateway):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events, operational=2, background=1, embedding=3)
        self.calls = 0

    def try_get_object_facet_statistics(
        self, request_id: str
    ) -> ObjectFacetStatistics:
        self.calls += 1
        if self.calls > 1:
            raise CoreSupervisorBusy("Core IPC channel is busy")
        return self.get_object_facet_statistics(request_id)


class _BlockingWorker:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def process_once(self) -> None:
        self.entered.set()
        self.release.wait(timeout=5)

    def request_stop(self) -> None:
        return None


class _DegradedWorker:
    def __init__(self) -> None:
        self.observed = threading.Event()

    def process_once(self) -> SimpleNamespace:
        self.observed.set()
        return SimpleNamespace(degraded=True)

    def request_stop(self) -> None:
        return None


def _runtime(
    tmp_path: Path,
    *,
    config: LocalConfig,
    gateway: object | None = None,
    worker_factories: dict[str, object] | None = None,
) -> LocalRuntime:
    paths = ServicePaths(tmp_path / "service")
    events: list[str] = []
    selected_gateway = gateway or _Gateway(events)
    return LocalRuntime(
        paths=paths,
        config=config,
        api_token="test-token",
        database_path=paths.resolve_rounds_database_path(config.rounds_database_path),
        core_gateway_factory=lambda: selected_gateway,
        worker_factories=worker_factories,  # type: ignore[arg-type]
    )


def _minimal_config(**workers: object) -> LocalConfig:
    defaults = {
        "retention": {"enabled": False},
        "core_commands": {"enabled": False},
        "core_model_tasks": {"enabled": False},
    }
    defaults.update(workers)
    return LocalConfig(config_version=1, semantic_language="ru", workers=defaults)


def test_legacy_security_switch_migrates_to_secure_config_without_serializing_legacy_key() -> None:
    config = LocalConfig.from_dict(
        {
            "config_version": 1,
            "semantic_language": "ru",
            "require_core_network_isolation": True,
        }
    )

    assert config.config_version == 2
    assert config.core_security.profile == "secure"
    assert config.core_security.require_network_isolation is True
    payload = json.loads(config.to_json())
    assert "require_core_network_isolation" not in payload
    assert "require_core_network_isolation" not in config.model_dump()

    migrated_false = LocalConfig.from_dict(
        {
            "config_version": 1,
            "semantic_language": "ru",
            "require_core_network_isolation": False,
        }
    )
    assert migrated_false.config_version == 2
    assert migrated_false.core_security.profile == "secure"
    assert migrated_false.core_security.require_signature is True


def test_persisted_legacy_config_is_rewritten_to_current_schema(tmp_path: Path) -> None:
    paths = ServicePaths(tmp_path / "service")
    paths.home.mkdir(parents=True)
    paths.config_file.write_text(
        json.dumps(
            {
                "config_version": 1,
                "semantic_language": "ru",
                "require_core_network_isolation": False,
            }
        ),
        encoding="utf-8",
    )

    _paths, config, _token = bootstrap.initialize_local_layout(home=paths.home)

    persisted = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert config.config_version == 2
    assert persisted["config_version"] == 2
    assert "require_core_network_isolation" not in persisted


def test_runtime_bootstrap_and_doctor_share_one_policy_translation() -> None:
    assert bootstrap.build_core_isolation_requirements is build_core_isolation_requirements
    assert not hasattr(bootstrap, "_core_isolation_requirements")

    permissive = CoreSecurityConfig(profile="permissive", require_network_isolation=True)
    requirements = build_core_isolation_requirements(
        permissive,
        verify_core_signature=False,
    )
    assert requirements.require_network_isolation is True


def test_runtime_does_not_close_core_when_worker_shutdown_times_out(tmp_path: Path) -> None:
    events: list[str] = []
    gateway = _Gateway(events)
    worker = _BlockingWorker()
    config = _minimal_config(
        retention={
            "enabled": True,
            "interval_seconds": 0,
            "shutdown_timeout_seconds": 0.01,
        }
    )
    runtime = _runtime(
        tmp_path,
        config=config,
        gateway=gateway,
        worker_factories={"retention": lambda _runtime: worker},
    )

    runtime.start()
    assert worker.entered.wait(timeout=1)
    runtime.stop()

    assert "core-close" not in events
    report = runtime.health_report()
    assert report["shutdown"]["incomplete"] is True
    assert report["shutdown"]["timed_out_workers"] == ["retention"]
    assert report["components"]["workers"]["retention"]["state"]["shutdown_timed_out"] is True

    worker.release.set()
    runtime.stop()
    assert "core-close" in events


def test_runtime_health_exposes_worker_degradation_without_result_payload(tmp_path: Path) -> None:
    worker = _DegradedWorker()
    config = _minimal_config(retention={"enabled": True, "interval_seconds": 0})
    runtime = _runtime(
        tmp_path,
        config=config,
        worker_factories={"retention": lambda _runtime: worker},
    )

    runtime.start()
    try:
        assert worker.observed.wait(timeout=1)
        report = runtime.health_report()
        worker_report = report["components"]["workers"]["retention"]
        assert worker_report["ready"] is False
        assert report["full_ready"] is False
        assert report["degraded"] is True
        assert worker_report["state"]["degraded"] is True
        assert worker_report["observability"] == {}
        assert "provider_unavailable" not in json.dumps(worker_report)
        assert "model_input" not in json.dumps(report)
    finally:
        runtime.stop()


def test_runtime_activity_combines_local_handoff_and_core_backlog(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    gateway = _ActivityGateway(
        events,
        operational=2,
        background=1,
        embedding=3,
    )
    runtime = _runtime(tmp_path, config=_minimal_config(), gateway=gateway)
    runtime.start()
    try:
        with sqlite3.connect(runtime.database_path) as connection:
            base = (
                "ingest_raw_round",
                "space-1",
                "{}",
                "sha256:" + "0" * 64,
                "2026-08-31T00:00:00Z",
            )
            connection.execute(
                """
                INSERT INTO core_commands (
                    command_id, command_type, memory_space_id, idempotency_key,
                    payload_json, payload_digest, status, available_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    "pending-1",
                    base[0],
                    base[1],
                    "pending-key",
                    base[2],
                    base[3],
                    base[4],
                    base[4],
                ),
            )
            connection.execute(
                """
                INSERT INTO core_commands (
                    command_id, command_type, memory_space_id, idempotency_key,
                    payload_json, payload_digest, status, available_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'delivering', ?, ?)
                """,
                (
                    "leased-1",
                    base[0],
                    base[1],
                    "leased-key",
                    base[2],
                    base[3],
                    base[4],
                    base[4],
                ),
            )

        report = runtime.activity_report()

        assert report["known"] is True
        assert report["quiescent"] is False
        assert report["leased_tasks"] == 1
        assert report["pending_writes"] == 7
        assert report["local"] == {
            "delivering_commands": 1,
            "pending_commands": 1,
        }
        assert report["core"] == {
            "operational_backlog": 2,
            "background_backlog": 1,
            "embedding_backlog": 3,
        }
        assert "payload" not in json.dumps(report)
    finally:
        runtime.stop()


def test_runtime_activity_returns_stale_cached_counts_when_core_is_busy(
    tmp_path: Path,
) -> None:
    gateway = _BusyAfterSnapshotGateway([])
    runtime = _runtime(
        tmp_path,
        config=_minimal_config(),
        gateway=gateway,
    )
    runtime.start()
    try:
        fresh = runtime.activity_report()
        stale = runtime.activity_report()

        assert fresh["known"] is True
        assert fresh["stale"] is False
        assert fresh["pending_writes"] == 6
        assert isinstance(fresh["observed_at"], str)

        assert stale["known"] is False
        assert stale["stale"] is True
        assert stale["quiescent"] is False
        assert stale["error_code"] == "core_activity_busy"
        assert stale["pending_writes"] == 6
        assert stale["core"] == fresh["core"]
        assert stale["observed_at"] == fresh["observed_at"]
    finally:
        runtime.stop()


def test_runtime_builds_generic_execution_worker_for_core_model_tasks(
    tmp_path: Path, monkeypatch
) -> None:
    created: list[dict[str, object]] = []

    class _GenericExecutionWorker:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

        def process_once(self) -> int:
            return 0

        def close(self) -> None:
            return None

    monkeypatch.setattr(bootstrap, "CoreExecutionTaskWorker", _GenericExecutionWorker)
    runtime = _runtime(
        tmp_path,
        config=_minimal_config(core_model_tasks={"enabled": True, "interval_seconds": 0}),
    )

    runtime.start()
    try:
        assert len(created) == 1
        assert created[0]["worker_id"] == "local-execution-tasks"
        executor = created[0]["executor"]
        assert (
            type(executor._embedding_provider).__module__
            == "ledgermind_inference.embedding_provider"
        )
    finally:
        runtime.stop()


def test_contract_migration_runs_before_any_worker(tmp_path: Path, monkeypatch) -> None:
    events: list[str] = []

    def fake_contract_migration(**kwargs: object) -> None:
        del kwargs
        events.append("contract-migration")

    class _Worker:
        def process_once(self) -> None:
            events.append("worker")

        def close(self) -> None:
            return None

    monkeypatch.setattr(bootstrap, "migrate_contract_payloads", fake_contract_migration)
    runtime = _runtime(
        tmp_path,
        config=_minimal_config(retention={"enabled": True, "interval_seconds": 0}),
        worker_factories={"retention": lambda _runtime: _Worker()},
    )

    runtime.start()
    try:
        assert events.index("contract-migration") < events.index("worker")
    finally:
        runtime.stop()


def test_runtime_surfaces_pending_restore_journal_and_blocks_full_ready(tmp_path: Path) -> None:
    config = _minimal_config()
    runtime = _runtime(tmp_path, config=config)
    journal = runtime.paths.home / "restore-journal.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"state": "pending"}), encoding="utf-8")
    runtime.core_gateway_factory = lambda: (_ for _ in ()).throw(RuntimeError("Core unavailable"))

    runtime.start()
    try:
        report = runtime.health_report()
        assert report["capture_ready"] is True
        assert report["full_ready"] is False
        assert report["components"]["restore"]["ready"] is False
        assert report["components"]["restore"]["error_code"] in {
            "restore_pending",
            "restore_journal_corrupt",
        }
    finally:
        runtime.stop()


def test_backup_restore_uses_coordinated_saga_and_rotates_token(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "service"
    assert cli.main(
        ["--home", str(home), "init", "--semantic-language", "ru"]
    ) == 0
    old_token = (home / "server.token").read_text(encoding="utf-8")
    events: list[str] = []

    class _Prepared:
        def cleanup(self) -> None:
            events.append("cleanup")

    class _Saga:
        def __init__(self, **kwargs: object) -> None:
            events.append("saga-init")
            assert "core_backup_service" in kwargs
            assert callable(kwargs["stop_core"])
            assert callable(kwargs["start_core"])
            assert callable(kwargs["health_check"])

        def prepare_restore(self, source: Path) -> _Prepared:
            events.append(f"prepare:{source.name}")
            return _Prepared()

        def apply_restore(self, prepared: _Prepared) -> SimpleNamespace:
            del prepared
            events.append("apply")
            return SimpleNamespace(state="committed")

    class _GatewayForRestore:
        def start(self) -> None:
            events.append("start")

        def health(self) -> CoreHealth:
            return CoreHealth(healthy=True, backend="fake")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(cli, "CoordinatedRestoreService", _Saga)
    monkeypatch.setattr(
        cli,
        "_build_core_backup_service",
        lambda **_kwargs: (_GatewayForRestore(), object()),
    )
    source = home / "backup.zip"
    source.write_bytes(b"opaque-test-archive")

    assert (
        cli.main(
            ["--home", str(home), "backup", "restore", "--source", str(source)]
        )
        == 0
    )

    new_token = (home / "server.token").read_text(encoding="utf-8")
    assert new_token != old_token
    assert events[:3] == ["saga-init", "prepare:backup.zip", "apply"]
    assert "cleanup" in events
    assert "close" in events


def test_permissive_runtime_emits_warning_and_reports_capabilities_honestly(
    tmp_path: Path, caplog
) -> None:
    config = _minimal_config()
    config = config.model_copy(update={"core_security": CoreSecurityConfig(profile="permissive")})
    runtime = _runtime(tmp_path, config=config)

    with caplog.at_level("WARNING", logger="ledgermind_local.bootstrap"):
        runtime.start()
    try:
        assert any("permissive" in record.message for record in caplog.records)
        assert runtime.health_report()["components"]["isolation"]["ready"] is True
    finally:
        runtime.stop()
