"""Concurrency checks for service lock implementation."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


def _write_lock_runner_script(root: Path) -> Path:
    script = root / "lock_runner.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            import time
            from pathlib import Path

            from ledgermind_local.service_lock import ServiceLock, ServiceLockError

            lock = Path(sys.argv[1])
            hold = float(sys.argv[2])
            try:
                with ServiceLock(lock_path=lock):
                    print("acquired", flush=True)
                    time.sleep(hold)
            except ServiceLockError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(2)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return script


def _run_runner(
    script: Path, lock: Path, hold_seconds: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), str(lock), str(hold_seconds)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_first_process_acquires_service_lock(tmp_path: Path) -> None:
    lock = tmp_path / "service.lock"
    script = _write_lock_runner_script(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, str(script), str(lock), "0.4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        line = proc.stdout.readline() if proc.stdout else ""
        assert line.strip() == "acquired"
    finally:
        proc.wait(timeout=2.0)

    assert proc.returncode == 0
    assert (proc.stderr.read() if proc.stderr else "") == ""
    assert not lock.exists()


def test_second_process_rejects_locked_service(tmp_path: Path) -> None:
    lock = tmp_path / "service.lock"
    script = _write_lock_runner_script(tmp_path)
    proc1 = subprocess.Popen(
        [sys.executable, str(script), str(lock), "1.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        first_line = proc1.stdout.readline().strip() if proc1.stdout else ""
        assert first_line == "acquired"
        proc2 = _run_runner(script, lock, 0.0)
        assert proc2.returncode == 2
        assert "already running" in proc2.stderr.lower()
    finally:
        proc1.wait(timeout=2.0)


def test_second_process_acquires_after_first_released(tmp_path: Path) -> None:
    lock = tmp_path / "service.lock"
    script = _write_lock_runner_script(tmp_path)
    proc1 = subprocess.Popen(
        [sys.executable, str(script), str(lock), "0.2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc1.wait(timeout=2.0)
    assert proc1.returncode == 0
    assert (proc1.stderr.read() if proc1.stderr else "") == ""

    proc2 = _run_runner(script, lock, 0.0)
    assert proc2.returncode == 0
    assert proc2.stdout.strip() == "acquired"


def test_stale_pid_lock_can_be_cleaned(tmp_path: Path) -> None:
    lock = tmp_path / "service.lock"
    lock.write_text(
        json.dumps({"version": 1, "pid": 999_999}, ensure_ascii=False),
        encoding="utf-8",
    )
    script = _write_lock_runner_script(tmp_path)
    proc = _run_runner(script, lock, 0.0)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "acquired"


def test_corrupt_lock_payload_is_treated_as_stale(tmp_path: Path) -> None:
    lock = tmp_path / "service.lock"
    lock.write_text("{}", encoding="utf-8")
    script = _write_lock_runner_script(tmp_path)
    proc = _run_runner(script, lock, 0.0)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "acquired"
