"""HTTP endpoint for immutable RawRound capture."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from ledgermind_protocol import RawRoundRequest

from ledgermind_local.raw_rounds import (
    RawRoundConflict,
    RawRoundDigestMismatch,
    RawRoundError,
    RawRoundTooLarge,
)

from .http import build_request_id, error_payload


def create_rounds_router(
    require_token: Callable[..., str], raw_round_handler: Any
) -> APIRouter:
    router = APIRouter()

    @router.post("/rounds", status_code=status.HTTP_202_ACCEPTED)
    def ingest_round(
        payload: RawRoundRequest,
        request: Request,
        response: Response,
        _token: str = Depends(require_token),
    ) -> dict[str, object]:
        try:
            result = raw_round_handler.handle(payload)
        except RawRoundConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_payload("source_round_conflict", str(exc)),
            ) from exc
        except RawRoundTooLarge as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=error_payload("raw_round_too_large", str(exc)),
            ) from exc
        except (RawRoundDigestMismatch, RawRoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_payload("invalid_raw_round", str(exc)),
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_payload("database_unavailable", "database unavailable"),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_payload(
                    "raw_round_ingestion_failed", "raw round ingestion failed"
                ),
            ) from exc

        response.status_code = (
            status.HTTP_200_OK if result.duplicate else status.HTTP_202_ACCEPTED
        )
        response.headers["X-Request-ID"] = build_request_id(request.headers)
        response.headers["Cache-Control"] = "no-store"
        return {
            "schema_version": 2,
            "raw_round_id": result.raw_round_id,
            "core_command_id": result.core_command_id,
            "duplicate": result.duplicate,
            "status": result.status,
            "core_raw_round_id": result.core_raw_round_id,
        }

    return router
