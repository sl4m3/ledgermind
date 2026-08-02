"""Manual knowledge supersession use case for LedgerMind core."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from application.errors import (
    AtomAlreadySuperseded,
    ConcurrentModification,
    InvalidSupersession,
    KnowledgeNotFound,
    MemorySpaceMismatch,
    SupersedeKnowledgeError,
)
from application.mappers import SupersedeKnowledgeCommand
from domain import AtomId, KnowledgeId, KnowledgeItem, KnowledgeRevision, Phase, RevisionId
from domain.events import KnowledgeCreated, KnowledgeSuperseded
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


def _json_superseded_payload(
    old_knowledge_id: str,
    new_knowledge_id: str,
    cause_atom_id: str | None,
) -> str:
    return json.dumps(
        {
            "event_type": KnowledgeSuperseded.EVENT_NAME,
            "previous_knowledge_id": old_knowledge_id,
            "next_knowledge_id": new_knowledge_id,
            "by_atom_id": cause_atom_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_knowledge_created_payload(knowledge_id: str) -> str:
    return json.dumps(
        {
            "event_type": KnowledgeCreated.EVENT_NAME,
            "aggregate_id": knowledge_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class SupersedeKnowledgeResult:
    replacement_knowledge_id: str
    replacement_version: int
    superseded_knowledge_ids: tuple[str, ...]


class _SupersedeKnowledgeNotFoundError(SupersedeKnowledgeError, KnowledgeNotFound):
    pass


class _SupersedeKnowledgeMismatchError(SupersedeKnowledgeError, MemorySpaceMismatch):
    pass


class _SupersedeKnowledgeStateError(SupersedeKnowledgeError, AtomAlreadySuperseded):
    pass


class _SupersedeKnowledgeConcurrentError(SupersedeKnowledgeError, ConcurrentModification):
    pass


class _SupersedeKnowledgeInvalidError(SupersedeKnowledgeError, InvalidSupersession):
    pass


class SupersedeKnowledgeHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        clock: Clock,
        identifiers: IdentifierFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = identifiers

    def _load_knowledge(
        self,
        uow: UnitOfWork,
        command: SupersedeKnowledgeCommand,
    ) -> dict[str, KnowledgeItem]:
        knowledge_map: dict[str, KnowledgeItem] = {
            item.knowledge_id: item
            for item in uow.knowledge.get_many(command.memory_space_id, command.old_knowledge_ids)
        }
        expected = set(command.old_knowledge_ids)
        if expected != set(knowledge_map):
            missing = ", ".join(sorted(expected - set(knowledge_map)))
            raise _SupersedeKnowledgeNotFoundError(f"unknown old knowledge ids: {missing}")
        return knowledge_map

    def _assert_same_memory_space(
        self,
        command: SupersedeKnowledgeCommand,
        knowledge: KnowledgeItem,
    ) -> None:
        if knowledge.memory_space_id != command.memory_space_id:
            raise _SupersedeKnowledgeMismatchError(
                "all old knowledge must have the same memory_space_id"
            )

    def _assert_current(self, knowledge_id: str, knowledge: KnowledgeItem) -> None:
        if knowledge.superseded_by_id is not None:
            raise _SupersedeKnowledgeStateError(f"{knowledge_id} is already superseded")
        if knowledge.deleted_at is not None:
            raise _SupersedeKnowledgeInvalidError(f"{knowledge_id} is deleted")

    def _assert_expected_versions(
        self,
        command: SupersedeKnowledgeCommand,
        knowledge_map: dict[str, KnowledgeItem],
    ) -> None:
        for knowledge_id in command.old_knowledge_ids:
            expected_version = command.expected_versions[knowledge_id]
            current = knowledge_map[knowledge_id]
            if current.version != expected_version:
                raise _SupersedeKnowledgeConcurrentError(
                    f"expected version mismatch for {knowledge_id}: "
                    f"expected {expected_version}, got {current.version}"
                )

    def _assert_no_cycle(self, knowledge_map: dict[str, KnowledgeItem]) -> None:
        for start_id in knowledge_map:
            visited: set[str] = set()
            current = start_id
            while True:
                current_knowledge = knowledge_map.get(current)
                if current_knowledge is None or current_knowledge.superseded_by_id is None:
                    break
                target = current_knowledge.superseded_by_id
                if target in visited:
                    raise _SupersedeKnowledgeInvalidError(
                        "cycle detected in supersession graph"
                    )
                if target not in knowledge_map:
                    break
                visited.add(current)
                current = target

    def _build_revision(
        self,
        knowledge: KnowledgeItem,
        event_type: str,
        caused_by_atom_id: str | None,
    ) -> KnowledgeRevision:
        return KnowledgeRevision.from_snapshot(
            revision_id=RevisionId(self._ids.new_revision_id()),
            knowledge_id=KnowledgeId(knowledge.knowledge_id),
            version=knowledge.version,
            event_type=event_type,
            snapshot=_knowledge_snapshot(knowledge),
            cause_atom_id=AtomId(caused_by_atom_id) if caused_by_atom_id is not None else None,
            created_at=self._clock.now(),
        )

    def handle(self, command: SupersedeKnowledgeCommand) -> SupersedeKnowledgeResult:
        with self._uow_factory() as uow:
            knowledge_map = self._load_knowledge(uow, command)
            replacement_id = self._ids.new_knowledge_id()
            if replacement_id in command.old_knowledge_ids:
                raise _SupersedeKnowledgeInvalidError(
                    "replacement knowledge id overlaps with old knowledge ids"
                )

            self._assert_no_cycle(knowledge_map)
            for knowledge_id in command.old_knowledge_ids:
                knowledge = knowledge_map[knowledge_id]
                self._assert_same_memory_space(command, knowledge)
                self._assert_current(knowledge_id, knowledge)

            self._assert_expected_versions(command, knowledge_map)

            now = self._clock.now()
            replacement = KnowledgeItem(
                knowledge_id=replacement_id,
                memory_space_id=command.memory_space_id,
                title=command.replacement_title,
                target=command.replacement_target,
                statement=command.replacement_statement,
                rationale=command.replacement_rationale,
                phase=Phase.CANONICAL,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.knowledge.add(replacement)
            uow.revisions.add(
                self._build_revision(
                    knowledge=replacement,
                    event_type=KnowledgeCreated.EVENT_NAME,
                    caused_by_atom_id=command.cause_atom_id,
                )
            )
            uow.events.add(
                DomainEvent(
                    event_id=self._ids.new_event_id(),
                    event_type=KnowledgeCreated.EVENT_NAME,
                    aggregate_id=replacement.knowledge_id,
                    memory_space_id=replacement.memory_space_id,
                    payload_json=_json_knowledge_created_payload(replacement.knowledge_id),
                    occurred_at=now,
                )
            )

            for knowledge_id in command.old_knowledge_ids:
                old = knowledge_map[knowledge_id]
                superseded = KnowledgeItem(
                    knowledge_id=old.knowledge_id,
                    memory_space_id=old.memory_space_id,
                    title=old.title,
                    target=old.target,
                    statement=old.statement,
                    rationale=old.rationale,
                    phase=old.phase,
                    version=old.version + 1,
                    created_at=old.created_at,
                    updated_at=now,
                    superseded_by_id=replacement_id,
                    deleted_at=old.deleted_at,
                )
                uow.knowledge.update(
                    superseded,
                    expected_version=command.expected_versions[knowledge_id],
                )
                uow.revisions.add(
                    self._build_revision(
                        knowledge=superseded,
                        event_type=KnowledgeSuperseded.EVENT_NAME,
                        caused_by_atom_id=command.cause_atom_id,
                    )
                )
                uow.events.add(
                    DomainEvent(
                        event_id=self._ids.new_event_id(),
                        event_type=KnowledgeSuperseded.EVENT_NAME,
                        aggregate_id=old.knowledge_id,
                        memory_space_id=command.memory_space_id,
                        payload_json=_json_superseded_payload(
                            old_knowledge_id=old.knowledge_id,
                            new_knowledge_id=replacement_id,
                            cause_atom_id=command.cause_atom_id,
                        ),
                        occurred_at=now,
                    )
                )

            uow.commit()
            return SupersedeKnowledgeResult(
                replacement_knowledge_id=replacement_id,
                replacement_version=1,
                superseded_knowledge_ids=command.old_knowledge_ids,
            )


__all__ = [
    "SupersedeKnowledgeError",
    "SupersedeKnowledgeHandler",
    "SupersedeKnowledgeResult",
]
