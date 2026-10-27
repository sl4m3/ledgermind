"""Small deterministic Core IPC process used by Local acceptance tests."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path


def _configure_python_paths() -> None:
    paths = [
        sys.argv[index + 1]
        for index, argument in enumerate(sys.argv[:-1])
        if argument == "--python-path" and index + 1 < len(sys.argv)
    ]
    for path in reversed(paths):
        sys.path.insert(0, path)


_configure_python_paths()

from ledgermind_protocol.core_ipc import (
    CoreError,
    CoreRequestEnvelope,
    CoreResponseEnvelope,
)

from ledgermind_local.core_gateway.compatibility import (
    SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
    SUPPORTED_PROTOCOL_MAX,
)

_CURRENT_OPERATIONS = {
    "handshake",
    "health",
    "shutdown",
    "ingest_raw_round",
    "poll_execution_tasks",
    "submit_execution_result",
    "fail_execution_task",
    "retrieve_context",
    "record_retrieval_outcome",
    "run_control_maintenance",
    "get_object_facet_statistics",
    "delete_memory_space",
    "create_backup",
    "validate_backup",
    "prepare_restore",
    "begin_restore",
    "commit_restore",
    "rollback_restore",
}
_CURRENT_CAPABILITIES = {
    "object_facet_memory",
    "operational_pipeline",
    "strict_candidate_binding",
    "generic_execution_tasks",
    "raw_round_ingest",
    "context_retrieval",
    "context_provenance",
    "stable_sha256_digests",
    "object_resolution",
    "explainable_context",
    "control_contour",
    "core_owned_backup",
    "coordinated_restore",
}


def _read_frame() -> bytes:
    header = sys.stdin.buffer.read(4)
    if len(header) != 4:
        raise EOFError
    length = int.from_bytes(header, "big")
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length:
        raise EOFError
    return payload


def _write(response: CoreResponseEnvelope) -> None:
    payload = response.to_json().encode("utf-8")
    sys.stdout.buffer.write(len(payload).to_bytes(4, "big") + payload)
    sys.stdout.buffer.flush()


def _write_raw(payload: bytes) -> None:
    sys.stdout.buffer.write(len(payload).to_bytes(4, "big") + payload)
    sys.stdout.buffer.flush()


def _argument_values(name: str) -> set[str]:
    values: set[str] = set()
    for index, argument in enumerate(sys.argv[:-1]):
        if argument == name:
            values.add(sys.argv[index + 1])
    return values


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _error(request_id: str, code: str, message: str) -> None:
    _write(
        CoreResponseEnvelope.from_error(
            request_id,
            CoreError(
                code=code,
                message=message,
                error_id="fake-error-1",
                retryable=False,
            ),
        )
    )


def _exchange_file(core_data_dir: Path, relative_path: str) -> Path:
    candidate = (core_data_dir / relative_path).resolve()
    root = core_data_dir.resolve()
    candidate.relative_to(root)
    return candidate


def main() -> int:
    crash_once_file: Path | None = None
    delay_seconds = 0.0
    stderr_line: str | None = None
    mismatched_health_id = "--mismatched-health-id" in sys.argv
    malformed_health_response = "--malformed-health-response" in sys.argv
    missing_capabilities = _argument_values("--missing-capability")
    missing_operations = _argument_values("--missing-operation")
    schema_version = SUPPORTED_KNOWLEDGE_SCHEMA_MAX
    if "--schema-version" in sys.argv:
        schema_version = int(sys.argv[sys.argv.index("--schema-version") + 1])
    core_data_dir = Path(os.environ.get("LEDGERMIND_CORE_DATA_DIR", "."))
    if "--crash-once-file" in sys.argv:
        marker_index = sys.argv.index("--crash-once-file") + 1
        crash_once_file = Path(sys.argv[marker_index])
    if "--delay-seconds" in sys.argv:
        delay_index = sys.argv.index("--delay-seconds") + 1
        delay_seconds = float(sys.argv[delay_index])
    if "--stderr-line" in sys.argv:
        stderr_index = sys.argv.index("--stderr-line") + 1
        stderr_line = sys.argv[stderr_index]
    if stderr_line is not None:
        print(stderr_line, file=sys.stderr, flush=True)

    while True:
        try:
            raw = _read_frame()
        except EOFError:
            return 0
        request = CoreRequestEnvelope.from_json(raw.decode("utf-8"))
        if request.operation == "handshake":
            operations = sorted(_CURRENT_OPERATIONS - missing_operations)
            capabilities = {
                capability: capability not in missing_capabilities
                for capability in _CURRENT_CAPABILITIES
            }
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "protocol_version": SUPPORTED_PROTOCOL_MAX,
                        "core_version": "fake-core-1",
                        "knowledge_schema_version": schema_version,
                        "supported_operations": operations,
                        "capabilities": capabilities,
                    },
                )
            )
        elif request.operation in missing_operations:
            _error(request.request_id, "INVALID_REQUEST", "operation is unavailable")
        elif request.operation == "health":
            if delay_seconds:
                time.sleep(delay_seconds)
            if crash_once_file is not None and not crash_once_file.exists():
                crash_once_file.parent.mkdir(parents=True, exist_ok=True)
                crash_once_file.touch()
                return 17
            if malformed_health_response:
                _write_raw(b"{not-json")
                return 18
            response_request_id = (
                f"{request.request_id}-wrong"
                if mismatched_health_id
                else request.request_id
            )
            _write(
                CoreResponseEnvelope.ok(
                    response_request_id,
                    {
                        "healthy": True,
                        "backend": "fake",
                        "protocol_version": SUPPORTED_PROTOCOL_MAX,
                        "schema_version": schema_version,
                    },
                )
            )
        elif request.operation == "shutdown":
            _write(CoreResponseEnvelope.ok(request.request_id, {"stopped": True}))
            return 0
        elif request.operation == "ingest_raw_round":
            command_id = str(request.payload.get("command_id", request.request_id))
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "raw_round_id": command_id,
                        "duplicate": False,
                        "status": "queued",
                    },
                )
            )
        elif request.operation == "poll_execution_tasks":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id, {"tasks": [], "has_more": False}
                )
            )
        elif request.operation == "submit_execution_result":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {"accepted": True, "duplicate": False, "status": "accepted"},
                )
            )
        elif request.operation == "fail_execution_task":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "released": True,
                        "retry_scheduled": False,
                        "terminal": True,
                        "status": "failed",
                    },
                )
            )
        elif request.operation == "retrieve_context":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "retrieval_request_id": request.request_id,
                        "items": [
                            {
                                "value_id": "value-1",
                                "primary_object_id": "object-1",
                                "object_name": "Fake object",
                                "facet": "property",
                                "content": "Fake context",
                                "relevance": 0.9,
                                "explanation": {
                                    "object_reasons": ["direct_value_semantic"],
                                    "item_facet": "property",
                                    "activated_facets": [],
                                    "score_components": {
                                        "semantic": 0.9,
                                        "object": 0.0,
                                        "facet": 0.0,
                                        "scope_time": 0.0,
                                        "context": 0.0,
                                        "recency": 0.0,
                                        "support": 0.0,
                                        "usage": 0.0,
                                    },
                                },
                            }
                        ],
                    },
                )
            )
        elif request.operation == "record_retrieval_outcome":
            _write(CoreResponseEnvelope.ok(request.request_id, {"recorded": True}))
        elif request.operation == "run_control_maintenance":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "status": "completed",
                        "memory_echoes_reconciled": 0,
                        "stats_rebuilt": 0,
                        "stale_jobs_recovered": 0,
                        "findings_created": 0,
                        "duplicate_object_findings": 0,
                        "missing_card_embeddings": 0,
                        "missing_facet_embeddings": 0,
                        "integrity_errors": 0,
                        "retried_failed_round_semantic": 0,
                    },
                )
            )
        elif request.operation == "get_object_facet_statistics":
            if request.payload.get("include_projection") is True:
                memory_space_id = str(request.payload.get("memory_space_id", ""))
                _write(
                    CoreResponseEnvelope.ok(
                        request.request_id,
                        {
                            "schema_version": 1,
                            "memory_space_id": memory_space_id,
                            "projection_source": "Core.database",
                            "memory_objects": [],
                            "knowledge_values": [],
                            "value_observations": [],
                            "value_lineage": [],
                            "value_stats": [],
                        },
                    )
                )
                continue
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "object_count": 1,
                        "active_value_count": 1,
                        "superseded_value_count": 0,
                        "operational_backlog": 0,
                        "background_backlog": 0,
                        "embedding_backlog": 0,
                        "integrity_finding_count": 0,
                        "missing_card_embeddings": 0,
                        "missing_facet_embeddings": 0,
                        "legacy_digest_upgrade_required": False,
                    },
                )
            )
        elif request.operation == "delete_memory_space":
            _write(CoreResponseEnvelope.ok(request.request_id, {"deleted": True}))
        elif request.operation == "create_backup":
            relative_path = "exchange/outgoing/fake-core-backup.bin"
            snapshot = b"fake-core-snapshot"
            destination = _exchange_file(core_data_dir, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(snapshot)
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "relative_path": relative_path,
                        "sha256": _digest(snapshot),
                        "size_bytes": len(snapshot),
                        "schema_version": schema_version,
                    },
                )
            )
        elif request.operation in {
            "validate_backup",
            "prepare_restore",
            "begin_restore",
        }:
            raw_relative_path = request.payload.get("relative_path")
            expected_sha = request.payload.get("sha256")
            if (
                not isinstance(raw_relative_path, str)
                or not raw_relative_path.startswith("exchange/incoming/")
                or ".." in raw_relative_path.split("/")
                or not isinstance(expected_sha, str)
            ):
                _error(request.request_id, "INVALID_REQUEST", "invalid exchange path")
                continue
            relative_path = raw_relative_path
            try:
                source = _exchange_file(core_data_dir, relative_path)
                content = source.read_bytes()
            except (OSError, ValueError):
                _error(
                    request.request_id,
                    "INTEGRITY_VIOLATION",
                    "backup artifact is missing",
                )
                continue
            actual_sha = _digest(content)
            if actual_sha != expected_sha:
                _error(
                    request.request_id, "INTEGRITY_VIOLATION", "backup digest mismatch"
                )
                continue
            result: dict[str, object] = {
                "relative_path": relative_path,
                "sha256": actual_sha,
                "size_bytes": len(content),
                "schema_version": schema_version,
            }
            if request.operation == "begin_restore":
                if request.payload.get("restore_token") != "fake-restore-token-1":
                    _error(
                        request.request_id,
                        "INVALID_REQUEST",
                        "restore token is invalid",
                    )
                    continue
                result.update(
                    {
                        "restore_transaction_id": "fake-restore-transaction-1",
                        "state": "applied_pending_commit",
                    }
                )
            elif request.operation == "prepare_restore":
                result.update(
                    {
                        "restore_token": "fake-restore-token-1",
                        "requires_restart": True,
                    }
                )
            _write(CoreResponseEnvelope.ok(request.request_id, result))
        elif request.operation == "commit_restore":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "restore_transaction_id": request.payload.get(
                            "restore_transaction_id"
                        ),
                        "committed": True,
                        "state": "committed",
                    },
                )
            )
        elif request.operation == "rollback_restore":
            _write(
                CoreResponseEnvelope.ok(
                    request.request_id,
                    {
                        "restore_transaction_id": request.payload.get(
                            "restore_transaction_id"
                        ),
                        "rolled_back": True,
                        "state": "rolled_back",
                    },
                )
            )
        else:
            _error(request.request_id, "INVALID_REQUEST", "operation is unavailable")


if __name__ == "__main__":
    raise SystemExit(main())
