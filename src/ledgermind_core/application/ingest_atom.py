"""Atom ingestion use case for LedgerMind core."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from ledgermind_core.application.digests import (
    calculate_atom_content_digest,
    calculate_source_round_key,
)
from ledgermind_core.application.errors import (
    IdempotencyConflict,
    SourceRoundConflict,
    UnsupportedEvolutionDecision,
)
from ledgermind_core.application.mappers import IngestAtomCommand
from ledgermind_core.domain import (
    Atom,
    AtomId,
    EvidenceRelation,
    KnowledgeEvidence,
    KnowledgeId,
    KnowledgeItem,
    KnowledgeRevision,
    Phase,
    RevisionId,
)
from ledgermind_core.domain.events import AtomCreated, KnowledgeCreated
from ledgermind_core.domain.policies import CreateNewPattern, KnowledgeEvolutionPolicy
from ledgermind_core.ports import Clock, IdentifierFactory, UnitOfWork
from ledgermind_core.ports.repository_ports import DomainEvent, StoredIdempotencyResult


@dataclass(frozen=True, slots=True)
class IngestAtomResult:
    atom_id: str
    knowledge_id: str
    knowledge_version: int
    phase: str
    duplicate: bool
    projections_pending: bool


class JsonIngestAtomResultSerializer:
    def result_to_json(self, result: IngestAtomResult) -> str:
        return json.dumps(
            {
                "atom_id": result.atom_id,
                "knowledge_id": result.knowledge_id,
                "knowledge_version": result.knowledge_version,
                "phase": result.phase,
                "duplicate": result.duplicate,
                "projections_pending": result.projections_pending,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def result_from_json(self, response_json: str) -> IngestAtomResult:
        payload = json.loads(response_json)
        return IngestAtomResult(
            atom_id=payload["atom_id"],
            knowledge_id=payload["knowledge_id"],
            knowledge_version=payload["knowledge_version"],
            phase=payload["phase"],
            duplicate=payload["duplicate"],
            projections_pending=payload["projections_pending"],
        )


def _json_event_payload(event_type: str, aggregate_id: str) -> str:
    return json.dumps(
        {
            "event_type": event_type,
            "aggregate_id": aggregate_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _build_knowledge_snapshot(knowledge: KnowledgeItem) -> dict[str, object]:
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


class IngestAtomHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        policy: KnowledgeEvolutionPolicy,
        clock: Clock,
        identifiers: IdentifierFactory,
        serializer: JsonIngestAtomResultSerializer,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._clock = clock
        self._ids = identifiers
        self._serializer = serializer

    def _build_creation_result(
        self,
        atom: Atom,
        knowledge: KnowledgeItem,
        duplicate: bool,
    ) -> IngestAtomResult:
        return IngestAtomResult(
            atom_id=atom.atom_id,
            knowledge_id=knowledge.knowledge_id,
            knowledge_version=knowledge.version,
            phase=knowledge.phase.value,
            duplicate=duplicate,
            projections_pending=True,
        )

    def _build_revision(self, knowledge: KnowledgeItem, atom: Atom) -> KnowledgeRevision:
        return KnowledgeRevision.from_snapshot(
            revision_id=RevisionId(self._ids.new_revision_id()),
            knowledge_id=KnowledgeId(knowledge.knowledge_id),
            version=knowledge.version,
            event_type=KnowledgeCreated.EVENT_NAME,
            snapshot=_build_knowledge_snapshot(knowledge),
            cause_atom_id=AtomId(atom.atom_id),
            created_at=self._clock.now(),
        )

    def _add_domain_events(self, uow: UnitOfWork, atom: Atom, knowledge: KnowledgeItem) -> None:
        uow.events.add(
            DomainEvent(
                event_id=self._ids.new_event_id(),
                event_type=AtomCreated.EVENT_NAME,
                aggregate_id=atom.atom_id,
                memory_space_id=atom.memory_space_id,
                payload_json=_json_event_payload(AtomCreated.EVENT_NAME, atom.atom_id),
                occurred_at=self._clock.now(),
            )
        )
        uow.events.add(
            DomainEvent(
                event_id=self._ids.new_event_id(),
                event_type=KnowledgeCreated.EVENT_NAME,
                aggregate_id=knowledge.knowledge_id,
                memory_space_id=knowledge.memory_space_id,
                payload_json=_json_event_payload(
                    KnowledgeCreated.EVENT_NAME,
                    knowledge.knowledge_id,
                ),
                occurred_at=self._clock.now(),
            )
        )

    def _persist_idempotent_result(
        self,
        uow: UnitOfWork,
        command: IngestAtomCommand,
        result: IngestAtomResult,
    ) -> None:
        uow.idempotency.add(
            StoredIdempotencyResult(
                memory_space_id=command.memory_space_id,
                key=command.idempotency_key,
                request_hash=command.request_hash,
                response_json=self._serializer.result_to_json(result),
            )
        )

    def _existing_source_result(
        self,
        uow: UnitOfWork,
        command: IngestAtomCommand,
        content_digest: str,
    ) -> IngestAtomResult | None:
        existing = uow.atoms.find_by_source_version(
            memory_space_id=command.memory_space_id,
            source_round_key=calculate_source_round_key(command.source),
            prompt_version=command.extraction.prompt_version,
            schema_version=command.extraction.schema_version,
        )
        if existing is None:
            return None
        if existing.content_digest != content_digest:
            raise SourceRoundConflict(command.source.source_round_id)

        evidence = uow.evidence.list_for_atom(
            memory_space_id=command.memory_space_id,
            atom_id=existing.atom_id,
        )
        if not evidence:
            raise SourceRoundConflict(command.source.source_round_id)
        knowledge = uow.knowledge.get(
            command.memory_space_id,
            evidence[0].knowledge_id,
        )
        if knowledge is None:
            raise SourceRoundConflict(command.source.source_round_id)
        return self._build_creation_result(existing, knowledge, duplicate=True)

    def handle(self, command: IngestAtomCommand) -> IngestAtomResult:
        with self._uow_factory() as uow:
            stored = uow.idempotency.get(
                command.memory_space_id,
                command.idempotency_key,
            )
            if stored is not None:
                if stored.request_hash != command.request_hash:
                    raise IdempotencyConflict(command.idempotency_key)
                cached = self._serializer.result_from_json(stored.response_json)
                if cached.duplicate:
                    return cached

                return IngestAtomResult(
                    atom_id=cached.atom_id,
                    knowledge_id=cached.knowledge_id,
                    knowledge_version=cached.knowledge_version,
                    phase=cached.phase,
                    duplicate=True,
                    projections_pending=cached.projections_pending,
                )

            content_digest = calculate_atom_content_digest(
                content=command.content,
                source=command.source,
                extraction=command.extraction,
            )
            existing_result = self._existing_source_result(
                uow=uow,
                command=command,
                content_digest=content_digest,
            )
            if existing_result is not None:
                self._persist_idempotent_result(
                    uow=uow,
                    command=command,
                    result=existing_result,
                )
                uow.commit()
                return existing_result

            now = self._clock.now()
            atom = Atom(
                atom_id=self._ids.new_atom_id(),
                memory_space_id=command.memory_space_id,
                source=command.source,
                content=command.content,
                extraction=command.extraction,
                content_digest=content_digest,
                created_at=now,
            )
            uow.atoms.add(atom)

            decision = self._policy.decide(atom, ())
            if not isinstance(decision, CreateNewPattern):
                raise UnsupportedEvolutionDecision(type(decision).__name__)

            knowledge = KnowledgeItem(
                knowledge_id=self._ids.new_knowledge_id(),
                memory_space_id=command.memory_space_id,
                title=decision.title,
                target=decision.target,
                statement=decision.statement,
                rationale=decision.rationale,
                phase=Phase.PATTERN,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.knowledge.add(knowledge)

            uow.evidence.add(
                KnowledgeEvidence(
                    knowledge_id=KnowledgeId(knowledge.knowledge_id),
                    atom_id=AtomId(atom.atom_id),
                    relation=EvidenceRelation.ORIGIN,
                    created_at=now,
                )
            )

            uow.revisions.add(self._build_revision(knowledge=knowledge, atom=atom))
            self._add_domain_events(uow=uow, atom=atom, knowledge=knowledge)

            result = self._build_creation_result(
                atom=atom,
                knowledge=knowledge,
                duplicate=False,
            )
            self._persist_idempotent_result(uow=uow, command=command, result=result)
            uow.commit()

            return result


__all__ = [
    "IdempotencyConflict",
    "IngestAtomHandler",
    "IngestAtomResult",
    "JsonIngestAtomResultSerializer",
    "UnsupportedEvolutionDecision",
]
