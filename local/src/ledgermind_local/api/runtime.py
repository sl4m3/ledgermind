"""HTTP bridge for on-demand runtime leases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException


def create_runtime_router(
    require_token: Any,
    supervisor: object | None,
    runtime: object | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/runtime", tags=["runtime"])

    def _supervisor() -> Any:
        if supervisor is None:
            raise HTTPException(
                status_code=503, detail="runtime supervisor is unavailable"
            )
        return supervisor

    @router.post("/acquire")
    def acquire(
        payload: dict[str, Any], _token: str = Depends(require_token)
    ) -> dict[str, Any]:
        try:
            return dict(
                _supervisor().acquire(
                    client=str(payload.get("client", "")),
                    session_id=str(payload.get("session_id", "")),
                    ttl_seconds=(
                        float(payload["ttl_seconds"])
                        if payload.get("ttl_seconds") is not None
                        else None
                    ),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/heartbeat")
    def heartbeat(
        payload: dict[str, Any], _token: str = Depends(require_token)
    ) -> dict[str, Any]:
        try:
            return dict(_supervisor().heartbeat(str(payload.get("lease_id", ""))))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="lease not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/release")
    def release(
        payload: dict[str, Any], _token: str = Depends(require_token)
    ) -> dict[str, Any]:
        try:
            return dict(_supervisor().release(str(payload.get("lease_id", ""))))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/status")
    def status(_token: str = Depends(require_token)) -> dict[str, Any]:
        return dict(_supervisor().status())

    @router.get("/activity")
    def activity(_token: str = Depends(require_token)) -> dict[str, Any]:
        report = getattr(runtime, "activity_report", None)
        if not callable(report):
            raise HTTPException(
                status_code=503, detail="runtime activity is unavailable"
            )
        return dict(report())

    return router


__all__ = ["create_runtime_router"]
