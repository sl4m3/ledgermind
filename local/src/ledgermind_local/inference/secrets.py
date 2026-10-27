"""Private, atomic storage for Local provider secrets."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_SECRET_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")


class SecretNotFoundError(KeyError):
    """Raised when a configured secret reference is not present."""


class SecretStoreFormatError(RuntimeError):
    """Raised when the private secret store has an invalid structure."""


class SecretStore:
    """Store provider values by reference without exposing them in diagnostics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def __repr__(self) -> str:
        return f"SecretStore(path={str(self.path)!r})"

    @staticmethod
    def _validate_ref(secret_ref: str) -> str:
        if not isinstance(secret_ref, str) or not _SECRET_REF_RE.fullmatch(secret_ref):
            raise ValueError("secret_ref must contain only safe identifier characters")
        return secret_ref

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("secret store cannot be read") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("secrets"), dict
        ):
            raise SecretStoreFormatError("secret store has invalid format")
        secrets = payload["secrets"]
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in secrets.items()
        ):
            raise SecretStoreFormatError("secret store has invalid format")
        return dict(secrets)

    def _write(self, secrets: dict[str, str]) -> None:
        parent = self.path.parent
        temporary: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(parent, 0o700)
            payload: dict[str, Any] = {"secrets": secrets}
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                os.chmod(temporary, 0o600)
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
            os.chmod(self.path, 0o600)
        except OSError as exc:
            raise RuntimeError("secret store cannot be written") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, secret_ref: str) -> str:
        ref = self._validate_ref(secret_ref)
        secrets = self._load()
        try:
            return secrets[ref]
        except KeyError as exc:
            raise SecretNotFoundError(f"secret ref '{ref}' not found") from exc

    def put(self, secret_ref: str, value: str) -> None:
        ref = self._validate_ref(secret_ref)
        if not isinstance(value, str) or not value:
            raise ValueError("secret value must not be empty")
        secrets = self._load()
        secrets[ref] = value
        self._write(secrets)

    def delete(self, secret_ref: str) -> bool:
        ref = self._validate_ref(secret_ref)
        secrets = self._load()
        if ref not in secrets:
            return False
        del secrets[ref]
        self._write(secrets)
        return True

    def list_refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._load()))


__all__ = ["SecretNotFoundError", "SecretStore"]
