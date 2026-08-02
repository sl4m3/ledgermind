"""Tests for atom ingestion application flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping

import pytest

from application.digests import calculate_atom_content_digest
from application.ingest_atom import (
    IdempotencyConflict,
    IngestAtomHandler,
    IngestAtomResult,
    JsonIngestAtomResultSerializer,
)
from application.mappers import IngestAtomCommand
from domain import (
    AtomContent,
    EvidenceRelation,
    ExtractionInfo,
    Phase,
    SourceReference,
)
from domain.events import AtomCreated, KnowledgeCreated
from domain.policies import IsolatedPatternPolicy
from ports.repository_ports import StoredIdempotencyResult
from tests.fakes import FakeClock, FakeIdentifierFactory, FakeUnitOfWork


_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
_MEMORY_SPACE_ID = "hermes:src_01K0ABCDEF:default"
_IDEMPOTENCY_KEY = "sha256:" + "a" * 64
_REQUEST_HASH = "sha256:" + "b" * 64


def _command(
    *,
    idempotency_key: str = _IDEMPOTENCY_KEY,
    request_hash: str = _REQUEST_HASH,
) -> IngestAtomCommand:
    return IngestAtomCommand(
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        memory_space_id=_MEMORY_SPACE_ID,
        source=SourceReference(
            source_system="hermes",
            source_instance_id="instance",
            source_profile_id="default",
            source_session_id="session",
            source_round_id="round",
            first_message_id=None,
            final_message_id=None,
            message_ids=("m1", "m2"),
            source_digest="sha256:" + "c" * 64,
            source_schema_version=1,
            resolver_version=1,
        ),
        content=AtomContent(
            title="SQLite как каноническое локальное хранилище",
            target="architecture.storage.local",
            statement="Локальная версия LedgerMind хранит каноническое состояние.",
            rationale="test rationale",
            result="test result",
            artifacts=("docs/adr/0006-sqlite-canonical-store.md",),
        ),
        extraction=ExtractionInfo(
            host="hermes",
            provider="openrouter",
            model="openai/gpt-5.3-codex",
            prompt_version=1,
            schema_version=1,
            purpose="ledgermind.atom.extract",
        ),
    )


def _setup(
    *,
    fail_steps: set[str] | None = None,
    idempotency_store: Mapping[str, StoredIdempotencyResult] | None = None,
) -> tuple[IngestAtomHandler, FakeUnitOfWork, JsonIngestAtomResultSerializer]:
    clock = FakeClock(_NOW)
    ids = FakeIdentifierFactory()
    uow = FakeUnitOfWork(
        clock=clock,
        fail_steps=fail_steps,
        idempotency_store=idempotency_store,
    )

    serializer = JsonIngestAtomResultSerializer()
    handler = IngestAtomHandler(
        uow_factory=lambda: uow,
        policy=IsolatedPatternPolicy(),
        clock=clock,
        identifiers=ids,
        serializer=serializer,
    )

    return handler, uow, serializer


def _run_successful_ingest() -> tuple[IngestAtomResult, IngestAtomHandler, FakeUnitOfWork]:
    handler, uow, _ = _setup()
    result = handler.handle(_command())
    return result, handler, uow


def test_ingest_atom_creates_atom_knowledge_origin_revision_and_two_events() -> None:
    command = _command()
    result, _, uow = _run_successful_ingest()

    atoms = uow.atoms.committed().get(_MEMORY_SPACE_ID, {})
    knowledge_items = uow.knowledge.committed().get(_MEMORY_SPACE_ID, {})

    assert len(atoms) == 1
    assert len(knowledge_items) == 1
    assert len(uow.evidence.committed()) == 1
    assert len(uow.revisions.committed()) == 1
    assert len(uow.events.events) == 2

    atom = atoms[result.atom_id]
    knowledge = knowledge_items[result.knowledge_id]
    evidence = uow.evidence.committed()[0]
    revision = uow.revisions.committed()[0]
    first_event, second_event = uow.events.events

    assert atom.source == command.source
    assert atom.content == command.content
    assert atom.extraction == command.extraction
    assert atom.content_digest == calculate_atom_content_digest(
        content=command.content,
        source=command.source,
        extraction=command.extraction,
    )

    assert knowledge.title == command.content.title
    assert knowledge.target == command.content.target
    assert knowledge.statement == command.content.statement
    assert knowledge.rationale == command.content.rationale
    assert knowledge.phase == Phase.PATTERN
    assert knowledge.version == 1

    assert evidence.knowledge_id == result.knowledge_id
    assert evidence.atom_id == result.atom_id
    assert evidence.relation == EvidenceRelation.ORIGIN
    assert evidence.created_at == _NOW

    assert revision.knowledge_id == result.knowledge_id
    assert revision.version == 1
    assert revision.event_type == KnowledgeCreated.EVENT_NAME
    assert revision.cause_atom_id == result.atom_id
    assert revision.snapshot["phase"] == Phase.PATTERN.value
    assert revision.snapshot["memory_space_id"] == _MEMORY_SPACE_ID

    assert first_event.event_type == AtomCreated.EVENT_NAME
    assert first_event.aggregate_id == result.atom_id
    assert first_event.memory_space_id == _MEMORY_SPACE_ID
    assert first_event.occurred_at == _NOW
    assert json.loads(first_event.payload_json) == {
        "event_type": AtomCreated.EVENT_NAME,
        "aggregate_id": result.atom_id,
    }
    assert second_event.event_type == KnowledgeCreated.EVENT_NAME
    assert second_event.aggregate_id == result.knowledge_id
    assert second_event.memory_space_id == _MEMORY_SPACE_ID
    assert second_event.occurred_at == _NOW
    assert json.loads(second_event.payload_json) == {
        "event_type": KnowledgeCreated.EVENT_NAME,
        "aggregate_id": result.knowledge_id,
    }


def test_ingest_atom_keeps_all_objects_in_one_memory_space() -> None:
    result, _, uow = _run_successful_ingest()

    atom = uow.atoms.committed()[_MEMORY_SPACE_ID][result.atom_id]
    knowledge = uow.knowledge.committed()[_MEMORY_SPACE_ID][result.knowledge_id]
    evidence = uow.evidence.committed()[0]
    events = uow.events.events

    assert atom.memory_space_id == _MEMORY_SPACE_ID
    assert knowledge.memory_space_id == _MEMORY_SPACE_ID
    assert evidence.knowledge_id == result.knowledge_id
    assert evidence.relation == EvidenceRelation.ORIGIN
    assert all(event.memory_space_id == _MEMORY_SPACE_ID for event in events)


def test_ingest_atom_creates_phase_pattern() -> None:
    result, _, uow = _run_successful_ingest()

    knowledge = uow.knowledge.committed()[_MEMORY_SPACE_ID][result.knowledge_id]
    assert knowledge.phase == Phase.PATTERN


def test_ingest_atom_creates_version_one_knowledge() -> None:
    result, _, uow = _run_successful_ingest()

    knowledge = uow.knowledge.committed()[_MEMORY_SPACE_ID][result.knowledge_id]
    assert knowledge.version == 1


def test_ingest_atom_commits_once() -> None:
    _, _, uow = _run_successful_ingest()

    assert uow.commit_count == 1


def test_ingest_atom_idempotent_repeat_returns_cached_response_without_new_records() -> None:
    handler, uow, _ = _setup()

    first = handler.handle(_command())
    second = handler.handle(_command())

    assert second == IngestAtomResult(
        atom_id=first.atom_id,
        knowledge_id=first.knowledge_id,
        knowledge_version=first.knowledge_version,
        phase=first.phase,
        duplicate=True,
        projections_pending=first.projections_pending,
    )

    assert uow.commit_count == 1
    assert len(uow.atoms.committed()[_MEMORY_SPACE_ID]) == 1
    assert len(uow.knowledge.committed()[_MEMORY_SPACE_ID]) == 1
    assert len(uow.evidence.committed()) == 1
    assert len(uow.revisions.committed()) == 1
    assert len(uow.events.events) == 2
    assert uow.rollback_count == 0


def test_ingest_atom_idempotent_conflict_on_different_request_hash() -> None:
    serializer = JsonIngestAtomResultSerializer()
    command = _command()

    stored = serializer.result_to_json(
        IngestAtomResult(
            atom_id="atm_999999",
            knowledge_id="knw_999999",
            knowledge_version=1,
            phase=Phase.PATTERN.value,
            duplicate=False,
            projections_pending=True,
        )
    )

    handler, _, _ = _setup(
        idempotency_store={
            _IDEMPOTENCY_KEY: StoredIdempotencyResult(
                key=_IDEMPOTENCY_KEY,
                request_hash="sha256:" + "d" * 64,
                response_json=stored,
            )
        }
    )

    with pytest.raises(IdempotencyConflict):
        handler.handle(command)


def _assert_rollback_on_fail(fail_step: str) -> None:
    handler, uow, _ = _setup(fail_steps={fail_step})

    with pytest.raises(RuntimeError):
        handler.handle(_command())

    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert uow.atoms.committed() == {}
    assert uow.knowledge.committed() == {}
    assert uow.evidence.committed() == []
    assert uow.revisions.committed() == []
    assert uow.idempotency.committed() == {}
    assert uow.events.events == []


def test_ingest_atom_atoms_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("atom.add")


def test_ingest_atom_knowledge_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("knowledge.add")


def test_ingest_atom_evidence_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("evidence.add")


def test_ingest_atom_revisions_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("revision.add")


def test_ingest_atom_events_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("events.add")


def test_ingest_atom_idempotency_add_failure_rolls_back() -> None:
    _assert_rollback_on_fail("idempotency.add")


def test_ingest_atom_commit_failure_does_not_return_success() -> None:
    _assert_rollback_on_fail("commit")


def test_stored_idempotency_response_is_exact_json_match() -> None:
    result, _, uow = _run_successful_ingest()
    stored = uow.idempotency.committed()[_IDEMPOTENCY_KEY]

    assert stored.response_json == JsonIngestAtomResultSerializer().result_to_json(result)

    payload = json.loads(stored.response_json)
    assert payload["duplicate"] is False
    assert payload["projections_pending"] is True
