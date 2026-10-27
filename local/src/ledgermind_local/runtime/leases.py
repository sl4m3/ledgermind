"""Persistent TTL leases for Hermes and future agent clients."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _now() -> float:
    return time.time()


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class Lease:
    lease_id: str
    client: str
    session_id: str
    created_at: float
    expires_at: float
    ttl_seconds: float

    def as_dict(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "client": self.client,
            "session_id": self.session_id,
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
            "ttl_seconds": self.ttl_seconds,
        }


class LeaseStore:
    def __init__(self, directory: str | Path, *, ttl_seconds: float = 30.0) -> None:
        self.directory = Path(directory).expanduser()
        self.ttl_seconds = max(float(ttl_seconds), 0.1)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)

    def _path(self, lease_id: str) -> Path:
        if not lease_id or Path(lease_id).name != lease_id:
            raise ValueError("invalid lease id")
        return self.directory / f"{lease_id}.json"

    def _read(self, path: Path) -> Lease | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return Lease(
                lease_id=str(payload["lease_id"]),
                client=str(payload["client"]),
                session_id=str(payload["session_id"]),
                created_at=float(payload["created_at_epoch"]),
                expires_at=float(payload["expires_at_epoch"]),
                ttl_seconds=float(payload.get("ttl_seconds", self.ttl_seconds)),
            )
        except (OSError, ValueError, KeyError, TypeError):
            path.unlink(missing_ok=True)
            return None

    def _write(self, lease: Lease) -> None:
        payload = {
            **lease.as_dict(),
            "created_at_epoch": lease.created_at,
            "expires_at_epoch": lease.expires_at,
        }
        path = self._path(lease.lease_id)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def reap_expired(self, *, now: float | None = None) -> tuple[str, ...]:
        current = _now() if now is None else now
        expired: list[str] = []
        for path in self.directory.glob("lease-*.json"):
            lease = self._read(path)
            if lease is None:
                continue
            if lease.expires_at <= current:
                path.unlink(missing_ok=True)
                expired.append(lease.lease_id)
        return tuple(sorted(expired))

    def acquire(
        self, *, client: str, session_id: str, ttl_seconds: float | None = None
    ) -> Lease:
        client = client.strip()
        session_id = session_id.strip()
        if not client or not session_id:
            raise ValueError("client and session_id are required")
        now = _now()
        effective_ttl = (
            self.ttl_seconds
            if ttl_seconds is None
            else max(float(ttl_seconds), self.ttl_seconds)
        )
        matching = [
            lease
            for lease in self.active()
            if lease.client == client and lease.session_id == session_id
        ]
        if matching:
            # Acquisition is idempotent for one logical agent session.  Hook
            # retries and concurrent lifecycle events must refresh the same
            # lease instead of keeping the runtime alive with duplicates.
            canonical = min(matching, key=lambda item: (item.created_at, item.lease_id))
            for duplicate in matching:
                if duplicate.lease_id != canonical.lease_id:
                    self.release(duplicate.lease_id)
            refreshed_ttl = max(effective_ttl, canonical.ttl_seconds)
            refreshed = Lease(
                canonical.lease_id,
                canonical.client,
                canonical.session_id,
                canonical.created_at,
                now + refreshed_ttl,
                refreshed_ttl,
            )
            self._write(refreshed)
            return refreshed
        lease = Lease(
            f"lease-{uuid4().hex}",
            client,
            session_id,
            now,
            now + effective_ttl,
            effective_ttl,
        )
        self._write(lease)
        return lease

    def heartbeat(self, lease_id: str) -> Lease:
        path = self._path(lease_id)
        lease = self._read(path)
        if lease is None:
            raise KeyError(f"lease not found: {lease_id}")
        now = _now()
        if lease.expires_at <= now:
            path.unlink(missing_ok=True)
            raise KeyError(f"lease expired: {lease_id}")
        refreshed = Lease(
            lease.lease_id,
            lease.client,
            lease.session_id,
            lease.created_at,
            now + lease.ttl_seconds,
            lease.ttl_seconds,
        )
        self._write(refreshed)
        return refreshed

    def release(self, lease_id: str) -> bool:
        path = self._path(lease_id)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def active(self) -> tuple[Lease, ...]:
        self.reap_expired()
        leases = [
            lease
            for path in self.directory.glob("lease-*.json")
            if (lease := self._read(path))
        ]
        return tuple(sorted(leases, key=lambda lease: lease.lease_id))


__all__ = ["Lease", "LeaseStore"]
