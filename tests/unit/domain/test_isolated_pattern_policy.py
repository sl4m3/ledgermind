"""Tests for isolated pattern evolution policy."""

from __future__ import annotations

from datetime import datetime, timezone

from domain import Atom, AtomContent, ExtractionInfo, SourceReference
from domain.knowledge import KnowledgeItem
from domain.phase import Phase
from domain.policies import CreateNewPattern, IsolatedPatternPolicy


def _atom() -> Atom:
    return Atom(
        atom_id="atm_1",
        memory_space_id="space",
        source=SourceReference(
            source_system="hermes",
            source_instance_id="inst_1",
            source_profile_id="profile",
            source_session_id="sess",
            source_round_id="round",
            first_message_id="m1",
            final_message_id="m1",
            message_ids=("m1",),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=1,
            resolver_version=1,
        ),
        content=AtomContent(
            title="auth",
            target="architecture.auth",
            statement="Атрибуты auth должны валидироваться строго.",
            rationale="Безопасность.",
            result="Нужна строгая политика.",
        ),
        extraction=ExtractionInfo(
            host="hermes",
            provider="provider",
            model="model",
            prompt_version=1,
            schema_version=1,
            purpose="ledgermind.atom.extract",
        ),
        content_digest="sha256:" + "b" * 64,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _knowledge(knowledge_id: str, suffix: str) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id="space",
        title=f"auth pattern {suffix}",
        target="architecture.auth",
        statement="Проверка auth похожа на прошлую.",
        rationale="Довольно схоже.",
        phase=Phase.PATTERN,
        version=1,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_isolated_pattern_policy_always_creates_new_pattern() -> None:
    decision = IsolatedPatternPolicy().decide(
        _atom(),
        (_knowledge("k1", "A"), _knowledge("k2", "B")),
    )

    assert isinstance(decision, CreateNewPattern)
    assert decision.title == "auth"
    assert decision.target == "architecture.auth"
    assert decision.statement == "Атрибуты auth должны валидироваться строго."
    assert decision.rationale == "Безопасность."
