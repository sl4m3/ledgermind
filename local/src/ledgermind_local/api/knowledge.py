"""Read-only knowledge export for an authenticated runtime client."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core_gateway.contracts import DomainRejectedError, TransientCoreError
from .http import error_payload


class KnowledgeExportRequest(BaseModel):
    memory_space_prefix: str = Field(min_length=1, max_length=500)
    cursor: str | None = Field(default=None, max_length=100)
    page_size: int = Field(default=10_000, ge=1, le=10_000)


def _parse_export_cursor(cursor: str | None) -> tuple[int, str | None]:
    if cursor is None:
        return 0, None
    parts = cursor.split(":")
    if len(parts) != 4 or parts[0] != "page":
        raise ValueError("export cursor is malformed")
    try:
        space_index = int(parts[1])
        core_offset = int(parts[3])
    except ValueError as exc:
        raise ValueError("export cursor is malformed") from exc
    digest = parts[2]
    if (
        space_index < 0
        or core_offset < 0
        or (
            digest != "start"
            and (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            )
        )
    ):
        raise ValueError("export cursor is malformed")
    if digest == "start":
        if core_offset != 0:
            raise ValueError("export cursor is malformed")
        return space_index, None
    return space_index, f"page:{digest}:{core_offset}"


def create_knowledge_router(
    require_token: Callable[..., str],
    core_gateway: object | None,
    *,
    database_path: Path,
) -> APIRouter:
    router = APIRouter(prefix="/knowledge", tags=["knowledge"])

    @router.post("/export")
    def export_knowledge(
        payload: KnowledgeExportRequest,
        _token: str = Depends(require_token),
    ) -> dict[str, Any]:
        del _token
        prefix = payload.memory_space_prefix.strip()
        if not prefix:
            raise HTTPException(
                status_code=422, detail="memory_space_prefix is required"
            )
        export_snapshot = getattr(core_gateway, "get_object_facet_snapshot", None)
        if not callable(export_snapshot):
            raise HTTPException(
                status_code=503, detail="Knowledge export is unavailable"
            )

        try:
            space_index, core_cursor = _parse_export_cursor(payload.cursor)
            with sqlite3.connect(database_path) as connection:
                memory_space_ids = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
                    )
                    if str(row[0]).startswith(prefix)
                ]
            if space_index > len(memory_space_ids):
                raise ValueError("export cursor is outside the matching memory spaces")
            spaces: list[dict[str, Any]] = []
            page_item_count = 0
            current_cursor: str | None = payload.cursor
            next_cursor: str | None = None
            if space_index < len(memory_space_ids):
                memory_space_id = memory_space_ids[space_index]
                core_page = export_snapshot(
                    memory_space_id,
                    uuid4().hex,
                    cursor=core_cursor,
                    page_size=payload.page_size,
                )
                core_page_info = core_page["page"]
                page_item_count = int(core_page_info["item_count"])
                core_current = str(core_page_info["cursor"])
                current_cursor = (
                    f"page:{space_index}:{core_current.removeprefix('page:')}"
                )
                spaces.append(
                    {
                        "memory_space_id": memory_space_id.removeprefix(prefix)
                        or "default",
                        "snapshot": core_page["snapshot"],
                    }
                )
                core_next = core_page_info.get("next_cursor")
                if isinstance(core_next, str):
                    next_cursor = (
                        f"page:{space_index}:{core_next.removeprefix('page:')}"
                    )
                elif space_index + 1 < len(memory_space_ids):
                    next_cursor = f"page:{space_index + 1}:start:0"
        except DomainRejectedError as exc:
            status_code = 413 if "projection_item_too_large" in exc.detail else 422
            if status_code == 413:
                code = "projection_too_large"
            elif "projection_snapshot_changed" in exc.detail:
                code = "projection_snapshot_changed"
            else:
                code = "invalid_export_cursor"
            raise HTTPException(
                status_code=status_code,
                detail=error_payload(code, exc.detail),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_payload("invalid_export_request", str(exc)),
            ) from exc
        except TransientCoreError as exc:
            code = (
                "projection_frame_too_large"
                if "frame exceeds maximum size" in str(exc)
                else "core_unavailable"
            )
            status_code = 413 if code == "projection_frame_too_large" else 503
            raise HTTPException(
                status_code=status_code,
                detail=error_payload(code, str(exc)),
            ) from exc
        except (OSError, sqlite3.Error) as exc:
            raise HTTPException(
                status_code=503,
                detail=error_payload("knowledge_export_failed", str(exc)),
            ) from exc

        return {
            "schema_version": 2,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memory_spaces": spaces,
            "page": {
                "cursor": current_cursor,
                "next_cursor": next_cursor,
                "item_count": page_item_count,
                "complete": next_cursor is None,
            },
        }

    @router.post("/purge")
    def purge_knowledge(
        payload: KnowledgeExportRequest,
        _token: str = Depends(require_token),
    ) -> dict[str, Any]:
        del _token
        prefix = payload.memory_space_prefix.strip()
        if not prefix:
            raise HTTPException(
                status_code=422, detail="memory_space_prefix is required"
            )
        purge_memory_space = getattr(core_gateway, "delete_memory_space", None)
        if not callable(purge_memory_space):
            raise HTTPException(
                status_code=503, detail="Knowledge deletion is unavailable"
            )

        try:
            with sqlite3.connect(database_path) as connection:
                memory_space_ids = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
                    )
                    if str(row[0]).startswith(prefix)
                ]
            for memory_space_id in memory_space_ids:
                purge_memory_space(memory_space_id, uuid4().hex)
            with sqlite3.connect(database_path) as connection:
                connection.executemany(
                    "DELETE FROM memory_spaces WHERE memory_space_id = ?",
                    [(memory_space_id,) for memory_space_id in memory_space_ids],
                )
        except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
            raise HTTPException(
                status_code=503, detail="Knowledge deletion failed"
            ) from exc

        return {"deleted_memory_spaces": len(memory_space_ids)}

    return router


__all__ = ["create_knowledge_router"]
