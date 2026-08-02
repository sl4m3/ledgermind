"""Contract tests for atom ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pydantic
import pytest

from contracts.atom import IngestAtomRequest


def _fixture_request() -> dict:
    return {
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
            "message_ids": ["18420", "18421", "18422", "18423", "18424", "18425", "18426", "18427"],
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
            "statement": "Локальная версия LedgerMind хранит каноническое состояние в одной SQLite-базе.",
            "rationale": "Markdown, Git и векторный индекс должны быть пересобираемыми проекциями, чтобы сбой одной из них не нарушал атомарность знания.",
            "result": "Архитектура разделяет каноническую транзакцию и асинхронное обновление проекций.",
            "artifacts": ["docs/adr/0006-sqlite-canonical-store.md"],
        },
    }


def test_valid_ingest_atom_request() -> None:
    request = _fixture_request()
    parsed = IngestAtomRequest.model_validate(request)

    assert parsed.api_version == "1"
    assert parsed.memory_space_id == request["memory_space_id"]


def test_unknown_root_field_is_rejected() -> None:
    request = _fixture_request()
    request["phase"] = "pattern"

    with pytest.raises(pydantic.ValidationError):
        IngestAtomRequest.model_validate(request)


def test_phase_status_confidence_fields_are_rejected() -> None:
    request = _fixture_request()
    request["atom"]["status"] = "pattern"
    with pytest.raises(pydantic.ValidationError):
        IngestAtomRequest.model_validate(request)

    request2 = _fixture_request()
    request2["source"]["confidence"] = 0.7
    with pytest.raises(pydantic.ValidationError):
        IngestAtomRequest.model_validate(request2)


def test_incorrect_checksum_is_rejected() -> None:
    request = _fixture_request()
    request["idempotency_key"] = "bad-checksum"

    with pytest.raises(pydantic.ValidationError):
        IngestAtomRequest.model_validate(request)


def test_payload_size_limits_are_enforced() -> None:
    request = _fixture_request()
    request["atom"]["statement"] = "x" * 20_001

    with pytest.raises(pydantic.ValidationError):
        IngestAtomRequest.model_validate(request)


def test_no_circular_import_between_contract_modules() -> None:
    import contracts.atom as atom
    import contracts.common as common

    if not common.__file__ or not atom.__file__:
        raise AssertionError("contract module file path missing")

    atom_source = Path(atom.__file__).read_text(encoding="utf-8")
    common_source = Path(common.__file__).read_text(encoding="utf-8")

    assert "from .atom import" not in common_source
    assert "from .common import" not in atom_source
    assert "from .atom import" not in atom_source

    assert atom is not None


def test_schema_can_be_exported_and_matches_snapshot() -> None:
    snapshot_path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "snapshots"
        / "ingest_atom.schema.json"
    )
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    exported = IngestAtomRequest.model_json_schema()
    assert exported == expected
