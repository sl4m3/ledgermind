from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledgermind_local.api.knowledge import create_knowledge_router
from ledgermind_local.core_gateway.contracts import DomainRejectedError


class _Gateway:
    def __init__(self) -> None:
        self.memory_space_ids: list[str] = []
        self.deleted_memory_space_ids: list[str] = []

    def get_object_facet_snapshot(
        self,
        memory_space_id: str,
        request_id: str,
        *,
        cursor: str | None = None,
        page_size: int = 10_000,
    ) -> dict[str, Any]:
        assert request_id
        assert cursor is None
        assert page_size == 10_000
        self.memory_space_ids.append(memory_space_id)
        digest = "a" * 64
        return {
            "schema_version": 2,
            "memory_space_id": memory_space_id,
            "snapshot": {
                "schema_version": 1,
                "memory_space_id": memory_space_id,
                "knowledge_values": [{"value_id": f"value:{memory_space_id}"}],
            },
            "page": {
                "cursor": f"page:{digest}:0",
                "next_cursor": None,
                "item_count": 1,
                "total_items": 1,
                "complete": True,
            },
        }

    def delete_memory_space(self, memory_space_id: str, request_id: str) -> bool:
        assert request_id
        self.deleted_memory_space_ids.append(memory_space_id)
        return True


def test_export_contains_only_matching_memory_spaces(tmp_path: Path) -> None:
    database_path = tmp_path / "rounds.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE memory_spaces (memory_space_id TEXT PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT INTO memory_spaces VALUES (?)",
            [
                ("tenant:user:workspace:one:default",),
                ("tenant:user:workspace:one:project",),
                ("tenant:user:workspace:two:default",),
            ],
        )

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_knowledge_router(lambda: "token", gateway, database_path=database_path)
    )

    response = TestClient(app).post(
        "/knowledge/export",
        json={"memory_space_prefix": "tenant:user:workspace:one:"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 2
    assert [item["memory_space_id"] for item in payload["memory_spaces"]] == [
        "default",
    ]
    assert payload["page"]["next_cursor"] == "page:1:start:0"

    second_page = TestClient(app).post(
        "/knowledge/export",
        json={
            "memory_space_prefix": "tenant:user:workspace:one:",
            "cursor": payload["page"]["next_cursor"],
        },
    )
    assert second_page.status_code == 200
    assert [
        item["memory_space_id"] for item in second_page.json()["memory_spaces"]
    ] == ["project"]
    assert second_page.json()["page"]["complete"] is True
    assert gateway.memory_space_ids == [
        "tenant:user:workspace:one:default",
        "tenant:user:workspace:one:project",
    ]

    purged = TestClient(app).post(
        "/knowledge/purge",
        json={"memory_space_prefix": "tenant:user:workspace:one:"},
    )
    assert purged.status_code == 200
    assert purged.json() == {"deleted_memory_spaces": 2}
    assert gateway.deleted_memory_space_ids == [
        "tenant:user:workspace:one:default",
        "tenant:user:workspace:one:project",
    ]
    with sqlite3.connect(database_path) as connection:
        remaining = connection.execute(
            "SELECT memory_space_id FROM memory_spaces"
        ).fetchall()
    assert remaining == [("tenant:user:workspace:two:default",)]


def test_export_rejects_malformed_cursor_without_calling_core(tmp_path: Path) -> None:
    database_path = tmp_path / "rounds.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE memory_spaces (memory_space_id TEXT PRIMARY KEY)"
        )
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_knowledge_router(lambda: "token", gateway, database_path=database_path)
    )

    response = TestClient(app).post(
        "/knowledge/export",
        json={"memory_space_prefix": "tenant:", "cursor": "broken"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_export_request"
    assert gateway.memory_space_ids == []


def test_export_reports_projection_item_too_large(tmp_path: Path) -> None:
    class OversizedGateway(_Gateway):
        def get_object_facet_snapshot(
            self,
            memory_space_id: str,
            request_id: str,
            *,
            cursor: str | None = None,
            page_size: int = 10_000,
        ) -> dict[str, Any]:
            raise DomainRejectedError(
                "invalid_request",
                "projection_item_too_large: one item exceeds the safe page size",
            )

    database_path = tmp_path / "rounds.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE memory_spaces (memory_space_id TEXT PRIMARY KEY)"
        )
        connection.execute("INSERT INTO memory_spaces VALUES ('tenant:default')")
    app = FastAPI()
    app.include_router(
        create_knowledge_router(
            lambda: "token", OversizedGateway(), database_path=database_path
        )
    )

    response = TestClient(app).post(
        "/knowledge/export", json={"memory_space_prefix": "tenant:"}
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "projection_too_large"
