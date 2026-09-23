"""Boundary protocol for the isolated Core backend."""

from __future__ import annotations

from typing import Any, Protocol

from .contracts import (
    ControlMaintenanceResult,
    CoreHealth,
    FailExecutionTaskCommand,
    FailExecutionTaskResult,
    IngestRawRoundCommand,
    IngestRawRoundResult,
    ObjectFacetStatistics,
    PollExecutionTasksCommand,
    PollExecutionTasksResult,
    RecordRetrievalOutcomeCommand,
    RetrieveContextCommand,
    RetrieveContextResult,
    RunControlMaintenanceCommand,
    SubmitExecutionResult,
    SubmitExecutionResultCommand,
)
from .maintenance import (
    BackupManifest,
    BeginRestoreCommand,
    BeginRestoreResult,
    CommitRestoreCommand,
    CommitRestoreResult,
    CreateBackupCommand,
    PrepareRestoreCommand,
    PrepareRestoreResult,
    RollbackRestoreCommand,
    RollbackRestoreResult,
    ValidateBackupCommand,
)


class CoreGateway(Protocol):
    """Only supported Local boundary for current Core operations."""

    def ingest_raw_round(
        self, command: IngestRawRoundCommand
    ) -> IngestRawRoundResult: ...

    def retrieve_context(
        self, request: RetrieveContextCommand
    ) -> RetrieveContextResult: ...

    def record_retrieval_outcome(
        self, command: RecordRetrievalOutcomeCommand
    ) -> None: ...

    def run_control_maintenance(
        self, command: RunControlMaintenanceCommand
    ) -> ControlMaintenanceResult: ...

    def get_object_facet_statistics(self, request_id: str) -> ObjectFacetStatistics: ...

    def get_object_facet_snapshot(
        self,
        memory_space_id: str,
        request_id: str,
        *,
        cursor: str | None = None,
        page_size: int = 10_000,
    ) -> dict[str, Any]: ...

    def delete_memory_space(self, memory_space_id: str, request_id: str) -> bool: ...

    def poll_execution_tasks(
        self, command: PollExecutionTasksCommand
    ) -> PollExecutionTasksResult: ...

    def submit_execution_result(
        self, command: SubmitExecutionResultCommand
    ) -> SubmitExecutionResult: ...

    def fail_execution_task(
        self, command: FailExecutionTaskCommand
    ) -> FailExecutionTaskResult: ...

    def create_backup(self, command: CreateBackupCommand) -> BackupManifest: ...

    def validate_backup(self, command: ValidateBackupCommand) -> BackupManifest: ...

    def prepare_restore(
        self, command: PrepareRestoreCommand
    ) -> PrepareRestoreResult: ...

    def begin_restore(self, command: BeginRestoreCommand) -> BeginRestoreResult: ...

    def commit_restore(self, command: CommitRestoreCommand) -> CommitRestoreResult: ...

    def rollback_restore(
        self, command: RollbackRestoreCommand
    ) -> RollbackRestoreResult: ...

    def health(self) -> CoreHealth: ...


__all__ = ["CoreGateway"]
