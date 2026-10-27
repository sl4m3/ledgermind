"""SQLite unit-of-work helper."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import ClassVar

from typing_extensions import Self

from .database import open_sqlite_connection
from .memory_space_repository import SQLiteMemorySpaceRepository
from .raw_round_repository import SQLiteRawRoundRepository


class SQLiteUnitOfWorkError(RuntimeError):
    """Base error for unit-of-work misuse."""


class SQLiteUnitOfWorkInactiveError(SQLiteUnitOfWorkError):
    """Raised when unit-of-work is used outside an active transaction scope."""


@dataclass
class SQLiteUnitOfWork:
    """Transaction boundary that owns exactly one connection and one transaction."""

    database_path: str | Path
    busy_timeout_ms: int = 5_000
    write_transaction: bool = True

    _connection: sqlite3.Connection | None = None
    _committed: bool = False
    _memory_spaces: SQLiteMemorySpaceRepository | None = None
    _raw_rounds: SQLiteRawRoundRepository | None = None

    _closed_error_message: ClassVar[str] = "sqlite unit of work is not active"

    def __enter__(self) -> Self:
        if self._connection is not None:
            return self

        self._connection = open_sqlite_connection(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )
        self._committed = False
        try:
            self._connection.execute(
                "BEGIN IMMEDIATE" if self.write_transaction else "BEGIN"
            )
            self._memory_spaces = SQLiteMemorySpaceRepository(self._connection)
            self._raw_rounds = SQLiteRawRoundRepository(self._connection)
            return self
        except Exception:
            self._disconnect()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                if not self._committed:
                    self.rollback()
            else:
                self.rollback()
        finally:
            self._disconnect()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise SQLiteUnitOfWorkInactiveError(self._closed_error_message)
        return self._connection



    @property
    def memory_spaces(self) -> SQLiteMemorySpaceRepository:
        if self._memory_spaces is None:
            raise SQLiteUnitOfWorkInactiveError(self._closed_error_message)
        return self._memory_spaces

    @property
    def raw_rounds(self) -> SQLiteRawRoundRepository:
        if self._raw_rounds is None:
            raise SQLiteUnitOfWorkInactiveError(self._closed_error_message)
        return self._raw_rounds

    def commit(self) -> None:
        if self._connection is None:
            raise SQLiteUnitOfWorkInactiveError(self._closed_error_message)
        if self._committed:
            raise SQLiteUnitOfWorkError("commit already called")

        self._connection.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._connection is None:
            return
        if self._committed:
            return
        self._connection.rollback()

    def _disconnect(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
        finally:
            self._connection = None
            self._committed = False
            self._memory_spaces = None
            self._raw_rounds = None
