"""Single-owner process lock for the local service."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import cast

from typing_extensions import Self


class ServiceLockError(RuntimeError):
    """Raised when lock cannot be acquired."""


@dataclass(slots=True)
class ServiceLock:
    lock_path: Path
    force_stale_cleanup: bool = True
    _locked: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.lock_path = Path(self.lock_path)

    def acquire(self) -> None:
        if self._locked:
            return

        while True:
            try:
                self._try_create_lock()
                self._locked = True
                return
            except ServiceLockError:
                if not self.force_stale_cleanup:
                    raise
                if not self._maybe_cleanup_stale_lock():
                    raise

    def _try_create_lock(self) -> None:
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {"version": 1, "pid": os.getpid()},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            # Use O_EXCL + O_CREAT for atomic ownership.
            fd = os.open(
                self.lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(fd, payload.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            return
        except FileExistsError:
            raise ServiceLockError("service is already running")
        except OSError as error:
            raise ServiceLockError(f"unable to create lock: {error}") from error

    def _read_lock_payload(self) -> dict[str, object]:
        raw = self.lock_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise TypeError("invalid lock payload")
        return payload

    def _is_running_pid(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _maybe_cleanup_stale_lock(self) -> bool:
        if not self.lock_path.exists():
            return True

        try:
            payload = self._read_lock_payload()
            candidate_pid = int(cast(str, payload.get("pid", 0)))
        except Exception:  # noqa: BLE001
            candidate_pid = 0

        if candidate_pid == 0 or not self._is_running_pid(candidate_pid):
            self.lock_path.unlink(missing_ok=True)
            return True

        return False

    def release(self) -> None:
        if not self._locked:
            return
        self.lock_path.unlink(missing_ok=True)
        self._locked = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
