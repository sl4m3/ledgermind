"""Hermes-facing on-demand runtime lease."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from .client import LedgerMindClient, LedgerMindNetworkError

logger = logging.getLogger(__name__)

RUNTIME_BOOTSTRAP_TIMEOUT_SECONDS = 45.0


@dataclass(slots=True)
class RuntimeLease:
    client: LedgerMindClient
    lease_id: str
    heartbeat_seconds: float = 10.0
    _stop: threading.Event = field(init=False, repr=False)
    _thread: threading.Thread | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._stop = threading.Event()

    @classmethod
    def acquire(
        cls,
        client: LedgerMindClient,
        *,
        client_id: str,
        session_id: str,
        heartbeat_seconds: float,
        bootstrap_command: str | Sequence[str] | None = None,
        ttl_seconds: float | None = None,
        start_heartbeat: bool = True,
    ) -> RuntimeLease:
        try:
            response = client.runtime_acquire(
                client=client_id,
                session_id=session_id,
                ttl_seconds=ttl_seconds,
            )
        except LedgerMindNetworkError:
            response = _bootstrap_runtime(
                client,
                client_id=client_id,
                session_id=session_id,
                command=bootstrap_command,
                ttl_seconds=ttl_seconds,
            )
        lease_id = response.get("lease_id")
        if not isinstance(lease_id, str) or not lease_id:
            raise RuntimeError("runtime acquire returned no lease_id")
        lease = cls(client, lease_id, max(float(heartbeat_seconds), 0.1))
        if start_heartbeat:
            lease.start()
        return lease

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ledgermind-hermes-lease",
            daemon=True,
        )
        self._thread.start()

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.heartbeat_seconds + 1.0)
        self._thread = None
        try:
            self.client.runtime_release(self.lease_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("runtime lease release failed: %s", type(exc).__name__)

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self.client.runtime_heartbeat(self.lease_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("runtime lease heartbeat failed: %s", type(exc).__name__)


__all__ = ["RuntimeLease"]


def _bootstrap_runtime(
    client: LedgerMindClient,
    *,
    client_id: str,
    session_id: str,
    command: str | Sequence[str] | None,
    ttl_seconds: float | None = None,
) -> dict[str, object]:
    if command is None:
        raise RuntimeError("LedgerMind runtime is unavailable")
    parts = shlex.split(command) if isinstance(command, str) else [str(item) for item in command]
    if not parts:
        raise RuntimeError("LedgerMind runtime bootstrap command is empty")
    parts[0] = os.path.expanduser(parts[0])
    try:
        arguments = [
            *parts,
            "runtime",
            "acquire",
            "--client",
            client_id,
            "--session-id",
            session_id,
        ]
        if ttl_seconds is not None:
            arguments.extend(("--ttl-seconds", str(float(ttl_seconds))))
        arguments.append("--json")
        completed = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            # A cold secure-runtime start verifies the signed Core and waits
            # for Local readiness.  Killing the supervisor after the normal
            # HTTP request timeout leaves its detached child untracked.
            timeout=max(client.timeout, RUNTIME_BOOTSTRAP_TIMEOUT_SECONDS),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("LedgerMind runtime bootstrap failed") from exc
    if completed.returncode != 0:
        raise RuntimeError("LedgerMind runtime bootstrap failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LedgerMind runtime bootstrap returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("LedgerMind runtime bootstrap returned an invalid result")
    runtime = payload.get("runtime")
    result = runtime if isinstance(runtime, dict) else payload
    lease_id = result.get("lease_id")

    def rollback() -> None:
        if not isinstance(lease_id, str) or not lease_id:
            return
        try:
            subprocess.run(
                [
                    *parts,
                    "runtime",
                    "release",
                    "--lease-id",
                    lease_id,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=max(client.timeout, 5.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            logger.debug("runtime bootstrap lease rollback failed")

    endpoint = result.get("endpoint")
    if isinstance(endpoint, str) and endpoint:
        client.endpoint = endpoint.rstrip("/")
        deadline = time.monotonic() + max(client.timeout, 5.0)
        ready = False
        while time.monotonic() < deadline:
            try:
                client.health_live()
                ready = True
                break
            except LedgerMindNetworkError:
                time.sleep(0.1)
        if not ready:
            rollback()
            raise RuntimeError("LedgerMind runtime did not become ready")
    return dict(result)
