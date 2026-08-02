"""Tests for canonical digest functions."""

from __future__ import annotations

from datetime import datetime, timezone

from application.digests import (
    calculate_atom_content_digest,
    calculate_idempotency_key,
    calculate_request_hash,
    calculate_source_round_key,
)
from domain import Atom, AtomContent, ExtractionInfo, SourceReference

_RAW_INGEST_PAYLOAD = {
    "api_version": "1",
    "idempotency_key": "sha256:" + "a" * 64,
    "memory_space_id": "hermes:src_01K0ABCDEF:default",
    "source": {
        "source_system": "hermes",
        "source_instance_id": "src_01K0ABCDEF",
        "source_profile_id": "default",
        "source_session_id": "20260801_182422_abcd1234",
        "source_round_id": "turn_01K0ROUND",
        "first_message_id": "18420",
        "final_message_id": "18427",
        "message_ids": ["18420", "18421"],
        "source_digest": "sha256:" + "b" * 64,
        "source_schema_version": 23,
        "resolver_version": 1,
    },
    "extraction": {
        "host": "hermes",
        "provider": "openrouter",
        "model": "openai/gpt-5.3-codex",
        "prompt_version": 1,
        "schema_version": 1,
        "purpose": "ledgermind.atom.extract",
    },
    "atom": {
        "title": "SQLite как каноническое локальное хранилище",
        "target": "architecture.storage.local",
        "statement": "Локальная версия LedgerMind хранит каноническое состояние.\\nСтабильные правила.",
        "rationale": "test rationale",
        "result": "test result",
        "artifacts": ["docs/adr/0006-sqlite-canonical-store.md"],
    },
}


def _command_data() -> tuple[AtomContent, SourceReference, ExtractionInfo]:
    content = AtomContent(
        title="SQLite как каноническое локальное хранилище",
        target="architecture.storage.local",
        statement="Локальная версия LedgerMind хранит каноническое состояние.\\nСтабильные правила.",
        rationale="test rationale",
        result="test result",
        artifacts=("docs/adr/0006-sqlite-canonical-store.md",),
    )
    source = SourceReference(
        source_system="hermes",
        source_instance_id="src_01K0ABCDEF",
        source_profile_id="default",
        source_session_id="20260801_182422_abcd1234",
        source_round_id="turn_01K0ROUND",
        first_message_id="18420",
        final_message_id="18427",
        message_ids=("18420", "18421"),
        source_digest="sha256:" + "b" * 64,
        source_schema_version=23,
        resolver_version=1,
    )
    extraction = ExtractionInfo(
        host="hermes",
        provider="openrouter",
        model="openai/gpt-5.3-codex",
        prompt_version=1,
        schema_version=1,
        purpose="ledgermind.atom.extract",
    )
    return content, source, extraction


def test_calculate_source_round_key_is_stable() -> None:
    _, source, _ = _command_data()

    assert calculate_source_round_key(source) == "sha256:d44215b3f5997ebb9fe56fc473f7d579e55495f00db304543750402e05deed75"


def test_calculate_idempotency_key_is_deterministic() -> None:
    source_round_key = calculate_source_round_key(_command_data()[1])

    assert (
        calculate_idempotency_key(source_round_key, extraction_prompt_version=1, extraction_schema_version=1)
        == "sha256:16580939715e70a46a070ea65b54982694152e995aa170e72cf03b6a7371dc81"
    )


def test_calculate_request_hash_is_canonical_json() -> None:
    shuffled = {
        "atom": _RAW_INGEST_PAYLOAD["atom"],
        "source": _RAW_INGEST_PAYLOAD["source"],
        "memory_space_id": _RAW_INGEST_PAYLOAD["memory_space_id"],
        "api_version": _RAW_INGEST_PAYLOAD["api_version"],
        "extraction": _RAW_INGEST_PAYLOAD["extraction"],
        "idempotency_key": _RAW_INGEST_PAYLOAD["idempotency_key"],
    }

    assert (
        calculate_request_hash(shuffled)
        == "sha256:c5e5fcf0be07cf9602e734b936c976050c2c2966894ec2075d87490da7d38eca"
    )


def test_calculate_atom_content_digest_covers_payload() -> None:
    content, source, extraction = _command_data()

    assert (
        calculate_atom_content_digest(content, source, extraction)
        == "sha256:fd28c030b3998c8918d30f1ed99d904419931257ab633cd983560a763677af7b"
    )


def test_content_digest_changes_if_any_semantically_relevant_field_changes() -> None:
    content, source, extraction = _command_data()
    reference = calculate_atom_content_digest(content, source, extraction)

    updated_content = Atom(
        atom_id="atm_01",
        memory_space_id="space",
        source=source,
        content=AtomContent(
            title=content.title,
            target=content.target,
            statement=content.statement + " ",
            rationale=content.rationale,
            result=content.result,
            artifacts=content.artifacts,
        ),
        extraction=extraction,
        content_digest="sha256:" + "a" * 64,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    ).content

    changed = calculate_atom_content_digest(updated_content, source, extraction)

    assert changed != reference
