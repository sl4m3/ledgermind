"""Tests for contract-to-domain mapper logic."""

from __future__ import annotations

import pytest

from application.mappers import (
    IngestAtomCommand,
    map_context_query,
    map_ingest_atom_request,
)


def _raw_ingest_payload() -> dict:
    return {
        "api_version": "1",
        "idempotency_key": "sha256:" + "a" * 64,
        "memory_space_id": " hermes:src_01K0ABCDEF:default ",
        "source": {
            "source_system": "hermes",
            "source_instance_id": " src_01K0ABCDEF ",
            "source_profile_id": " default ",
            "source_session_id": " 20260801_182422_abcd1234 ",
            "source_round_id": " turn_01K0ROUND ",
            "first_message_id": " 18420 ",
            "final_message_id": " 18427 ",
            "message_ids": [" 18420 ", " 18421 "],
            "source_digest": "sha256:" + "b" * 64,
            "source_schema_version": 23,
            "resolver_version": 1,
        },
        "extraction": {
            "host": " hermes ",
            "provider": " openrouter ",
            "model": " openai/gpt-5.3-codex ",
            "prompt_version": 1,
            "schema_version": 1,
            "purpose": " ledgermind.atom.extract ",
        },
        "atom": {
            "title": " SQLite как каноническое локальное хранилище ",
            "target": " architecture.storage.local ",
            "statement": " Локальная версия LedgerMind хранит каноническое состояние.\\nСтабильные правила. ",
            "rationale": " test rationale ",
            "result": " test result ",
            "artifacts": [" docs/adr/0006-sqlite-canonical-store.md "],
        },
    }


def test_map_ingest_request_normalizes_external_whitespace_once() -> None:
    command = map_ingest_atom_request(_raw_ingest_payload(), request_hash="sha256:" + "a" * 64)

    assert isinstance(command, IngestAtomCommand)
    assert command.memory_space_id == "hermes:src_01K0ABCDEF:default"
    assert command.source.source_instance_id == "src_01K0ABCDEF"
    assert command.source.message_ids == ("18420", "18421")
    assert command.content.statement == "Локальная версия LedgerMind хранит каноническое состояние.\\nСтабильные правила."
    assert command.content.statement.startswith("Локальная")


def test_map_ingest_request_requires_known_api_version() -> None:
    payload = _raw_ingest_payload()
    payload["api_version"] = "2"

    with pytest.raises(ValueError, match="unsupported api_version"):
        map_ingest_atom_request(payload, request_hash="sha256:" + "a" * 64)


def test_checksum_mismatch_is_not_silent() -> None:
    payload = _raw_ingest_payload()

    with pytest.raises(ValueError, match="checksum mismatch"):
        map_ingest_atom_request(payload, request_hash="sha256:" + "c" * 64)


def test_context_query_mapping() -> None:
    query_payload = {
        "api_version": "1",
        "memory_space_id": " hermes:src_01K0ABCDEF:default ",
        "query": "как сделать хранение атомарным",
        "limit": 10,
        "min_phase": "pattern",
    }

    query = map_context_query(query_payload)

    assert query.memory_space_id == "hermes:src_01K0ABCDEF:default"
    assert query.query == "как сделать хранение атомарным"
    assert query.limit == 10
    assert query.min_phase == "pattern"


def test_context_query_rejects_unknown_fields_and_values() -> None:
    query_payload = {
        "api_version": "1",
        "memory_space_id": "space",
        "query": "q",
        "limit": 5,
        "confidence": 0.5,  # type: ignore[call-arg]
    }

    with pytest.raises(ValueError):
        map_context_query(query_payload)
