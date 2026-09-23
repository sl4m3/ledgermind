"""Retry worker that sends only validated RawRound request envelopes."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol

from .client import LedgerMindClientError, LedgerMindConflictError
from .spool import FileSpool


class RoundSubmitter(Protocol):
    def submit_round(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...


class DeliveryWorker:
    def __init__(
        self,
        spool: FileSpool,
        client: RoundSubmitter,
        *,
        max_attempts: int | None = None,
        base_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        self.spool = spool
        self.client = client
        self.max_attempts = None if max_attempts is None else max(int(max_attempts), 1)
        self.base_backoff_seconds = max(float(base_backoff_seconds), 0.01)
        self.max_backoff_seconds = max(float(max_backoff_seconds), self.base_backoff_seconds)

    def run_once(self, limit: int = 10) -> bool:
        processed = False
        for item_name, envelope in self.spool.pop_ready(limit):
            processed = True
            self._process(item_name, envelope)
        return processed

    def _process(self, item_name: str, envelope: Mapping[str, Any]) -> None:
        request = envelope.get("request")
        if not isinstance(request, Mapping):
            self.spool.fail(item_name, "invalid_request_envelope")
            return
        delivery = dict(envelope.get("delivery", {}))
        attempts = int(delivery.get("attempts", 0)) + 1
        delivery["attempts"] = attempts
        mutable = {"request": dict(request), "delivery": delivery}
        if self.max_attempts is not None and attempts > self.max_attempts:
            self.spool.fail(item_name, "max_attempts_exceeded")
            return
        try:
            response = self.client.submit_round(request)
            if response.get("status") != "accepted" and response.get("accepted") is not True:
                raise LedgerMindClientError("round acceptance was not confirmed")
        except LedgerMindConflictError:
            self.spool.fail(item_name, "source_round_conflict")
        except Exception:  # noqa: BLE001 - preserve uncertain deliveries, including malformed acknowledgements
            delay = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** min(attempts - 1, 16)))
            delivery["next_attempt_at"] = time.time() + delay
            self.spool.retry(item_name, mutable)
        else:
            self.spool.complete(item_name)
