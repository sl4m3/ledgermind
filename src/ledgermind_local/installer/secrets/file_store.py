"""0600 JSON fallback secret store."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..permissions import assert_private, ensure_private_dir


class FileSecretStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def available(self) -> bool:
        return True

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        assert_private(self.path, directory=False)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        secrets = payload.get("secrets") if isinstance(payload, dict) else None
        if not isinstance(secrets, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in secrets.items()
        ):
            raise ValueError("secret store has invalid format")
        return dict(secrets)

    def _write(self, values: dict[str, str]) -> None:
        ensure_private_dir(self.path.parent)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                json.dump(
                    {"secrets": values}, handle, sort_keys=True, separators=(",", ":")
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
            os.chmod(self.path, 0o600)
            assert_private(self.path, directory=False)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, key: str) -> str | None:
        return self._load().get(key)

    def put(self, key: str, value: str) -> None:
        if not key or not value:
            raise ValueError("secret key and value must not be empty")
        values = self._load()
        values[key] = value
        self._write(values)

    def delete(self, key: str) -> bool:
        values = self._load()
        if key not in values:
            return False
        del values[key]
        self._write(values)
        return True

    def list_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._load()))


__all__ = ["FileSecretStore"]
