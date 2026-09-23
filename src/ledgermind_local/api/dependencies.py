"""DI containers and request-scoped defaults for the local API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ledgermind_local.core_gateway import CoreGateway


@runtime_checkable
class Application(Protocol):
    """Dependency interface expected by API routes."""

    core_gateway: CoreGateway | None

    def build_ingest_raw_round_handler(self) -> object:
        """Return an immutable RawRound capture handler."""


@dataclass(frozen=True, slots=True, init=False)
class Settings:
    """Runtime settings for API operation."""

    rounds_database_path: Path
    api_token: str | None = None
    service_lock_path: Path | None = None
    max_raw_round_bytes: int = 5_000_000
    raw_round_retention_days: int = 30
    runtime_supervisor: object | None = None

    def __init__(
        self,
        rounds_database_path: str | Path | None = None,
        api_token: str | None = None,
        service_lock_path: Path | None = None,
        max_raw_round_bytes: int = 5_000_000,
        raw_round_retention_days: int = 30,
        runtime_supervisor: object | None = None,
        *,
        database_path: str | Path | None = None,
    ) -> None:
        if rounds_database_path is None:
            rounds_database_path = database_path
        elif database_path is not None and Path(rounds_database_path) != Path(
            database_path
        ):
            raise ValueError("rounds_database_path and database_path disagree")
        if rounds_database_path is None:
            raise TypeError("rounds_database_path is required")
        object.__setattr__(self, "rounds_database_path", Path(rounds_database_path))
        object.__setattr__(self, "api_token", api_token)
        object.__setattr__(self, "service_lock_path", service_lock_path)
        object.__setattr__(self, "max_raw_round_bytes", max_raw_round_bytes)
        object.__setattr__(self, "raw_round_retention_days", raw_round_retention_days)
        object.__setattr__(self, "runtime_supervisor", runtime_supervisor)
        self.__post_init__()

    @property
    def database_path(self) -> Path:
        """Compatibility read alias; config serialization uses rounds name."""

        return self.rounds_database_path

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rounds_database_path", Path(self.rounds_database_path)
        )
        if self.max_raw_round_bytes < 1:
            raise ValueError("max_raw_round_bytes must be positive")
        if self.raw_round_retention_days < 1:
            raise ValueError("raw_round_retention_days must be positive")
        lock_path = self.service_lock_path
        object.__setattr__(
            self,
            "service_lock_path",
            Path(lock_path) if lock_path is not None else None,
        )
