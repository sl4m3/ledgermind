"""Knowledge logical deletion use case for LedgerMind core."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from application.errors import (
    ConcurrentModification,
    DeleteKnowledgeError,
    IntegrityViolation,
    KnowledgeNotFound,
    MemorySpaceMismatch,
)
from domain import (
    AtomId,
    KnowledgeId,
    KnowledgeItem,
    KnowledgeRevision,
    RevisionId,
)
from domain.events import KnowledgeDeleted
from ports import Clock, IdentifierFactory, UnitOfWork
from ports.repository_ports import DomainEvent


def _knowledge_snapshot(knowledge: KnowledgeItem) -> dict[str, object]:
    return {
        "knowledge_id": knowledge.knowledge_id,
        "memory_space_id": knowledge.memory_space_id,
        "title": knowledge.title,
        "target": knowledge.target,
        "statement": knowledge.statement,
        "rationale": knowledge.rationale,
        "phase": knowledge.phase.value,
        "version": knowledge.version,
        "created_at": knowledge.created_at.isoformat(),
        "updated_at": knowledge.updated_at.isoformat(),
        "superseded_by_id": knowledge.superseded_by_id,
        "deleted_at": knowledge.deleted_at.isoformat() if knowledge.deleted_at else None,
    }


def _json_knowledge_deleted_payload(knowledge_id: str, by_atom_id: str) -> str:
    return json.dumps(
        {
            "event_type": KnowledgeDeleted.EVENT_NAME,
            "knowledge_id": knowledge_id,
            "by_atom_id": by_atom_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class DeleteKnowledgeCommand:
    memory_space_id: str
    knowledge_id: str
    expected_version: int
    cause_atom_id: str

    def __post_init__(self) -> None:
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if not self.knowledge_id:
            raise ValueError("knowledge_id must not be empty")
        if not self.cause_atom_id:
            raise ValueError("cause_atom_id must not be empty")
        if self.expected_version < 1:
            raise ValueError("expected_version must be >= 1")


@dataclass(frozen=True, slots=True)
class DeleteKnowledgeResult:
    knowledge_id: str
    version: int
    deleted_at: str | None


class _DeleteKnowledgeNotFoundError(DeleteKnowledgeError, KnowledgeNotFound):
    pass


class _DeleteKnowledgeMismatchError(DeleteKnowledgeError, MemorySpaceMismatch):
    pass


class _DeleteKnowledgeStateError(DeleteKnowledgeError, IntegrityViolation):
    pass


class _DeleteKnowledgeConcurrentError(DeleteKnowledgeError, ConcurrentModification):
    pass


class DeleteKnowledgeHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Clock,
        identifiers: IdentifierFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = identifiers

    def _build_revision(
        self,
        knowledge: KnowledgeItem,
        cause_atom_id: str,
        now: datetime,
    ) -> KnowledgeRevision:
        return KnowledgeRevision.from_snapshot(
            revision_id=RevisionId(self._ids.new_revision_id()),
            knowledge_id=KnowledgeId(knowledge.knowledge_id),
            version=knowledge.version,
            event_type=KnowledgeDeleted.EVENT_NAME,
            snapshot=_knowledge_snapshot(knowledge),
            cause_atom_id=AtomId(cause_atom_id),
            created_at=now,
        )

    def handle(self, command: DeleteKnowledgeCommand) -> DeleteKnowledgeResult:
        with self._uow_factory() as uow:
            knowledge = uow.knowledge.get(command.memory_space_id, command.knowledge_id)
            if knowledge is None:
                raise _DeleteKnowledgeNotFoundError("knowledge not found")
            if knowledge.memory_space_id != command.memory_space_id:
                raise _DeleteKnowledgeMismatchError("knowledge not in requested memory space")
            if knowledge.deleted_at is not None:
                raise _DeleteKnowledgeStateError("knowledge is already deleted")
            if knowledge.version != command.expected_version:
                raise _DeleteKnowledgeConcurrentError(
                    f"expected version mismatch: expected {command.expected_version}, got {knowledge.version}"
                )

            now = self._clock.now()
            deleted = KnowledgeItem(
                knowledge_id=knowledge.knowledge_id,
                memory_space_id=knowledge.memory_space_id,
                title=knowledge.title,
                target=knowledge.target,
                statement=knowledge.statement,
                rationale=knowledge.rationale,
                phase=knowledge.phase,
                version=knowledge.version + 1,
                created_at=knowledge.created_at,
                updated_at=now,
                superseded_by_id=knowledge.superseded_by_id,
                deleted_at=now,
            )

            uow.knowledge.update(deleted, expected_version=command.expected_version)
            uow.revisions.add(
                self._build_revision(
                    knowledge=deleted,
                    cause_atom_id=command.cause_atom_id,
                    now=now,
                )
            )
            uow.events.add(
                DomainEvent(
                    event_id=self._ids.new_event_id(),
                    event_type=KnowledgeDeleted.EVENT_NAME,
                    aggregate_id=knowledge.knowledge_id,
                    memory_space_id=knowledge.memory_space_id,
                    payload_json=_json_knowledge_deleted_payload(
                        knowledge_id=knowledge.knowledge_id,
                        by_atom_id=command.cause_atom_id,
                    ),
                    occurred_at=now,
                )
            )

            uow.commit()

            return DeleteKnowledgeResult(
                knowledge_id=knowledge.knowledge_id,
                version=deleted.version,
                deleted_at=deleted.deleted_at.isoformat() if deleted.deleted_at is not None else None,
            )


__all__ = [
    "DeleteKnowledgeCommand",
    "DeleteKnowledgeError",
    "DeleteKnowledgeHandler",
    "DeleteKnowledgeResult",
]
