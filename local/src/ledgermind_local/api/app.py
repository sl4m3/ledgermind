"""FastAPI application factory for Local-owned rounds and CoreGateway calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ledgermind_local.bootstrap import build_ingest_raw_round_handler

from .auth import (
    build_bearer_token_dependency,
    build_optional_bearer_token_dependency,
)
from .context import create_context_router
from .dependencies import Application, Settings
from .errors import AuthenticationError, authentication_error_handler
from .health import create_health_router
from .http import error_payload
from .knowledge import create_knowledge_router
from .maintenance import create_maintenance_router
from .rounds import create_rounds_router
from .runtime import create_runtime_router


def _normalize_database_path(database_path: str | Path) -> Path:
    return Path(database_path)


def create_app(
    application: Application,
    settings: Settings,
) -> FastAPI:
    """Create the Local HTTP surface without opening Core storage.

    ``application.core_gateway`` is an optional already-created boundary
    implementation.  The app factory never constructs a Python Core adapter and
    therefore never opens ``knowledge.db`` as part of Local request setup.
    """

    app = FastAPI()
    app.state.application = application
    app.state.database_path = _normalize_database_path(settings.rounds_database_path)

    @app.middleware("http")
    async def reject_oversized_json(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_type = (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if content_type == "application/json":
            body = await request.body()
            if len(body) > settings.max_raw_round_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_payload(
                        "request_too_large",
                        f"request body exceeds {settings.max_raw_round_bytes} bytes",
                    ),
                )
        return await call_next(request)

    if hasattr(application, "build_ingest_raw_round_handler"):
        raw_round_handler = application.build_ingest_raw_round_handler()
    else:
        raw_round_handler = build_ingest_raw_round_handler(
            database_path=app.state.database_path,
            max_raw_round_bytes=settings.max_raw_round_bytes,
            retention_days=settings.raw_round_retention_days,
        )
    core_gateway = getattr(application, "core_gateway", None)
    runtime = getattr(application, "runtime", None)
    if runtime is None and callable(getattr(application, "health_report", None)):
        runtime = application
    context_gateway = getattr(application, "context_gateway", None)
    if context_gateway is None:
        context_gateway = core_gateway
    app.state.raw_round_handler = raw_round_handler
    app.state.core_gateway = core_gateway
    app.state.runtime = runtime
    app.state.runtime_supervisor = settings.runtime_supervisor
    query_embedder = (
        runtime if callable(getattr(runtime, "embed_query", None)) else None
    )
    reranker = getattr(runtime, "retrieval_reranker", None)
    reranker_config = getattr(getattr(runtime, "config", None), "reranker", None)

    require_token = build_bearer_token_dependency(settings=settings)
    maybe_token = build_optional_bearer_token_dependency(settings=settings)
    app.add_exception_handler(
        AuthenticationError, cast(Any, authentication_error_handler)
    )

    @app.get("/ping")
    def ping(_token: str = Depends(require_token)) -> dict[str, str]:
        return {"pong": "true"}

    app.include_router(create_rounds_router(require_token, raw_round_handler))
    app.include_router(
        create_health_router(
            require_token,
            maybe_token,
            database_path=app.state.database_path,
            service_lock_path=settings.service_lock_path,
            write_handler=raw_round_handler,
            runtime=runtime,
        )
    )
    app.include_router(
        create_context_router(
            require_token,
            context_gateway,
            max_body_bytes=settings.max_raw_round_bytes,
            query_embedder=query_embedder,
            reranker=reranker,
            reranker_config=reranker_config,
        )
    )
    app.include_router(create_maintenance_router(require_token, runtime))
    app.include_router(
        create_knowledge_router(
            require_token,
            core_gateway,
            database_path=app.state.database_path,
        )
    )
    app.include_router(
        create_runtime_router(require_token, settings.runtime_supervisor, runtime)
    )

    return app
