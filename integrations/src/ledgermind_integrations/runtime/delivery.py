"""Retry worker that sends only validated RawRound request envelopes."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol

from .client import LedgerMindPermanentError, LedgerMindResponseError, round_acceptance_confirmed
from .defaults import (
    DEFAULT_DELIVERY_BASE_BACKOFF_SECONDS,
    DEFAULT_DELIVERY_MAX_BACKOFF_SECONDS,
)
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
        base_backoff_seconds: float = DEFAULT_DELIVERY_BASE_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_DELIVERY_MAX_BACKOFF_SECONDS,
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
            # A malformed request envelope will never be accepted by the server.
            # Quarantine it (retryable) instead of retrying forever.
            self.spool.fail(item_name, "invalid_request_envelope", retryable=True)
            return
        delivery = dict(envelope.get("delivery", {}))
        attempts = int(delivery.get("attempts", 0)) + 1
        delivery["attempts"] = attempts
        mutable = {"request": dict(request), "delivery": delivery}
        if self.max_attempts is not None and attempts > self.max_attempts:
            # Only callers that explicitly set a ceiling use this branch; the
            # production delivery paths keep max_attempts=None and retry forever.
            self.spool.fail(item_name, "max_attempts_exceeded")
            return
        try:
            response = self.client.submit_round(request)
            if not round_acceptance_confirmed(response):
                # The server answered but did not confirm durable acceptance:
                # treat as transient and keep retrying until it confirms.
                raise LedgerMindResponseError("round acceptance was not confirmed")
        except LedgerMindPermanentError as exc:
            # Non-core failure (4xx, invalid payload): quarantine immediately so it
            # does not block the queue. retryable keeps it recoverable after the
            # client (key/limit/payload) is fixed, but the promotion back to
            # ready/ is bounded: migration reads this attempt count as a ceiling.
            self.spool.fail(
                item_name,
                exc.reason or type(exc).__name__,
                retryable=True,
                delivery_patch={"attempts": attempts},
            )
        except Exception as exc:  # noqa: BLE001 - keep transient/core deliveries queued
            # Server/network/transient failures: retry without a ceiling until the
            # server confirms acceptance (200/202).
            delivery["last_error_type"] = type(exc).__name__
            delay = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** min(attempts - 1, 16)))
            delivery["next_attempt_at"] = time.time() + delay
            self.spool.retry(item_name, mutable)
        else:
            self.spool.complete(item_name)
