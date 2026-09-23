"""Private, atomic filesystem queues for Hermes capture and delivery."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


class SpoolFullError(RuntimeError):
    """The configured queue byte or file limit would be exceeded."""


class SpoolPermissionError(RuntimeError):
    """The spool cannot be created or kept private."""


@dataclass(frozen=True, slots=True)
class SpoolStats:
    pending_capture: int
    ready_delivery: int
    inflight: int
    failed: int


class FileSpool:
    def __init__(
        self,
        root: str | Path,
        *,
        max_payload_bytes: int = 5_000_000,
        max_bytes: int = 50_000_000,
        max_files: int = 1_000,
        inflight_ttl_seconds: float = 300.0,
        worker_id: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser()
        self.pending_dir = self.root / "pending-capture"
        self.ready_dir = self.root / "ready-delivery"
        self.inflight_dir = self.root / "inflight"
        self.failed_dir = self.root / "failed"
        self.max_payload_bytes = max(int(max_payload_bytes), 1)
        self.max_bytes = max(int(max_bytes), 1)
        self.max_files = max(int(max_files), 1)
        self.inflight_ttl_seconds = max(float(inflight_ttl_seconds), 0.1)
        self.worker_id = worker_id or f"worker-{uuid4().hex}"
        self.delivery_status_path = self.root / "delivery-status.json"

    def _ensure(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.root.chmod(0o700)
            for directory in (
                self.pending_dir,
                self.ready_dir,
                self.inflight_dir,
                self.failed_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                directory.chmod(0o700)
        except OSError as exc:
            raise SpoolPermissionError("cannot create private spool directories") from exc

    @staticmethod
    def _encode(payload: Mapping[str, Any]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _payload_size(cls, payload: Mapping[str, Any]) -> int:
        request = payload.get("request")
        if isinstance(request, Mapping):
            return len(cls._encode(request))
        return len(cls._encode(payload))

    def _check_limits(
        self,
        destination: Path,
        size: int,
        *,
        exclude: Sequence[Path] = (),
    ) -> None:
        queue_dirs = (self.pending_dir, self.ready_dir, self.inflight_dir)
        excluded = set(exclude)
        files = [
            path
            for directory in queue_dirs
            for path in directory.glob("*.json")
            if path not in excluded
        ]
        current_size = 0
        for path in files:
            try:
                current_size += path.stat().st_size
            except OSError:
                continue
        replacing = destination.exists()
        if replacing:
            try:
                current_size -= destination.stat().st_size
            except OSError:
                pass
        current_files = len(files) - int(replacing)
        if replacing or any(source.exists() for source in excluded):
            # Claim/retry/promotion updates an existing durable item, not a
            # new round. Metadata growth at a full queue must not strand it.
            return
        if current_files + 1 > self.max_files:
            raise SpoolFullError("spool file limit exceeded")
        if current_size + size > self.max_bytes:
            raise SpoolFullError("spool byte limit exceeded")

    def _write(
        self,
        destination: Path,
        payload: Mapping[str, Any],
        *,
        exclude: Sequence[Path] = (),
    ) -> Path:
        self._ensure()
        encoded = self._encode(payload)
        if self._payload_size(payload) > self.max_payload_bytes:
            raise SpoolFullError("payload byte limit exceeded")
        self._check_limits(destination, len(encoded), exclude=exclude)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as handle:
                temporary.chmod(0o600)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
            destination.chmod(0o600)
        except PermissionError as exc:
            temporary.unlink(missing_ok=True)
            raise SpoolPermissionError("cannot write private spool file") from exc
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    @staticmethod
    def _copy(payload: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(dict(payload), ensure_ascii=False)))

    @staticmethod
    def _safe_key(key: str) -> str:
        cleaned = "".join(
            character if character.isalnum() or character in "._-:" else "_"
            for character in str(key)
        )
        if cleaned in {"", ".", ".."}:
            return f"item-{uuid4().hex}"
        return cleaned[:200]

    def enqueue_pending(self, key: str, payload: Mapping[str, Any]) -> Path:
        pending = self._copy(payload)
        pending["delivery"] = {"attempts": 0, "next_attempt_at": 0.0}
        return self._write(self.pending_dir / f"{self._safe_key(key)}.json", pending)

    def enqueue_ready(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        exclude: Sequence[Path] = (),
    ) -> Path:
        envelope = {
            "request": self._copy(payload),
            "delivery": {"attempts": 0, "next_attempt_at": 0.0},
        }
        return self._write(
            self.ready_dir / f"{self._safe_key(key)}.json",
            envelope,
            exclude=exclude,
        )

    def pop_pending(self, limit: int = 10) -> list[tuple[str, dict[str, Any]]]:
        self._ensure()
        now = time.time()
        due_items: list[tuple[float, Path, dict[str, Any]]] = []
        for path in self.pending_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.fail_pending(path.name, "invalid_json")
                continue
            if not isinstance(payload, dict):
                self.fail_pending(path.name, "invalid_payload")
                continue
            delivery = payload.get("delivery")
            next_attempt_at: float
            if isinstance(delivery, Mapping):
                try:
                    next_attempt_at = float(delivery.get("next_attempt_at", 0.0))
                except (TypeError, ValueError):
                    next_attempt_at = 0.0
            else:
                next_attempt_at = 0.0
            if next_attempt_at <= now:
                due_items.append((next_attempt_at, path, payload))
        due_items.sort(key=lambda item: (item[0], item[1].name))
        return [
            (path.name, payload)
            for _, path, payload in due_items[: max(int(limit), 1)]
        ]

    def retry_pending(self, item_name: str, payload: Mapping[str, Any]) -> None:
        self._write(self.pending_dir / item_name, self._copy(payload))

    def complete_pending(self, item_name: str) -> None:
        (self.pending_dir / item_name).unlink(missing_ok=True)

    def fail_pending(self, item_name: str, reason: str) -> Path:
        source = self.pending_dir / item_name
        payload: dict[str, Any] = {"failure_reason": reason}
        if source.exists():
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    payload = {**raw, "failure_reason": reason}
            except (OSError, json.JSONDecodeError):
                pass
        target_path = self._write(
            self.failed_dir / f"pending-{item_name}",
            payload,
            exclude=(source,),
        )
        source.unlink(missing_ok=True)
        return target_path

    def _reclaim_expired_inflight(self) -> None:
        self._ensure()
        now = time.time()
        for path in sorted(self.inflight_dir.glob("*.json")):
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.fail_inflight(path.name, "invalid_json")
                continue
            if not isinstance(envelope, dict):
                self.fail_inflight(path.name, "invalid_envelope")
                continue
            delivery = envelope.get("delivery")
            claimed_at = delivery.get("claimed_at") if isinstance(delivery, dict) else None
            try:
                expired = claimed_at is None or now - float(claimed_at) >= self.inflight_ttl_seconds
            except (TypeError, ValueError):
                expired = True
            if not expired:
                continue
            if isinstance(delivery, dict):
                delivery.pop("worker_id", None)
                delivery.pop("claimed_at", None)
                delivery["next_attempt_at"] = 0.0
            self._write(self.ready_dir / path.name, envelope, exclude=(path,))
            path.unlink(missing_ok=True)

    def pop_ready(self, limit: int = 10) -> list[tuple[str, dict[str, Any]]]:
        self._reclaim_expired_inflight()
        result: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(self.ready_dir.glob("*.json")):
            if len(result) >= max(int(limit), 1):
                break
            claimed = self.inflight_dir / path.name
            try:
                path.replace(claimed)
                payload = json.loads(claimed.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                self.fail_inflight(path.name, "invalid_json")
                continue
            if not isinstance(payload, dict):
                self.fail_inflight(path.name, "invalid_envelope")
                continue
            delivery = payload.get("delivery")
            if not isinstance(delivery, dict):
                delivery = {}
                payload["delivery"] = delivery
            try:
                due = float(delivery.get("next_attempt_at", 0.0)) <= time.time()
            except (TypeError, ValueError):
                due = True
            if not due:
                self._write(self.ready_dir / path.name, payload, exclude=(claimed,))
                claimed.unlink(missing_ok=True)
                continue
            delivery["worker_id"] = self.worker_id
            delivery["claimed_at"] = time.time()
            self._write(claimed, payload)
            result.append((path.name, payload))
        return result

    def complete(self, item_name: str) -> None:
        (self.inflight_dir / item_name).unlink(missing_ok=True)

    def retry(self, item_name: str, payload: Mapping[str, Any]) -> None:
        self._write(
            self.ready_dir / item_name,
            self._copy(payload),
            exclude=(self.inflight_dir / item_name,),
        )
        (self.inflight_dir / item_name).unlink(missing_ok=True)

    def fail_inflight(self, item_name: str, reason: str) -> Path:
        source = self.inflight_dir / item_name
        if not source.exists():
            source = self.ready_dir / item_name
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"delivery": {}}
        if not isinstance(payload, dict):
            payload = {"delivery": {}}
        delivery = payload.get("delivery")
        if not isinstance(delivery, dict):
            delivery = {}
        delivery["failure_reason"] = reason
        payload["delivery"] = delivery
        target = self._write(self.failed_dir / item_name, payload, exclude=(source,))
        source.unlink(missing_ok=True)
        return target

    def fail(self, item_name: str, reason: str) -> Path:
        return self.fail_inflight(item_name, reason)

    def stats(self) -> SpoolStats:
        self._ensure()
        return SpoolStats(
            pending_capture=len(list(self.pending_dir.glob("*.json"))),
            ready_delivery=len(list(self.ready_dir.glob("*.json"))),
            inflight=len(list(self.inflight_dir.glob("*.json"))),
            failed=len(list(self.failed_dir.glob("*.json"))),
        )

    def note_delivery_failure(self, reason: str) -> None:
        """Persist a content-free operational diagnostic beside the durable queue."""

        safe_reason = self._safe_key(str(reason).split(":", 1)[0])[:120]
        self._write(
            self.delivery_status_path,
            {"status": "pending", "reason": safe_reason, "updated_at": time.time()},
        )

    def clear_delivery_failure(self) -> None:
        self.delivery_status_path.unlink(missing_ok=True)


__all__ = [
    "FileSpool",
    "SpoolFullError",
    "SpoolPermissionError",
    "SpoolStats",
]
