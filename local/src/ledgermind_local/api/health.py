"""Health endpoints for the local LedgerMind service."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from starlette import status

from ledgermind_local.diagnostics.health import (
    run_capture_readiness_checks,
    run_full_readiness_checks,
)


def _response_for_report(report: dict[str, object], *, ready_key: str) -> object:
    if bool(report.get(ready_key, report.get("ready", False))):
        return report
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=report,
    )


def create_health_router(
    require_token: Callable[..., object],
    maybe_token: Callable[..., object],
    *,
    database_path: Path,
    service_lock_path: Path | None,
    write_handler: object,
    runtime: object | None = None,
) -> APIRouter:
    """Build live, capture-ready, full-ready and diagnostic health routes."""

    router = APIRouter()

    @router.get("/health/live")
    def health_live(details: bool = Depends(maybe_token)) -> dict[str, str | bool]:
        payload: dict[str, str | bool] = {"status": "ok"}
        if details:
            payload["healthy"] = True
            payload["database_path"] = str(database_path)
            payload["capture_ready"] = bool(
                getattr(runtime, "capture_ready", True) if runtime is not None else True
            )
        return payload

    @router.get("/health/capture-ready", response_model=None)
    def health_capture_ready(_token: str = Depends(require_token)) -> object:
        del _token
        report = run_capture_readiness_checks(
            database_path=database_path,
            service_lock_path=service_lock_path,
            write_handler=write_handler,
            runtime=runtime,
        )
        return _response_for_report(report, ready_key="capture_ready")

    @router.get("/health/full-ready", response_model=None)
    @router.get("/health/ready", response_model=None)
    def health_full_ready(_token: str = Depends(require_token)) -> object:
        del _token
        report = run_full_readiness_checks(
            database_path=database_path,
            service_lock_path=service_lock_path,
            write_handler=write_handler,
            runtime=runtime,
        )
        return _response_for_report(report, ready_key="full_ready")

    @router.get("/health/details")
    def health_details(_token: str = Depends(require_token)) -> object:
        del _token
        report = run_full_readiness_checks(
            database_path=database_path,
            service_lock_path=service_lock_path,
            write_handler=write_handler,
            runtime=runtime,
        )
        # Details remain queryable while capture is alive so operators can see why
        # full readiness is degraded.
        if runtime is not None and bool(report.get("capture_ready", False)):
            return report
        return _response_for_report(report, ready_key="full_ready")

    return router
