"""User-scoped operation lock."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TextIO

from .errors import TransactionError


class InstallerLock:
    def __init__(self, path: str | Path, *, timeout_seconds: float = 30.0) -> None:
        self.path = Path(path).expanduser()
        self.timeout_seconds = max(float(timeout_seconds), 0.0)
        self._handle: TextIO | None = None

    def __enter__(self) -> InstallerLock:  # noqa: PYI034
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - first release is Linux only
            raise TransactionError("user lock is unsupported on this platform") from exc
        handle = self.path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                handle.write(f"pid={os.getpid()}\n")
                handle.flush()
                os.fchmod(handle.fileno(), 0o600)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TransactionError(
                        f"another LedgerMind operation holds {self.path}"
                    )
                time.sleep(0.05)
            except OSError as exc:
                handle.close()
                raise TransactionError(
                    f"cannot acquire installer lock: {self.path}"
                ) from exc

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._handle is None:
            return
        import fcntl

        handle = self._handle
        self._handle = None
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


__all__ = ["InstallerLock"]
