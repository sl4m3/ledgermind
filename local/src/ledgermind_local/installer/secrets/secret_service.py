"""Best-effort Secret Service backend using the system ``secret-tool`` CLI."""

from __future__ import annotations

import os
import shutil
import subprocess


class SecretServiceStore:
    def __init__(self, *, application: str = "ledgermind") -> None:
        self.application = application

    def available(self) -> bool:
        return bool(
            os.environ.get("DBUS_SESSION_BUS_ADDRESS") and shutil.which("secret-tool")
        )

    def get(self, key: str) -> str | None:
        if not self.available():
            return None
        try:
            result = subprocess.run(
                ["secret-tool", "lookup", "application", self.application, "key", key],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() or None if result.returncode == 0 else None

    def put(self, key: str, value: str) -> None:
        if not self.available():
            raise RuntimeError("Secret Service is unavailable")
        subprocess.run(
            [
                "secret-tool",
                "store",
                "--label",
                f"LedgerMind {key}",
                "application",
                self.application,
                "key",
                key,
            ],
            input=value,
            text=True,
            check=True,
            timeout=5,
        )

    def delete(self, key: str) -> bool:
        if not self.available():
            return False
        result = subprocess.run(
            ["secret-tool", "clear", "application", self.application, "key", key],
            check=False,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0


__all__ = ["SecretServiceStore"]
