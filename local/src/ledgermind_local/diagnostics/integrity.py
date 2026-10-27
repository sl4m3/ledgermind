"""SQLite integrity diagnostics for the Local-owned rounds database."""

from __future__ import annotations

import sqlite3


def _check_integrity_pragma(connection: sqlite3.Connection) -> list[str]:
    rows = list(connection.execute("PRAGMA integrity_check").fetchall())
    if len(rows) != 1 or str(rows[0][0]) != "ok":
        details = ", ".join(str(row[0]) for row in rows)
        return [f"integrity_check failed: {details}"]
    return []


def _check_foreign_key_pragma(connection: sqlite3.Connection) -> list[str]:
    rows = list(connection.execute("PRAGMA foreign_key_check").fetchall())
    if not rows:
        return []
    details = ", ".join(
        f"{row[0]}.{row[1]}: missing parent {row[2]}({row[3]})" for row in rows
    )
    return [f"foreign_key_check failed: {details}"]


def run_database_integrity_checks(connection: sqlite3.Connection) -> list[str]:
    """Run integrity checks valid for the Local-owned SQLite database."""

    return _check_integrity_pragma(connection) + _check_foreign_key_pragma(connection)


def run_rounds_integrity_checks(connection: sqlite3.Connection) -> list[str]:
    """Run checks for Local's ``rounds.db``."""

    return run_database_integrity_checks(connection)


__all__ = ["run_database_integrity_checks", "run_rounds_integrity_checks"]
