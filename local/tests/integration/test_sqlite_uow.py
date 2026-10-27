"""Integration tests for `SQLiteUnitOfWork`."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ledgermind_local.persistence.sqlite_uow import (
    SQLiteUnitOfWork,
    SQLiteUnitOfWorkError,
    SQLiteUnitOfWorkInactiveError,
)

PROJECT_SRC = str(Path(__file__).resolve().parents[2] / "src")


def _runner_env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": (
            f"{PROJECT_SRC}{os.pathsep}{os.getenv('PYTHONPATH')}"
            if os.getenv("PYTHONPATH")
            else PROJECT_SRC
        ),
    }


def test_uow_rolls_back_without_explicit_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with SQLiteUnitOfWork(db_path) as uow:
        uow.connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, v TEXT)")
        uow.connection.execute("INSERT INTO sample (v) VALUES ('a')")
        assert uow.connection.in_transaction

    import sqlite3

    conn = sqlite3.connect(db_path)
    values = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sample'"
    ).fetchone()
    conn.close()
    assert values is None


def test_uow_commit_is_required_and_commit_twice_is_forbidden(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with SQLiteUnitOfWork(db_path) as uow:
        uow.connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, v TEXT)")
        uow.connection.execute("INSERT INTO sample (v) VALUES ('a')")
        uow.commit()

        with pytest.raises(SQLiteUnitOfWorkError):
            uow.commit()

    import sqlite3

    conn = sqlite3.connect(db_path)
    values = conn.execute("SELECT COUNT(*) AS total FROM sample").fetchone()[0]
    conn.close()
    assert values == 1


def test_uow_rollback_on_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"

    with pytest.raises(RuntimeError), SQLiteUnitOfWork(db_path) as uow:
        uow.connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, v TEXT)")
        uow.connection.execute("INSERT INTO sample (v) VALUES ('a')")
        raise RuntimeError("boom")

    import sqlite3

    conn = sqlite3.connect(db_path)
    values = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sample'"
    ).fetchone()
    conn.close()
    assert values is None


def test_connection_is_closed_after_context_exit(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    uow = SQLiteUnitOfWork(db_path)
    with uow:
        uow.connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

    with pytest.raises(SQLiteUnitOfWorkInactiveError):
        _ = uow.connection


def _write_uow_script(root: Path) -> Path:
    script = root / "uow_writer.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            import time
            from pathlib import Path

            from ledgermind_local.persistence.sqlite_uow import SQLiteUnitOfWork

            database = Path(sys.argv[1])
            hold = float(sys.argv[2])
            payload = sys.argv[3]

            with SQLiteUnitOfWork(database) as uow:
                uow.connection.execute(
                    "CREATE TABLE IF NOT EXISTS workers (id INTEGER PRIMARY KEY, payload TEXT)"
                )
                uow.connection.execute(
                    "INSERT INTO workers (payload) VALUES (?)",
                    (payload,),
                )
                time.sleep(hold)
                uow.commit()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def _run_uow_script(
    script: Path, db_path: Path, hold: float, payload: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(script),
            str(db_path),
            str(hold),
            payload,
        ],
        capture_output=True,
        check=False,
        text=True,
        env=_runner_env(),
    )


def test_parallel_processes_do_not_corrupt_sqlite_db(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    script = _write_uow_script(tmp_path)

    proc1 = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(db_path),
            "1.0",
            "first",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_runner_env(),
    )
    time.sleep(0.1)
    proc2 = _run_uow_script(script, db_path, 0.0, "second")

    proc1.wait(timeout=8.0)
    assert proc1.returncode == 0
    assert proc2.returncode == 0

    import sqlite3

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) AS total FROM workers").fetchone()[0]
    conn.close()
    assert count == 2
