from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ledgermind_local.api.app import _resolve_session_context_database_path


def test_session_context_prefers_core_database(tmp_path: Path) -> None:
    core_database = tmp_path / "core" / "knowledge.db"

    class Paths:
        def resolve_knowledge_database_path(self, value: str) -> Path:
            assert value == "../core/knowledge.db"
            return core_database

    runtime = SimpleNamespace(
        config=SimpleNamespace(knowledge_database_path="../core/knowledge.db"),
        paths=Paths(),
    )

    assert (
        _resolve_session_context_database_path(
            runtime, tmp_path / "rounds.db"
        )
        == core_database
    )


def test_session_context_falls_back_to_rounds_database(tmp_path: Path) -> None:
    fallback = tmp_path / "rounds.db"

    assert _resolve_session_context_database_path(None, fallback) == fallback
    assert (
        _resolve_session_context_database_path(
            SimpleNamespace(config=SimpleNamespace(knowledge_database_path="x")),
            fallback,
        )
        == fallback
    )

    class BrokenPaths:
        def resolve_knowledge_database_path(self, value: str) -> Path:
            del value
            raise OSError("missing")

    runtime = SimpleNamespace(
        config=SimpleNamespace(knowledge_database_path="x"),
        paths=BrokenPaths(),
    )
    assert _resolve_session_context_database_path(runtime, fallback) == fallback
