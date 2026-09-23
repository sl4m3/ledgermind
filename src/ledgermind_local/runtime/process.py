"""Managed child processes for on-demand Local/Core services."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


def process_start_ticks(pid: int) -> int | None:
    """Read the Linux process birth tick so a recycled PID is not trusted."""

    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return int(stat.rsplit(") ", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


@dataclass(slots=True)
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen[bytes]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "pid": self.process.pid,
            "command": list(self.command),
            "start_ticks": process_start_ticks(self.process.pid),
        }


class ProcessManager:
    def __init__(
        self, *, environment_overrides: Mapping[str, str] | None = None
    ) -> None:
        self.processes: dict[str, ManagedProcess] = {}
        self._environment_overrides = dict(environment_overrides or {})

    def start(self, commands: dict[str, Sequence[str]]) -> dict[str, ManagedProcess]:
        for name, command in commands.items():
            if not command or name in self.processes:
                continue
            process = subprocess.Popen(
                [str(part) for part in command],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                env=_clean_environment(self._environment_overrides),
            )
            self.processes[name] = ManagedProcess(
                name, tuple(str(part) for part in command), process
            )
        return dict(self.processes)

    def running(self) -> dict[str, ManagedProcess]:
        dead = [
            name
            for name, item in self.processes.items()
            if item.process.poll() is not None
        ]
        for name in dead:
            self.processes.pop(name, None)
        return dict(self.processes)

    def stop(self, *, timeout_seconds: float = 5.0) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        for name, item in list(self.processes.items())[::-1]:
            if item.process.poll() is None:
                item.process.terminate()
                try:
                    item.process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    item.process.kill()
                    item.process.wait(timeout=timeout_seconds)
            result[name] = item.process.returncode
            self.processes.pop(name, None)
        return result

    @staticmethod
    def stop_external(
        records: dict[str, object], *, timeout_seconds: float = 5.0
    ) -> dict[str, int | None]:
        """Stop processes recorded by a previous supervisor instance."""

        result: dict[str, int | None] = {}
        for name, raw in records.items():
            if not isinstance(raw, dict):
                continue
            try:
                pid = int(raw["pid"])
                os.kill(pid, 0)
            except (
                KeyError,
                TypeError,
                ValueError,
                ProcessLookupError,
                PermissionError,
                OSError,
            ):
                result[name] = None
                continue
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                result[name] = None
                continue
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                except PermissionError:
                    break
                time.sleep(0.05)
            try:
                os.kill(pid, 0)
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                result[name] = None
            result[name] = None
        return result


def _clean_environment(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name in (
        "PATH",
        "LANG",
        "LC_ALL",
        "HOME",
        "USER",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "PYTHONPATH",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if overrides:
        environment.update(
            {
                str(name): str(value)
                for name, value in overrides.items()
                if str(name) and str(value)
            }
        )
    return environment


__all__ = ["ManagedProcess", "ProcessManager"]
