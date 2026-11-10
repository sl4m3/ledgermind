from __future__ import annotations


def test_create_app_passes_runtime_retrieval_config(monkeypatch) -> None:
    from fastapi import APIRouter
    from ledgermind_local.api import app as app_module
    from ledgermind_local.api.dependencies import Settings
    from ledgermind_local.config import LocalConfig, RetrievalConfig

    captured: dict[str, object] = {}

    def fake_create_context_router(*args, **kwargs):
        captured.update(kwargs)
        return APIRouter()

    monkeypatch.setattr(app_module, "create_context_router", fake_create_context_router)

    class Runtime:
        config = LocalConfig(
            config_version=1,
            semantic_language="ru",
            retrieval=RetrievalConfig(
                dual_view_rerank=False,
                adaptive_merge=False,
                session_context_query_chars=0,
            ),
        )

    class Application:
        runtime = Runtime()

    app_module.create_app(
        application=Application(),
        settings=Settings(database_path=":memory:", api_token="token"),
    )

    retrieval = captured["retrieval_config"]
    assert retrieval.dual_view_rerank is False
    assert retrieval.adaptive_merge is False
    assert retrieval.session_context_query_chars == 0
